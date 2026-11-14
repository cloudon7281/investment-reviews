# Research Charter B — Watch Requalification

**Status:** Standard charter, accompanying *Investment Research Programme Brief* v1.0  
**Version:** v1.0 · 14 November 2026  
**Purpose:** Decide which previously deferred ideas have **materially improved** and now deserve substantive independent research.

## 1. Invocation and universe

Run **before each monthly review** (or earlier on a significant event). Freeze a snapshot of **every idea whose latest official research verdict is `watch`**. Include source-specific duplicate ideas; share issuer observations but assess requalification against each idea's original proposition and documented reason for waiting. Record the last completed watch-check date, and treat never-checked or stale cases as distinct coverage states.

Inputs: watch-universe export with genuine idea/brief/analysis identifiers; latest `watch` rationale, available proof points, prior monthly check record, new briefs/observations and material news. Use current Strategy and existing canonical schemas. Do not infer a complete watch universe from an old archive if the live app state was not checked; mark the coverage limit.

## 2. Change-detection procedure

1. **Coverage and baseline:** enumerate all current watch ideas and identify the preceding comparison date/brief. Read the **specific reason for deferral**; if absent, mark the monitorability gap instead of inventing a past trigger.
2. **Efficient screening:** inspect new price/valuation changes, results, filings, funding/dilution, contracts, approvals, competitive evidence, and dated proof events. Share data by issuer; use targeted external research only for plausible material changes.
3. **Requalification test:** ask whether the new evidence has addressed the reason to wait **strongly enough to justify independent deep research now**. A cheaper price with the same business prospects can qualify; generic positive news does not automatically qualify.
4. **Challenge promotions:** verify material factual claims and assess whether apparent improvement is offset by changed financing, dilution or market expectations. Rank proposed promotions by research urgency if capacity is constrained, without inventing an admission quota.
5. **Hand off:** for each actual promotion, create a new `candidate` `AnalysisRecord.v1` superseding the latest `watch` analysis, citing the brief genuinely reviewed. The newly promoted idea enters the subsequent Charter C candidate universe once its record is accepted, or is separately flagged as pending import.

## 3. Deliberately narrow verdict policy

- **Promote to `candidate`:** material favourable change sufficient to warrant research, not automatically a buy or `select`.
- **No material change:** retain the existing `watch` analysis; **do not create a redundant watch-to-watch record**. Record only a check outcome in the programme coverage log.
- **Ambiguous evidence / unavailable data:** mark `needs_review` or `unverified` in the coverage report; no fabricated promotion.
- **Material negative change:** flag for separately authorised targeted triage/reassessment. This routine charter does not mass-convert `watch` to `reject` or hide material adverse developments.

The programme coverage report is an **internal operational record**, not an `AnalysisRecord` or a new `investment-analysis` object contract.

## 4. Gates and outputs

**Population gate:** every current watch idea counted once, including cases not refreshed or blocked.  
**Materiality gate:** every proposed promotion cites what changed, when it became known, how it bears on the earlier deferral, and the remaining reason not to research.  
**Import gate:** new analysis UUID, unique judgement date/time per record, exact idea/brief IDs and latest-analysis supersession; JSON/schema and live-ledger preview.

Produce: (a) complete watch-check register with no-change, promoted, blocked and negative-change flags; (b) concise **promotions report** with what changed and the reason for new research priority; (c) importable `candidate` records **only for actual promotions**; (d) any proposed ad hoc triage or new-idea discoveries; (e) source coverage/date/quality limitations.

## 5. Relation to periodic reviews

Complete the check before the monthly Charter C universe is frozen, so the default Charter C universe is simple: **current candidates plus in-scope holdings**. If watch requalification was unavailable or incomplete, disclose this to the monthly review; do not silently infer no promotions. The `investment-reviews` Periodic Review remains a separate mandatory portfolio-performance input to that review, not a substitute for watch requalification.

**Run-manifest minimum:** charter B/version, snapshot date and watch population/export hash, preceding check date, baseline analysis references, evidence date, unresolved coverage and changed-record import status.
