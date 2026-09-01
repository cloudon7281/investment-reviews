#!/usr/bin/env python3
"""Report and reconcile the tag a stock's notes are filed under.

A stock's tag is the directory its notes sit in — <category>/<year>/<tag>/ — and the
scanner takes the tag from the first note it processes for a given (ticker, category),
warning but not failing when later notes disagree.  A stock whose notes are split across
two tags therefore aggregates under whichever the scan happened to see first, silently.

The notes exist in three places, and a tag is only really changed when it has been
changed in all of them:

    iCloud   ~/Library/Mobile Documents/com~apple~Pages/Documents/Investment/history
      | ditto, hourly (additive: never deletes from staging)
    staging  ~/Documents/iCloud-Staging/history
      | rsync -a --delete, hourly (a mirror: jarvis is forced to match staging)
    jarvis   /Users/cl/srv/investment-reviews/state/history

The two hops do not behave alike, and that dictates the order moves must be made in.
Because the first hop never deletes, a note left behind in iCloud is copied back into
staging; because the second hop mirrors, anything left in staging is pushed to jarvis,
and conversely anything removed from staging is removed from jarvis on its own.  So
moves go upstream first — iCloud, then staging, then jarvis — and each step leaves
nothing behind it that a later sync could use to recreate the old path.  Moving in the
other order guarantees the move is undone within the hour.

Usage:
    reconcile_tags.py FRAGMENT                        # report where the notes are filed
    reconcile_tags.py FRAGMENT --check                # exit 1 if the filing disagrees
    reconcile_tags.py FRAGMENT --move-to TAG          # show what would move
    reconcile_tags.py FRAGMENT --move-to TAG --apply  # move, then verify
"""

import argparse
import os
import shlex
import subprocess
import sys
from collections import defaultdict
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

# Extensions the scanner reads.  Anything else in the tree (.DS_Store, notes-to-self) is
# not a contract note and must not be moved on a stock's behalf.
NOTE_EXTENSIONS = ('.pdf', '.csv', '.mhtml')

CATEGORIES = ('isa', 'taxable', 'pension')

ICLOUD_ROOT = os.path.expanduser(
    '~/Library/Mobile Documents/com~apple~Pages/Documents/Investment/history')
STAGING_ROOT = os.path.expanduser('~/Documents/iCloud-Staging/history')
JARVIS_HOST = 'jarvis'
JARVIS_ROOT = '/Users/cl/srv/investment-reviews/state/history'

# Set by the launchd jobs that run the two hops.  A move made while one of them is
# mid-flight can be partly undone, so the tool refuses to start rather than race it.
SYNC_SCRIPTS = ('sync-icloud-to-local.sh', 'sync-investment-data.sh')


class Note(NamedTuple):
    """One matching note file, and where the directory structure files it."""
    location: str
    path: str
    category: Optional[str]
    year: Optional[str]
    tag: Optional[str]
    filename: str

    @property
    def placing(self) -> Tuple[Optional[str], Optional[str]]:
        """The (category, tag) this note claims.  Year is not part of a stock's tag."""
        return (self.category, self.tag)


def parse_note_path(root: str, path: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Split a note path below root into (category, year, tag).

    Mirrors PortfolioReview._extract_account_type_and_year: <category>/<year>/(<tag>/)file,
    where the tag directory is optional and a four-digit name is a year, not a tag.  Kept
    deliberately close to it — a tool that disagreed with the scanner about where a note
    is filed would report the wrong thing with total confidence.
    """
    relative = os.path.relpath(path, root)
    parts = relative.split(os.sep)

    category = year = tag = None
    for i, part in enumerate(parts):
        if part.lower() in CATEGORIES:
            category = part.lower()
            if i + 1 < len(parts):
                candidate = parts[i + 1]
                if candidate.isdigit() and len(candidate) == 4:
                    year = candidate
                    if i + 2 < len(parts):
                        candidate = parts[i + 2]
                        is_year = candidate.isdigit() and len(candidate) == 4
                        if not candidate.lower().endswith(NOTE_EXTENSIONS) and not is_year:
                            tag = candidate
            break
    return category, year, tag


def is_note(filename: str) -> bool:
    return filename.lower().endswith(NOTE_EXTENSIONS)


class Location(object):
    """One of the three copies of the notes tree."""

    def __init__(self, name: str, root: str) -> None:
        self.name = name
        self.root = root

    def list_files(self) -> List[str]:
        raise NotImplementedError

    def move(self, source: str, destination: str) -> None:
        raise NotImplementedError

    def exists(self, path: str) -> bool:
        raise NotImplementedError

    def available(self) -> bool:
        raise NotImplementedError

    def find(self, fragment: str) -> List[Note]:
        """Every note whose filename contains fragment, case-insensitively."""
        needle = fragment.lower()
        found = []
        for path in self.list_files():
            filename = os.path.basename(path)
            if not is_note(filename) or needle not in filename.lower():
                continue
            category, year, tag = parse_note_path(self.root, path)
            found.append(Note(self.name, path, category, year, tag, filename))
        return sorted(found, key=lambda note: note.path)

    def retag(self, note: Note, tag: str) -> str:
        """Path this note would take under tag, keeping its category and year.

        Built by rewriting the note's own path rather than reassembling one from the
        parsed parts: the category directory is 'ISA' but parses to 'isa', and a
        destination spelled from the parsed form would create a second, differently-cased
        tree beside the real one on a case-sensitive filesystem.
        """
        parts = os.path.relpath(note.path, self.root).split(os.sep)
        category_index = next(i for i, part in enumerate(parts) if part.lower() in CATEGORIES)
        head = parts[:category_index + 2]  # <category>/<year> exactly as they are on disk
        return os.path.join(self.root, *head, tag, note.filename)


class LocalLocation(Location):
    def available(self) -> bool:
        return os.path.isdir(self.root)

    def list_files(self) -> List[str]:
        paths = []
        for directory, _, filenames in os.walk(self.root):
            for filename in filenames:
                paths.append(os.path.join(directory, filename))
        return paths

    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def move(self, source: str, destination: str) -> None:
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        if os.path.exists(destination):
            raise RuntimeError(f"{self.name}: {destination} already exists")
        os.rename(source, destination)


class RemoteLocation(Location):
    """The copy on jarvis, reached over ssh.

    Filenames carry spaces and ampersands, so every path crossing the ssh boundary is
    quoted for the remote shell rather than interpolated.
    """

    def __init__(self, name: str, host: str, root: str) -> None:
        Location.__init__(self, name, root)
        self.host = host

    def _run(self, command: str) -> subprocess.CompletedProcess:
        return subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
                               self.host, command],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def available(self) -> bool:
        return self._run(f"test -d {shlex.quote(self.root)}").returncode == 0

    def list_files(self) -> List[str]:
        result = self._run(f"find {shlex.quote(self.root)} -type f")
        if result.returncode != 0:
            raise RuntimeError(f"{self.name}: listing failed: {result.stderr.strip()}")
        return [line for line in result.stdout.splitlines() if line]

    def exists(self, path: str) -> bool:
        return self._run(f"test -e {shlex.quote(path)}").returncode == 0

    def move(self, source: str, destination: str) -> None:
        quoted_destination = shlex.quote(destination)
        command = (f"test ! -e {quoted_destination} && "
                   f"mkdir -p {shlex.quote(os.path.dirname(destination))} && "
                   f"mv {shlex.quote(source)} {quoted_destination}")
        result = self._run(command)
        if result.returncode != 0:
            raise RuntimeError(f"{self.name}: move failed: {result.stderr.strip() or command}")


def build_locations() -> List[Location]:
    """Upstream first.  The order is the safety property, not a preference."""
    return [
        LocalLocation('icloud', ICLOUD_ROOT),
        LocalLocation('staging', STAGING_ROOT),
        RemoteLocation('jarvis', JARVIS_HOST, JARVIS_ROOT),
    ]


def sync_in_flight() -> List[str]:
    """Which sync hops are running right now, if any."""
    running = []
    for script in SYNC_SCRIPTS:
        result = subprocess.run(['pgrep', '-f', script],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0 and result.stdout.strip():
            running.append(script)
    return running


def placings_by_location(notes: Sequence[Note]) -> Dict[str, Dict[Optional[str], set]]:
    """location -> category -> {tags seen}."""
    placings = defaultdict(lambda: defaultdict(set))
    for note in notes:
        placings[note.location][note.category].add(note.tag)
    return placings


def disagreements(notes: Sequence[Note], locations: Sequence[str]) -> List[str]:
    """Every way the filing of these notes is not one tag per category everywhere.

    Two distinct faults, and the second is the one that outlives a naive fix: a category
    split across tags in one place, and a category filed differently between places.  The
    latter is what an incomplete move leaves behind, and the syncs will spread it.
    """
    problems = []
    placings = placings_by_location(notes)

    for location in locations:
        for category, tags in sorted(placings.get(location, {}).items(), key=lambda kv: str(kv[0])):
            if len(tags) > 1:
                shown = ', '.join(sorted(str(tag) for tag in tags))
                problems.append(f"{location}: {category} notes are split across {len(tags)} tags: {shown}")

    categories = {note.category for note in notes}
    for category in sorted(categories, key=str):
        per_location = {}
        for location in locations:
            tags = placings.get(location, {}).get(category)
            if tags:
                per_location[location] = tuple(sorted(str(tag) for tag in tags))
        if len(set(per_location.values())) > 1:
            shown = '; '.join(f"{location}={'/'.join(tags)}" for location, tags in sorted(per_location.items()))
            problems.append(f"{category}: filed differently in different locations: {shown}")

    return problems


def report(notes: Sequence[Note], locations: Sequence[Location]) -> None:
    if not notes:
        print("No matching notes found.")
        return

    print(f"{'LOCATION':9} {'CATEGORY':9} {'YEAR':5} {'TAG':34} FILE")
    for note in sorted(notes, key=lambda n: ([l.name for l in locations].index(n.location),
                                             str(n.category), str(n.year), n.filename)):
        tag = note.tag if note.tag is not None else '(none)'
        print(f"{note.location:9} {str(note.category):9} {str(note.year):5} {tag:34.34} {note.filename}")

    print()
    placings = placings_by_location(notes)
    for location in [l.name for l in locations]:
        for category, tags in sorted(placings.get(location, {}).items(), key=lambda kv: str(kv[0])):
            shown = ', '.join(sorted(str(tag) for tag in tags))
            count = sum(1 for n in notes if n.location == location and n.category == category)
            print(f"  {location:9} {str(category):9} {count:2d} note(s) under: {shown}")


def plan(notes: Sequence[Note], locations: Sequence[Location], tag: str) -> List[Tuple[Location, Note, str]]:
    """What would move, in the order it must move: upstream location first."""
    moves = []
    for location in locations:
        for note in notes:
            if note.location != location.name or note.tag == tag:
                continue
            if note.category is None or note.year is None:
                print(f"  SKIP  {note.path}\n"
                      f"        (not under <category>/<year>/, so it has no tag to change)")
                continue
            moves.append((location, note, location.retag(note, tag)))
    return moves


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('fragment', help="text appearing in the note filenames, e.g. 'Fidelity_Emerging'")
    parser.add_argument('--move-to', metavar='TAG',
                        help='file every matching note under this tag, keeping its category and year')
    parser.add_argument('--apply', action='store_true',
                        help='actually move the files (without it, --move-to only shows the plan)')
    parser.add_argument('--check', action='store_true',
                        help='exit 1 if the notes are not filed under one tag per category everywhere')
    args = parser.parse_args(argv)

    locations = build_locations()
    unavailable = [location.name for location in locations if not location.available()]
    if unavailable:
        print(f"ERROR: cannot reach {', '.join(unavailable)}; refusing to act on a partial view.",
              file=sys.stderr)
        return 2

    notes = []
    for location in locations:
        notes.extend(location.find(args.fragment))

    report(notes, locations)

    if not notes:
        return 0 if not args.check else 1

    names = [location.name for location in locations]
    problems = disagreements(notes, names)

    if args.move_to:
        moves = plan(notes, locations, args.move_to)
        if not moves:
            print(f"\nNothing to do: every matching note is already filed under '{args.move_to}'.")
            return 0

        print(f"\n{'Moving' if args.apply else 'Would move'} {len(moves)} file(s) to '{args.move_to}':")
        for location, note, destination in moves:
            print(f"  {location.name:9} {note.tag} -> {args.move_to}   {note.filename}")

        if not args.apply:
            print("\nRe-run with --apply to make these changes.")
            return 0

        running = sync_in_flight()
        if running:
            print(f"\nERROR: {', '.join(running)} is running now. A move made mid-sync can be "
                  f"partly undone. Wait for it to finish and re-run.", file=sys.stderr)
            return 2

        print()
        for location, note, destination in moves:
            location.move(note.path, destination)
            print(f"  moved   {location.name:9} {note.filename}")

        # Nothing upstream should still hold an old path; if it does, the next sync will
        # push it back down and undo the move.
        print("\nVerifying...")
        after = []
        for location in locations:
            after.extend(location.find(args.fragment))
        lingering = [note for note in after if note.tag != args.move_to and note.category is not None]
        if lingering:
            print("FAILED: these are still filed elsewhere and will be resynced:", file=sys.stderr)
            for note in lingering:
                print(f"  {note.location:9} {note.tag}  {note.filename}", file=sys.stderr)
            return 1

        remaining = disagreements(after, names)
        if remaining:
            print("FAILED: the notes are still not filed consistently:", file=sys.stderr)
            for problem in remaining:
                print(f"  {problem}", file=sys.stderr)
            return 1

        print(f"OK: all {len(after)} matching note(s) are filed under '{args.move_to}' in "
              f"{', '.join(names)}.")
        print("The syncs are hourly and additive upstream; re-run with --check after the "
              "next hop if you want confirmation nothing was recreated.")
        return 0

    if problems:
        print("\nINCONSISTENT:")
        for problem in problems:
            print(f"  {problem}")
        print("\nUse --move-to TAG to file them all under one tag.")
        return 1 if args.check else 0

    print("\nConsistent: one tag per category in every location.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
