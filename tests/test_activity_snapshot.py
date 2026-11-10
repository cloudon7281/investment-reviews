"""`--mode portfolio-activity-snapshot` (activity_snapshot.py): interfaces E and F for investment-analysis
(its SPEC.md §4 E, F; investment-analysis#1, "Phase 3 plan")."""

import hashlib
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import activity_snapshot as A
from portfolio_review import StockTransaction

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = Path(__file__).parent / "fixtures" / "contracts"
NOTES = str(ROOT / "anonymised_test_data")
NIGHT = datetime(2026, 11, 10, 22, 41, 7, tzinfo=timezone.utc)
NEXT_NIGHT = datetime(2026, 11, 11, 22, 39, 52, tzinfo=timezone.utc)

# investment-analysis's schemas as merged there; a change to either is a contract change (decision D14).
PINNED = {
    "portfolio-activity-snapshot.v1.schema.json": "fd580af0475bfe9c22eb718099fea2b731c5e2963211fd9e1cd0b0d743ab366a",
    "benchmark-definitions.v1.schema.json": "2aaad42cef30d740211d00308b0afe6ecf74d9f87566cdddf4e961e865210d1a",
}


def read(directory, name):
    return json.loads((Path(directory) / name).read_text())


def test_the_schemas_are_the_contract_s_own_copies():
    for name, digest in PINNED.items():
        assert hashlib.sha256((ROOT / "contracts" / name).read_bytes()).hexdigest() == digest, name


# --- the contract's own examples: the identity rules here are the consumer's --------------------------------

@pytest.mark.parametrize("name", ["first-generation", "corrected-generation", "share-grant-and-demerger"])
def test_the_contract_s_snapshot_examples_pass_and_their_ids_are_reproduced(name):
    doc = json.loads((CONTRACTS / f"portfolio-activity-snapshot.{name}.json").read_text())
    assert A.check("PortfolioActivitySnapshot", doc) == []
    assert A._ordered([{k: v for k, v in a.items() if k not in ("eventId", "revision")} for a in doc["activities"]]) == [
        {k: v for k, v in a.items() if k != "revision"} for a in doc["activities"]]


def test_the_contract_s_definitions_example_passes():
    doc = json.loads((CONTRACTS / "benchmark-definitions.first-generation.json").read_text())
    assert A.check("BenchmarkDefinitions", doc) == []


# --- end to end, on the anonymised notes ----------------------------------------------------------------------

@pytest.fixture
def published(tmp_path):
    assert A.run(NOTES, str(tmp_path), now=NIGHT) == 0
    return tmp_path


def test_the_whole_history_and_the_benchmarks_are_published(published):
    e = read(published, A.SNAPSHOT_FILE)
    f = read(published, A.DEFINITIONS_FILE)
    assert A.check("PortfolioActivitySnapshot", e) == [] and A.check("BenchmarkDefinitions", f) == []
    assert e["generatedAt"] == "2026-11-10T22:41:07Z" and e["asOf"] == "2026-11-10"
    kinds = {(a["eventType"], a["derivation"]) for a in e["activities"]}
    assert {("buy", "broker_note"), ("sell", "broker_note"), ("conversion", "manual_entry")} <= kinds
    assert {a["accountKey"] for a in e["activities"]} == {"ISA", "Taxable", "Pension"}
    assert all(a["revision"] == 1 for a in e["activities"]) and e["tombstones"] == []
    assert not list(published.glob(".*"))                                      # no temporary file left behind


def test_the_benchmarks_are_this_service_s_own(published):
    from periodic_review_processor import BENCHMARKS
    from thesis_config import load_thesis_config
    f = read(published, A.DEFINITIONS_FILE)
    assert [(b["tag"], b["yahooSymbol"], b["name"]) for b in f["broadMarket"]] == list(BENCHMARKS)
    assert [t["name"] for t in f["theses"]] == [t["name"] for t in load_thesis_config(str(A.THESES))]


def test_an_unchanged_history_is_republished_with_the_same_id(published):
    first = read(published, A.SNAPSHOT_FILE)
    assert A.run(NOTES, str(published), now=NEXT_NIGHT) == 0
    second = read(published, A.SNAPSHOT_FILE)
    assert second["snapshotId"] == first["snapshotId"] and second["activities"] == first["activities"]
    assert second["generatedAt"] == "2026-11-11T22:39:52Z"                     # fresh, so the feed is seen to be


def test_a_scan_that_logs_a_problem_publishes_no_history_but_the_benchmarks_still_go(published, monkeypatch):
    before = read(published, A.SNAPSHOT_FILE)

    def troubled(base_dir, note_cache=None):
        recorder = A._Recorder()
        recorder.emit(logging.makeLogRecord({"levelno": logging.ERROR, "levelname": "ERROR",
                                             "msg": "Error processing activity.mhtml: bad table"}))
        raise A.ExportRefused(recorder.problems)
    monkeypatch.setattr(A, "scan", troubled)
    assert A.run(NOTES, str(published), now=NEXT_NIGHT) == 1
    assert read(published, A.SNAPSHOT_FILE) == before                          # the last publication stands
    assert read(published, A.DEFINITIONS_FILE)["generatedAt"] == "2026-11-11T22:39:52Z"


def test_the_recorder_passes_only_the_known_harmless_warnings():
    r = A._Recorder()
    for level, msg in [(logging.WARNING, "Stock VWRL first transaction is SELL, not BUY/TRANSFER/STOCK_CONVERSION - excluding entirely"),
                       (logging.WARNING, "Stock NVDA in isa tag changed from 'None' to 'AI' - this may indicate an input error"),
                       (logging.WARNING, "No matching stock found for EXA in isa in note.pdf"),
                       (logging.ERROR, "Error processing a.csv: boom")]:
        r.emit(logging.makeLogRecord({"levelno": level, "levelname": logging.getLevelName(level), "msg": msg}))
    assert len(r.problems) == 2 and "No matching stock" in r.problems[0] and "boom" in r.problems[1]


def test_an_unreadable_last_publication_is_refused_not_treated_as_none(published):
    (published / A.SNAPSHOT_FILE).write_text("{not json")
    assert A.run(NOTES, str(published), now=NEXT_NIGHT) == 1
    assert (published / A.SNAPSHOT_FILE).read_text() == "{not json"


def test_missing_notes_are_refused(tmp_path):
    assert A.run(str(tmp_path / "absent"), str(tmp_path / "out"), now=NIGHT) == 1
    assert not (tmp_path / "out" / A.SNAPSHOT_FILE).exists()


def test_the_cli_mode_publishes(tmp_path):
    # The note cache lives under HOME; a cache it cannot write is a warning, which the export would refuse on.
    env = {**os.environ, "HOME": str(tmp_path / "home")}
    result = subprocess.run([sys.executable, "-m", "portfolio", "--mode", "portfolio-activity-snapshot",
                             "--base-dir", NOTES, "--export-dir", str(tmp_path / "out")], cwd=ROOT, env=env,
                            capture_output=True, text=True)
    assert result.returncode == 0, (result.stdout + result.stderr)[-2000:]
    assert A.check("PortfolioActivitySnapshot", read(tmp_path / "out", A.SNAPSHOT_FILE)) == []


# --- revisions and tombstones (decision D10) --------------------------------------------------------------------

def event(eid, **kw):
    return {"eventId": eid, "accountKey": "ISA", "securityKey": "EXA.L", "tradeDate": "2024-01-02", "eventType": "buy",
            "quantity": "10", "unitPrice": "1", "currency": "GBP", "gbpConsideration": "10", "conversion": None,
            "derivation": "broker_note", "sourceRef": None, **kw}


def test_changed_content_is_a_new_revision_and_an_absent_event_a_tombstone():
    first, _ = A.revise([event("a"), event("b")], None, "T1")
    second, buried = A.revise([event("a", unitPrice="1.05")], {"activities": first, "tombstones": []}, "T2")
    assert [(a["eventId"], a["revision"]) for a in second] == [("a", 2)]
    assert buried == [{"eventId": "b", "lastRevision": 1, "removedAt": "T2"}]
    third, kept = A.revise([event("a", unitPrice="1.05")], {"activities": second, "tombstones": buried}, "T3")
    assert third[0]["revision"] == 2 and kept == buried                       # a tombstone stays
    back, gone = A.revise([event("a", unitPrice="1.05"), event("b")], {"activities": third, "tombstones": kept}, "T4")
    assert [(a["eventId"], a["revision"]) for a in back] == [("a", 2), ("b", 2)] and gone == []


# --- what the scan records, as E carries it -----------------------------------------------------------------------

def note(category, ticker, *transactions, currency="NOK"):
    return SimpleNamespace(category=category, ticker=ticker, stock_name=ticker, currency=currency, transactions=list(transactions))


def history(*notes, excluded=()):
    review = SimpleNamespace(stock_notes={"isa": [], "taxable": [], "pension": []}, excluded_stock_notes=list(excluded))
    for n in notes:
        review.stock_notes[n.category].append(n)
    return A.build_history(review, "/notes")


def test_a_demerger_s_cost_only_transfer_and_a_share_grant_are_carried():
    day = datetime(2026, 4, 23)
    _, activities = history(
        note("isa", "KMAR.OL", StockTransaction(day, "TRANSFER", 1192, 0.0, 5847.0, source_file="/notes/ISA/2026/d.yaml")),
        note("isa", "KOG.OL", StockTransaction(day, "TRANSFER", 0, 0.0, -5847.0, source_file="/notes/ISA/2026/d.yaml")),
        note("isa", "TECK", StockTransaction(datetime(2023, 5, 26), "STOCK_CONVERSION", 0, 0.0, 0.0, new_quantity=58,
                                             origin_file="/notes/ISA/2023/t.yaml"), currency="CAD"))
    by = {a["securityKey"]: a for a in activities}
    assert (by["KMAR.OL"]["eventType"], by["KMAR.OL"]["quantity"], by["KMAR.OL"]["gbpConsideration"]) == ("transfer_in", "1192", "5847")
    assert (by["KOG.OL"]["eventType"], by["KOG.OL"]["quantity"], by["KOG.OL"]["gbpConsideration"]) == ("transfer_out", "0", "5847")
    assert by["KOG.OL"]["derivation"] == "manual_entry" and by["KOG.OL"]["sourceRef"] == "ISA/2026/d.yaml"
    assert (by["TECK"]["quantity"], by["TECK"]["conversion"]["newQuantity"], by["TECK"]["derivation"]) == ("0", "58", "manual_entry")


def test_a_cost_only_transfer_s_direction_is_its_cost_s():
    _, activities = history(note("isa", "EXGP.OL", StockTransaction(datetime(2026, 4, 23), "TRANSFER", 0, 0.0, 120.0,
                                                                     source_file="/notes/ISA/2026/d.yaml")))
    assert (activities[0]["eventType"], activities[0]["gbpConsideration"]) == ("transfer_in", "120")


def test_a_merger_is_a_sale_in_gbp_and_an_inferred_transfer_has_no_note():
    day = datetime(2024, 2, 1)
    _, activities = history(
        note("pension", "EXDM.L", StockTransaction(day, "SELL", 1000, 0.875, 875.0, origin_file="/notes/Pension/m.pdf"), currency="USD"),
        note("taxable", "EXC.L", StockTransaction(day, "TRANSFER", -400, 2.31, -924.0)))
    by = {a["securityKey"]: a for a in activities}
    assert (by["EXDM.L"]["derivation"], by["EXDM.L"]["currency"], by["EXDM.L"]["sourceRef"]) == ("merger_as_sale", "GBP", "Pension/m.pdf")
    assert (by["EXC.L"]["eventType"], by["EXC.L"]["derivation"], by["EXC.L"]["sourceRef"]) == ("transfer_out", "inferred_bed_and_isa", None)


def test_a_stock_left_out_of_the_reports_is_still_exported():
    _, activities = history(excluded=[note("taxable", "VWRL", StockTransaction(datetime(2020, 3, 2), "SELL", 50, 80.1, 4005.0,
                                                                                source_file="/notes/Taxable/2020/s.pdf"), currency="GBP")])
    assert [(a["securityKey"], a["eventType"]) for a in activities] == [("VWRL", "sell")]


def test_an_event_the_scan_dated_itself_is_refused():
    undated = StockTransaction(datetime(2026, 11, 10, 22, 5, 31), "BUY", 5, 1.0, 5.0, source_file="/notes/ISA/x.pdf")
    with pytest.raises(A.ExportRefused, match="its date was not read from its note"):
        history(note("isa", "EXA.L", undated))


def test_a_trade_with_no_units_is_refused():
    with pytest.raises(A.ExportRefused, match="a trade with no units"):
        history(note("isa", "EXA.L", StockTransaction(datetime(2024, 1, 2), "BUY", 0, 1.0, 0.0, source_file="/notes/x.pdf")))


def test_same_day_duplicates_take_ordinals_by_quantity():
    day = datetime(2025, 1, 6)
    _, activities = history(note("pension", "EXFN.L",
                                 StockTransaction(day, "BUY", 24.6912, 2.025, 50.0, source_file="/notes/f.yaml"),
                                 StockTransaction(day, "BUY", 12.3456, 2.025, 25.0, source_file="/notes/f.yaml"), currency="GBP"))
    assert [a["quantity"] for a in activities] == ["12.3456", "24.6912"]
    assert activities[0]["eventId"] == A.event_id("Pension", "EXFN.L", "2025-01-06", "buy", 1)


@pytest.mark.parametrize("value, places, text", [(100.0, 6, "100"), (2041.9500000000003, 2, "2041.95"), (0.875, 6, "0.875"),
                                                 (12.3456, 6, "12.3456"), (-0.0, 2, "0"), (1e-7, 6, "0")])
def test_decimals_are_plain_strings(value, places, text):
    assert A.decimal(value, places) == text
