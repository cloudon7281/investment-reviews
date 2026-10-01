"""A cache of parsed notes, one per base directory (investment-reviews#91).

Parsing the PDF and MHTML notes is nearly all of a run's time -- about 73 of 75 seconds over
the full history -- and between the interactive runs of a monthly review the notes do not
change.  Each note's parsed result is kept, keyed by its path relative to the base directory,
its size, its modification time and the parser that read it.  A note whose key is unchanged is
not read again; a new or changed note is parsed and its entry replaced; the entry for a note
that no longer exists is dropped.  Holdings are still built from the parsed results on every
run, so filters and corporate actions are unaffected.

What a note parses to also depends on the parser code, on the ticker mappings it applies and on
the libraries and interpreter underneath it.  All of those are fingerprinted, and a cache with a
different fingerprint is discarded whole, so a parser fix is never masked by an old result.

A note that fails to parse is never cached: it is retried, and reported, on every run.

The cache lives under ~/.cache rather than in the base directory, because the base directory is
the synced notes tree, and on jarvis it is mounted read-only.
"""

import hashlib
import importlib.metadata
import json
import os
import sys
from datetime import datetime
from logger import logger

# Everything that decides what a note parses to.  ticker_mappings.yaml is applied at parse time.
_FINGERPRINTED_FILES = ('pdf_parser.py', 'mhtml_parser.py', 'ticker_mapping.py',
                        'ticker_mappings.yaml', 'note_cache.py')
_FINGERPRINTED_DISTRIBUTIONS = ('pdfplumber', 'pdfminer.six', 'beautifulsoup4')


def _fingerprint() -> str:
    digest = hashlib.sha256()
    here = os.path.dirname(os.path.abspath(__file__))
    for name in _FINGERPRINTED_FILES:
        with open(os.path.join(here, name), 'rb') as fh:
            digest.update(name.encode() + b'\0' + fh.read() + b'\0')
    for dist in _FINGERPRINTED_DISTRIBUTIONS:
        digest.update(f'{dist}={importlib.metadata.version(dist)}\0'.encode())
    digest.update(f'python={sys.version_info[:3]}'.encode())
    return digest.hexdigest()


def _encode(value):
    """A parsed note as JSON-ready data.  A datetime becomes {"$datetime": isoformat}."""
    if isinstance(value, datetime):
        return {'$datetime': value.isoformat()}
    if isinstance(value, dict):
        return {k: _encode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_encode(v) for v in value]
    return value


def _decode(value):
    if isinstance(value, dict):
        if value.keys() == {'$datetime'}:
            return datetime.fromisoformat(value['$datetime'])
        return {k: _decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode(v) for v in value]
    return value


class NoteCache:

    def __init__(self, base_dir: str, rebuild: bool = False):
        """Load the cache for base_dir, or start empty when rebuild is set."""
        self.base_dir = base_dir
        name = hashlib.sha256(os.path.realpath(base_dir).encode()).hexdigest()[:16]
        self.path = os.path.join(os.path.expanduser('~'), '.cache', 'investment-reviews',
                                 f'notes-{name}.json')
        self.fingerprint = _fingerprint()
        self.entries = {} if rebuild else self._load()
        self.changed = False
        self.reused = 0
        self.parsed = 0

    def _load(self) -> dict:
        try:
            with open(self.path) as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as e:
            logger.warning(f"Ignoring unreadable note cache {self.path}: {e}")
            return {}
        if data.get('fingerprint') != self.fingerprint:
            logger.info("The note parsers have changed since the note cache was written; "
                        "every note will be read again")
            return {}
        return data['entries']

    def parse(self, parser, file_path: str):
        """Return parser(file_path), reusing the cached result while the note is unchanged."""
        key = os.path.relpath(file_path, self.base_dir)
        stat = os.stat(file_path)
        stamp = [parser.__name__, stat.st_size, stat.st_mtime_ns]

        entry = self.entries.get(key)
        if entry is not None and entry['stamp'] == stamp:
            self.reused += 1
            return _decode(entry['result'])

        result = parser(file_path)  # a parse failure propagates, and nothing is cached
        self.parsed += 1
        self.changed = True
        # Cache only what comes back from JSON exactly as it went in, so a type the encoding
        # does not know is re-parsed every run rather than altered.
        encoded = json.loads(json.dumps(_encode(result)))
        if result is not None and _decode(encoded) == result:
            self.entries[key] = {'stamp': stamp, 'result': encoded}
        else:
            self.entries.pop(key, None)
        return result

    def save(self) -> None:
        """Write the cache back, dropping entries for notes that no longer exist.

        Entries for notes this run did not read -- excluded by a filter, say -- are kept.
        A failure to write is reported and otherwise ignored: the run's results do not
        depend on it.
        """
        logger.info(f"Notes: {self.reused} from the cache, {self.parsed} parsed")
        gone = [key for key in self.entries if not os.path.exists(os.path.join(self.base_dir, key))]
        for key in gone:
            del self.entries[key]
        if not (self.changed or gone):
            return

        tmp = f'{self.path}.{os.getpid()}.tmp'
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(tmp, 'w') as fh:
                json.dump({'fingerprint': self.fingerprint,
                           'base_dir': os.path.realpath(self.base_dir),
                           'entries': self.entries}, fh)
            # Replaced in one step, so a concurrent run reads the old cache or the new one.
            os.replace(tmp, self.path)
        except OSError as e:
            logger.warning(f"Could not write the note cache {self.path}: {e}")
