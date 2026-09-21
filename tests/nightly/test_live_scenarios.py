"""The integration scenarios that need live market prices (#78, devops-model#268).

These run in the nightly fleet sweep and NOT in the PR gate, because they shell out to a run that
fetches prices from Yahoo. Gating a merge on a third party being up is what `tests/nightly/` exists
to avoid; leaving them out of `tests/` altogether is how they came to run nowhere at all.

They are checked by their invariants rather than against a stored reference, and that is not a
weaker comparison chosen for convenience -- their values come from prices on the day, so a reference
would go stale and fail spuriously, or be loosened until it could not fail (#29). Two things are
asserted instead: the run reports no invariant violation, and every table it should have produced is
present with at least one row. The second half is what catches a run that collapsed and printed
nothing, which is how the periodic scenario once passed vacuously.
"""

import subprocess
import sys
import unittest
from pathlib import Path

import review_harness

ROOT = Path(__file__).resolve().parents[2]
TEST_DATA = "anonymised_test_data"


def run_cli(*args):
    result = subprocess.run(
        [sys.executable, "portfolio.py", "--base-dir", TEST_DATA, "--log-level", "WARNING", *args],
        capture_output=True, text=True, cwd=str(ROOT))
    return result.stdout + result.stderr


class LivePriceScenarios(unittest.TestCase):

    def test_full_history(self):
        output = run_cli("--mode", "full-history")
        self.assertTrue(
            review_harness.check_review_run(output, "Full history",
                                            ["Portfolio Summary", "Full Investment History"]),
            "full-history reported an invariant violation, or produced an empty table")

    def test_periodic_review(self):
        """The dates are the ones the reference outputs were captured with, so the corpus covers them."""
        output = run_cli("--mode", "periodic-review", "--start-date", "2025-03-01",
                         "--end-date", "2025-03-31", "--eval-date", "2025-06-16")
        self.assertTrue(
            review_harness.check_review_run(output, "Periodic review",
                                            ["Periodic Review Summary", "New Stocks",
                                             "Retained Stocks", "Sold Stocks"]),
            "periodic-review reported an invariant violation, or produced an empty table")

    def test_annual_review(self):
        output = run_cli("--mode", "annual-review", "--start-date", "2024-01-01")
        self.assertTrue(
            review_harness.check_review_run(output, "Annual review",
                                            ["Annual Review Summary", "Annual Review Detail"]),
            "annual-review reported an invariant violation, or produced an empty table")


class TheseChecksCanFail(unittest.TestCase):
    """A structural check is easy to write so that nothing can ever fail it."""

    def test_a_collapsed_run_is_not_reported_as_sound(self):
        self.assertFalse(review_harness.check_review_run("", "Full history", ["Portfolio Summary"]))

    def test_an_invariant_violation_is_not_reported_as_sound(self):
        output = run_cli("--mode", "full-history") + \
            "\nERROR [root] INVARIANT VIOLATION: 3 held positions have no price\n"
        self.assertFalse(review_harness.check_review_run(output, "Full history",
                                                         ["Portfolio Summary"]))


if __name__ == "__main__":
    unittest.main()
