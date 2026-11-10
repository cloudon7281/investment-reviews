"""`--mode portfolio-activity-snapshot`: this service's parsed trade and corporate-action history, and its benchmark
definitions, published for investment-analysis as interfaces E (`PortfolioActivitySnapshot.v1`) and F
(`BenchmarkDefinitions.v1`) into the shared store `investment-reviews-exports`.

The contracts are investment-analysis's (its SPEC.md §4 E and F; investment-analysis#1, "Phase 3 plan"). Their
schemas are byte-identical copies under contracts/, pinned by hash in the tests (decision D14).

This is a projection of what the parsers already record. It changes nothing this service reports, and it
invents nothing: no fees, dividends, brokers or ISINs, because no parser records them.

**Complete or not at all.** The scan logs, and carries on past, notes it cannot read or apply. A history
missing those notes would be published as complete, so the export refuses if the scan logs any error or any
warning it does not recognise as harmless. It also refuses an event whose date was not read from its note:
the scan dates such an event at the moment of the run, and that would give it a new identity every night.

**Identity** (decision D10). An event's id is derived from its account, security, date, type and ordinal, not
from its note's path, which changes when a stock is re-tagged. Each build is compared with the last
publication, read back from the store:
- an event whose content changed takes the next revision;
- an event no longer present becomes a tombstone, kept from then on;
- an event that reappears takes the revision after its tombstone's.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from datetime import date, datetime, time, timezone
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator

logger = logging.getLogger()

HERE = Path(__file__).resolve().parent
SCHEMAS = {"PortfolioActivitySnapshot": HERE / "contracts" / "portfolio-activity-snapshot.v1.schema.json",
           "BenchmarkDefinitions": HERE / "contracts" / "benchmark-definitions.v1.schema.json"}
THESES = HERE / "briefs" / "thesis.json"
SNAPSHOT_FILE = "portfolio-activity-snapshot.v1.json"
DEFINITIONS_FILE = "benchmark-definitions.v1.json"
ACCOUNTS = {"isa": "ISA", "taxable": "Taxable", "pension": "Pension"}
LONDON = ZoneInfo("Europe/London")

# Warnings that say nothing about the trades themselves:
# - a stock whose recorded history starts with a sale (bought before the notes begin) is left out of this
#   service's reports, but its trades are real and the export includes them;
# - a stock filed under two tags: a tag groups a stock in reports and is not part of any event.
HARMLESS_WARNINGS = re.compile(r"^Stock \S+ (first transaction is SELL, not BUY/TRANSFER/STOCK_CONVERSION|has no "
                               r"transactions after filtering) - excluding entirely$"
                               r"|^Stock \S+ in \w+ tag changed from '[^']*' to '[^']*' - this may indicate an input error$")


class ExportRefused(Exception):
    """The history cannot be published as complete; `problems` says why."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


# --- canonical forms and identities (investment-analysis SPEC.md §4 E, F) -------------------------------------

def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot_id(snapshot: dict) -> str:
    return sha256(canonical({k: snapshot[k] for k in ("securities", "activities", "tombstones")}))


def definitions_hash(definitions: dict) -> str:
    return sha256(canonical({k: definitions[k] for k in ("broadMarket", "theses")}))


def event_id(account_key: str, security_key: str, trade_date: str, event_type: str, ordinal: int) -> str:
    return sha256(f"{account_key}|{security_key}|{trade_date}|{event_type}|{ordinal}".encode())


def decimal(value: float, places: int) -> str:
    """A float as a decimal string, rounded to `places` and without trailing zeros or an exponent."""
    d = Decimal(repr(float(value))).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)
    text = format(d.normalize(), "f")
    return "0" if text in ("-0", "") else text


# --- building E -----------------------------------------------------------------------------------------------

def _trade_date(txn, where: str, problems: list[str]) -> str | None:
    value = txn.date
    if isinstance(value, datetime):
        if value.time() != time(0, 0):
            # The scan dates an event it found no date for at the moment of the run (portfolio_review.py).
            problems.append(f"{where}: its date was not read from its note")
            return None
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    problems.append(f"{where}: its date {value!r} is not a date")
    return None


def _origin(txn, base_dir: str) -> tuple[str, str | None]:
    """(derivation, sourceRef) for one parsed transaction."""
    def relative(path):
        return os.path.relpath(path, base_dir) if path else None
    if txn.transaction_type == "STOCK_CONVERSION":
        path = txn.origin_file
        return ("manual_entry" if path and path.endswith((".yaml", ".yml")) else "corporate_action_note"), relative(path)
    if txn.transaction_type == "TRANSFER":
        if txn.source_file:
            return "manual_entry", relative(txn.source_file)
        return "inferred_bed_and_isa", None
    if txn.origin_file and not txn.source_file:            # a merger, recorded as a sale for its cash
        return "merger_as_sale", relative(txn.origin_file)
    path = txn.source_file
    return ("manual_entry" if path and path.endswith((".yaml", ".yml")) else "broker_note"), relative(path)


def _activity(note, txn, base_dir: str, problems: list[str]) -> dict | None:
    account = ACCOUNTS[note.category]
    where = f"{account} {note.ticker} {txn.transaction_type} {txn.date}"
    trade_date = _trade_date(txn, where, problems)
    if trade_date is None:
        return None
    derivation, source = _origin(txn, base_dir)
    quantity = abs(txn.quantity)
    if txn.transaction_type in ("BUY", "SELL") and quantity <= 0:
        problems.append(f"{where}: a trade with no units")
        return None
    common = {"accountKey": account, "securityKey": note.ticker, "tradeDate": trade_date,
              "quantity": decimal(quantity, 6), "derivation": derivation, "sourceRef": source}
    if txn.transaction_type == "STOCK_CONVERSION":
        # A ratio, as transaction_processor.py applies it; from 0 units, a share grant.
        if txn.quantity < 0 or not txn.new_quantity or txn.new_quantity <= 0:
            problems.append(f"{where}: a conversion needs a ratio of {txn.quantity} to {txn.new_quantity}")
            return None
        return {**common, "eventType": "conversion", "unitPrice": None, "currency": None, "gbpConsideration": None,
                "conversion": {"newQuantity": decimal(txn.new_quantity, 6),
                               "newSecurityKey": txn.new_ticker if txn.new_ticker and txn.new_ticker != note.ticker else None,
                               "newCurrency": txn.new_currency or None}}
    if txn.transaction_type == "TRANSFER":
        # Units and cost move together; a demerger's apportionment moves cost alone, so its sign decides.
        incoming = txn.quantity > 0 if txn.quantity else txn.total_amount > 0
        event_type = "transfer_in" if incoming else "transfer_out"
        currency = "GBP"                       # moved at its cost, which the scan computes in GBP
    elif txn.transaction_type in ("BUY", "SELL"):
        event_type = txn.transaction_type.lower()
        currency = "GBP" if derivation == "merger_as_sale" else (note.currency or "GBP")
    else:
        problems.append(f"{where}: an event type this export does not know")
        return None
    return {**common, "eventType": event_type, "unitPrice": decimal(abs(txn.price_per_share), 6), "currency": currency,
            "gbpConsideration": decimal(abs(txn.total_amount), 2), "conversion": None}


def _ordered(activities: list[dict]) -> list[dict]:
    """Each event given its eventId, then all in the document's order."""
    groups: dict[tuple, list[dict]] = {}
    for a in activities:
        groups.setdefault((a["accountKey"], a["securityKey"], a["tradeDate"], a["eventType"]), []).append(a)
    for key, group in groups.items():
        group.sort(key=lambda a: (Decimal(a["quantity"]),
                                  (a["gbpConsideration"] is not None, Decimal(a["gbpConsideration"] or 0)),
                                  (a["sourceRef"] is not None, a["sourceRef"] or "")))
        for ordinal, a in enumerate(group, 1):
            a["eventId"] = event_id(*key, ordinal)
    return sorted(activities, key=lambda a: (a["tradeDate"], a["accountKey"], a["securityKey"], a["eventType"], a["eventId"]))


def build_history(review, base_dir: str) -> tuple[list[dict], list[dict]]:
    """(securities, activities) from a scanned PortfolioReview, unrevised. Raises ExportRefused."""
    problems: list[str] = []
    notes = [n for category in ("isa", "taxable", "pension") for n in review.stock_notes[category]]
    notes += getattr(review, "excluded_stock_notes", [])
    activities, securities = [], {}
    for note in notes:
        securities.setdefault(note.ticker, {"securityKey": note.ticker, "yahooSymbol": note.ticker,
                                            "name": note.stock_name or None, "currency": note.currency or None})
        for txn in note.transactions:
            a = _activity(note, txn, base_dir, problems)
            if a is not None:
                activities.append(a)
                new_key = (a["conversion"] or {}).get("newSecurityKey")
                if new_key:
                    securities.setdefault(new_key, {"securityKey": new_key, "yahooSymbol": new_key, "name": None,
                                                    "currency": a["conversion"]["newCurrency"] or note.currency or None})
    if problems:
        raise ExportRefused(problems)
    return sorted(securities.values(), key=lambda s: s["securityKey"]), _ordered(activities)


def revise(activities: list[dict], previous: dict | None, generated_at: str) -> tuple[list[dict], list[dict]]:
    """(activities with their revisions, tombstones), against the last publication (None for the first)."""
    published = {a["eventId"]: a for a in (previous or {}).get("activities", [])}
    buried = {t["eventId"]: t for t in (previous or {}).get("tombstones", [])}
    content = lambda a: {k: v for k, v in a.items() if k not in ("eventId", "revision")}
    revised = []
    for a in activities:
        before = published.get(a["eventId"])
        if before is not None:
            revision = before["revision"] if content(before) == content(a) else before["revision"] + 1
        elif a["eventId"] in buried:
            revision = buried.pop(a["eventId"])["lastRevision"] + 1
        else:
            revision = 1
        revised.append({"eventId": a["eventId"], "revision": revision, **content(a)})
    present = {a["eventId"] for a in activities}
    tombstones = list(buried.values()) + [
        {"eventId": i, "lastRevision": a["revision"], "removedAt": generated_at}
        for i, a in published.items() if i not in present]
    return revised, sorted(tombstones, key=lambda t: (t["removedAt"], t["eventId"]))


def snapshot(securities: list[dict], activities: list[dict], tombstones: list[dict], generated_at: datetime) -> dict:
    doc = {"schemaVersion": 1, "producer": "investment-reviews", "snapshotId": "",
           "generatedAt": generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "asOf": generated_at.astimezone(LONDON).date().isoformat(),
           "scope": {"accountCategories": ["ISA", "Taxable", "Pension"],
                     "historyFrom": min((a["tradeDate"] for a in activities), default=None), "completeness": "complete"},
           "securities": securities, "activities": activities, "tombstones": tombstones}
    doc["snapshotId"] = snapshot_id(doc)
    return doc


# --- building F -----------------------------------------------------------------------------------------------

def definitions(generated_at: datetime, theses_path: Path = THESES) -> dict:
    from periodic_review_processor import BENCHMARKS
    from thesis_config import load_thesis_config
    doc = {"schemaVersion": 1, "producer": "investment-reviews", "definitionsHash": "",
           "generatedAt": generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "broadMarket": [{"tag": tag, "yahooSymbol": symbol, "name": name} for tag, symbol, name in BENCHMARKS],
           "theses": [{"name": t["name"], "candidates": [{"yahooSymbol": c["ticker"], "name": c["name"]} for c in t["candidates"]]}
                      for t in load_thesis_config(str(theses_path))]}
    doc["definitionsHash"] = definitions_hash(doc)
    return doc


# --- checking and publishing ----------------------------------------------------------------------------------

def check(interface: str, doc: dict) -> list[str]:
    """Every problem with `doc`: its schema, then the rules no schema can check."""
    validator = Draft202012Validator(json.loads(SCHEMAS[interface].read_text()),
                                     format_checker=Draft202012Validator.FORMAT_CHECKER)
    problems = [f"{e.json_path}: {e.message}" for e in validator.iter_errors(doc)]
    if problems:
        return problems
    if interface == "BenchmarkDefinitions":
        return [] if doc["definitionsHash"] == definitions_hash(doc) else ["definitionsHash is not the hash of its definitions"]
    ids = [a["eventId"] for a in doc["activities"]]
    keys = {s["securityKey"] for s in doc["securities"]}
    if len(ids) != len(set(ids)):
        problems.append("an eventId appears more than once")
    named = {a["securityKey"] for a in doc["activities"]} | {
        a["conversion"]["newSecurityKey"] for a in doc["activities"] if a["conversion"] and a["conversion"]["newSecurityKey"]}
    if named - keys:
        problems.append(f"securities missing: {sorted(named - keys)}")
    if {t["eventId"] for t in doc["tombstones"]} & set(ids):
        problems.append("a tombstone names a present event")
    if doc["scope"]["historyFrom"] != min((a["tradeDate"] for a in doc["activities"]), default=None):
        problems.append("historyFrom is not the earliest tradeDate")
    if doc["snapshotId"] != snapshot_id(doc):
        problems.append("snapshotId is not the hash of its history")
    return problems


def publish(directory: Path, name: str, doc: dict) -> None:
    """Write `doc` beside its final name, then rename it into place: a reader sees the old file or the new."""
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=f".{name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1, ensure_ascii=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, directory / name)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _previous(directory: Path) -> dict | None:
    """The last publication, which a revision is counted from. One that cannot be read is refused rather than
    treated as none: that would reset every revision and forget every tombstone."""
    path = directory / SNAPSHOT_FILE
    if not path.exists():
        return None
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise ExportRefused([f"the last publication {path} cannot be read: {e}"]) from e
    problems = check("PortfolioActivitySnapshot", doc)
    if problems:
        raise ExportRefused([f"the last publication {path} is invalid: {problems[0]}"])
    return doc


class _Recorder(logging.Handler):
    """The scan's errors, and the warnings not known to be harmless."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.problems: list[str] = []

    def emit(self, record):
        message = record.getMessage()
        if record.levelno >= logging.ERROR or not HARMLESS_WARNINGS.match(message):
            self.problems.append(f"the scan logged {record.levelname}: {message}")


def scan(base_dir: str, note_cache=None):
    """A PortfolioReview of every account, year and tag. Raises ExportRefused if the scan reports a problem."""
    from pdf_parser import NoteParseError
    from portfolio_review import PortfolioReview
    if not os.path.isdir(base_dir):
        raise ExportRefused([f"the notes directory {base_dir} does not exist"])
    recorder = _Recorder()
    root = logging.getLogger()
    root.addHandler(recorder)
    try:
        review = PortfolioReview(base_dir, "full-history", note_cache=note_cache)
    except NoteParseError as e:
        raise ExportRefused([f"a note cannot be read: {e}"]) from e
    finally:
        root.removeHandler(recorder)
    if recorder.problems:
        raise ExportRefused(recorder.problems)
    return review


def run(base_dir: str, export_dir: str, note_cache=None, now: datetime | None = None) -> int:
    """Build, check and publish E and F. 0 when both are published; 1 when either is not, each one's failure
    leaving its last publication in place."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    directory = Path(export_dir)
    failed = False
    try:
        previous = _previous(directory)
        securities, activities = build_history(scan(base_dir, note_cache), base_dir)
        revised, tombstones = revise(activities, previous, now.strftime("%Y-%m-%dT%H:%M:%SZ"))
        # Published every night, changed or not: generatedAt is how a consumer sees the feed is fresh, and an
        # unchanged history keeps its snapshotId.
        doc = snapshot(securities, revised, tombstones, now)
        problems = check("PortfolioActivitySnapshot", doc)
        if problems:
            raise ExportRefused(problems)
        publish(directory, SNAPSHOT_FILE, doc)
        logger.info(f"published {len(doc['activities'])} activities and {len(doc['tombstones'])} tombstones "
                    f"as snapshot {doc['snapshotId'][:12]}")
    except ExportRefused as e:
        failed = True
        for p in e.problems:
            logger.error(f"portfolio activity snapshot not published: {p}")
    try:
        doc = definitions(now)
        problems = check("BenchmarkDefinitions", doc)
        if problems:
            raise ExportRefused(problems)
        publish(directory, DEFINITIONS_FILE, doc)
        logger.info(f"published benchmark definitions {doc['definitionsHash'][:12]}")
    except (ExportRefused, ValueError) as e:
        failed = True
        for p in getattr(e, "problems", [str(e)]):
            logger.error(f"benchmark definitions not published: {p}")
    return 1 if failed else 0
