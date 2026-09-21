# Testing

```
./scripts/test
```

That is the whole contract: it exits 0 if and only if the suite ran and passed. It builds its own
virtualenv from this repository's declared manifests, so it behaves the same in a working clone, in CI,
and in tier-1-ci's nightly fleet sweep.

## The layout is mandated

```
tests/test_*.py      Python, run by pytest
tests/test_*.sh      shell, executed directly
```

Anything else fails with a named reason rather than being worked around. A test file outside `tests/` is
rejected, and an empty `tests/` is a failure — a runner that cannot find a suite must not report success,
which is the whole point of the exercise.

## What is yours and what is not

- `scripts/test` is a **shim, distributed from tier2-project's templates**. Do not edit it here; the
  nightly sweep reports any repository whose copy has drifted.
- The runner behind it is `lib/run-tests` in **tier-1-ci**. That is where the layout rules, interpreter
  resolution and dependency handling live, and there is exactly one copy of it.
- `pyproject.toml`, this file, and the tests themselves are **yours**.

## Declaring the interpreter

`requires-python` in `pyproject.toml` decides which interpreter the suite runs on. Set it to what this
service actually ships — matching its Dockerfile — not to the widest range that resolves.

## Test dependencies

Runtime dependencies go in `requirements.txt`. Dependencies only the tests need go in
`requirements-dev.txt`, which the runner installs as well. Putting a test-only package in
`requirements.txt` would declare a runtime dependency this service does not have.

## This repository's layout, and why it changed

The suite used to live at the repository root as `test_unit.py`, alongside `test_runner.py`. Enrolling in
fleet testing moved it into `tests/` and renamed the second file to `review_harness.py`, because:

- `test_runner.py` contains **no tests**. It is a library of helpers — `run_tests`, `check_review_run`,
  `extract_table_data` — and `portfolio.py` imports it, so it is application code that merely started
  with `test_`. Left where it was, the runner would reject this repository for having a test file outside
  `tests/`; moved into `tests/`, it would break that production import.
- `tests/conftest.py` puts the repository root on `sys.path`, because the modules under test are single
  files there and pytest prepends the test file's directory rather than the rootdir.

## The integration scenarios

They drive the real CLI over `anonymised_test_data/` — real anonymised broker notes in the real
directory shape — which is the only thing in this repository that reads an actual document. The unit
suite builds trees of empty files with the parsers patched out, so nothing in it can observe a
corporate action landing on a holding or a number reaching a row.

They are split by whether they need a price:

| Scenario | Checked by | Runs in |
|---|---|---|
| `list-trades` | byte comparison against `reference_outputs/` | `tests/test_integration.py` — every PR and the sweep |
| `tax-report` | byte comparison against `reference_outputs/` | `tests/test_integration.py` — every PR and the sweep |
| `full-history` | invariants and table presence | `tests/nightly/` — the sweep only |
| `periodic-review` | invariants and table presence | `tests/nightly/` — the sweep only |
| `annual-review` | invariants and table presence | `tests/nightly/` — the sweep only |

The bottom three fetch live prices from Yahoo, so gating a merge on them would gate it on a third
party being up. `tests/nightly/` is the estate-wide mechanism for that
(`software-development-standards.md`, "Test layout"); run them locally with
`RUN_TESTS_INCLUDE_NIGHTLY=1 ./scripts/test`.

They cannot have reference outputs for the same reason: the values come from prices on the day, so a
stored snapshot would go stale and fail spuriously, or be loosened until it could not fail (#29).

**They used to run behind `portfolio.py --mode test`, and stopped.** Moving the unit suite into
`tests/` broke the import that harness used, and because nothing reported on it, the fact that they
had not run since 2026-09-14 surfaced only when a subdivision defect got through (#77, #78). That
mode, `run_tests` and `--test-data` are gone; the scenarios live in `tests/` now, where the one
entry point the estate already has runs them.
