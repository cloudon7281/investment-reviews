"""The integration scenarios that are deterministic, against the anonymised corpus (#78).

These drive the real CLI over `anonymised_test_data/` -- real anonymised broker notes, in the real
directory shape -- and compare the whole report against a stored reference. The unit suite cannot
reach what they cover: it builds trees of empty files with the parsers patched out, so nothing in it
observes a document being read, a corporate action landing on a holding, or a number reaching a row.

The corporate-action defects in #77 lived exactly in that gap, and were invisible for a further
reason: these scenarios existed but stopped running on 2026-09-14, when enrolling this repository in
fleet testing moved the unit suite into `tests/` and broke the import the old harness used. Putting
them here rather than behind a CLI flag is what makes them run again, on every PR and every night,
by the one entry point the estate already has.

Only the two price-independent scenarios are here. The three that fetch live prices are in
`tests/nightly/`, which the fleet sweep runs and the PR gate does not (devops-model#268) -- a merge
must not wait on Yahoo.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

import review_harness

ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = "anonymised_test_data"
REFERENCES = ROOT / TEST_DATA / "reference_outputs"


def run_cli(*args):
    """Run portfolio.py over the anonymised corpus and return stdout and stderr together.

    `cwd` is the repository root explicitly, not the caller's. The harness these came from used
    `cwd='.'` and was only ever launched from the root; under pytest the working directory is
    wherever pytest was invoked, so inheriting it would make the scenario pass or fail according to
    where somebody typed the command.
    """
    result = subprocess.run(
        [sys.executable, "portfolio.py", "--base-dir", TEST_DATA, "--log-level", "WARNING", *args],
        capture_output=True, text=True, cwd=str(ROOT))
    return result.stdout + result.stderr


class DeterministicScenarios(unittest.TestCase):
    """Both of these are computed from parsed documents alone, so the report is byte-comparable."""

    def reference(self, name):
        with open(REFERENCES / name) as fh:
            return fh.read()

    def test_list_trades_matches_its_reference(self):
        """Every transaction the corpus implies, including corporate actions as their own rows.

        This is the scenario that covers #77's whole class: a dropped corporate action removes a
        `Conversion` row, a double-applied one adds a second, and a misdated one moves it. None of
        that is visible to a unit test that stubs the parser.
        """
        output = run_cli("--mode", "list-trades", "--start-date", "2024-01-01")
        self.assertTrue(
            review_harness.compare_list_trades_outputs(output, self.reference("list_trades_reference.txt")),
            "list-trades output differs from its reference -- see the logged line-by-line diff")

    def test_tax_report_matches_its_reference(self):
        """Realised gains for FY24: parsed notes and Section 104 pooling, no market data."""
        output = run_cli("--mode", "tax-report", "--tax-year", "FY24")
        self.assertTrue(
            review_harness.compare_tax_report_outputs(output, self.reference("tax_report_fy24_reference.txt")),
            "tax-report output differs from its reference -- see the logged line-by-line diff")


class TheScenariosCanActuallyFail(unittest.TestCase):
    """#29 was that the harness could not fail. A comparison nobody has seen fail proves nothing."""

    def test_a_changed_report_is_detected(self):
        output = run_cli("--mode", "list-trades", "--start-date", "2024-01-01")
        with open(REFERENCES / "list_trades_reference.txt") as fh:
            mutated = fh.read().replace("Conversion", "Cnoversion", 1)
        self.assertFalse(review_harness.compare_list_trades_outputs(output, mutated),
                         "a corrupted reference still compared equal -- the comparison is not comparing")

    def test_the_corpus_is_actually_present(self):
        """A missing corpus would otherwise show up as a puzzling diff rather than as itself."""
        self.assertTrue((ROOT / TEST_DATA).is_dir(), "anonymised_test_data/ is missing")
        self.assertTrue(REFERENCES.is_dir(), "anonymised_test_data/reference_outputs/ is missing")


if __name__ == "__main__":
    unittest.main()
