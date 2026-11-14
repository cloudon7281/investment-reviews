# Research Charter A — Discovery Triage

**Status:** Standard charter, accompanying *Investment Research Programme Brief* v1.0  
**Version:** v1.0 · 14 November 2026  
**Purpose:** Efficient, defensible first-pass triage of newly received investment ideas.

## 1. Invocation and universe

Invoke for an incoming batch of internal or external ideas, including ranked lists, screeners and manually agreed discoveries. The universe is **all idea IDs in the approved batch**, not a handpicked set of attractive companies. Preserve duplicates as distinct propositions, but investigate common issuers once where possible. An ordinary single ad hoc idea may instead use the Operations Brief directly.

Default inputs: the actual `ResearchBrief` exports and applicable schemas; any known prior analysis history; current Strategy, Operations Brief and Programme Brief; source provenance. Capture archive checksum, idea IDs, source dates, latest reviewed brief ID/version and unresolved identities. No current portfolio or cost-basis details are normally required.

## 2. Research procedure

1. **Validate intake:** reconcile all idea IDs, security and listing IDs, sources, duplicate issuers and differing hypotheses. Verify that source categories (ranked-list mention, screener entry, explicit recommendation, internal thesis) remain distinct.
2. **Group work:** group by sector/peer where useful, usually in small packets. Do not let list ranking or screener score substitute for independent judgement.
3. **Triage at proportional depth:** review the company's economics, most material available financial evidence, investability, investment proposition and obvious risks. Seek targeted independent verification where decisive, especially before a substantive `reject`.
4. **Calibrate:** compare borderline verdicts across packets; challenge optimistic source claims and unsupported rejections; keep research effort proportionate to the decision being made.
5. **Conclude:** issue an evidence-backed verdict per idea, or explicitly flag a blocked/incomplete case. Do not manufacture a conclusion to satisfy a record-count target.

## 3. Verdict contract

- `candidate`: merits substantive independent research, not yet selected for purchase.
- `watch`: potentially worthwhile but no reason to prioritise full investigation now; record **why it is deferred** and, where possible, the specific evidence/price/catalyst that could requalify it.
- `reject`: considered, identifiable investment opportunity with a **substantive documented negative investment rationale**; mere missing evidence or failure to identify immediate upside does not automatically suffice.
- `not_relevant`: outside mandate or not practically investable; it is **not** a poor-return forecast.

These are precisely the `AnalysisRecord.v1` meanings; use its other verdict values only where truly applicable. A source mention does not imply the source advocated a buy. Do not set quotas for positive or negative verdicts.

## 4. Gates and outputs

**Coverage gate:** every input idea appears in the register and is either concluded or explicitly blocked.  
**Calibration gate:** material `reject` and borderline `candidate` cases receive a contrary check; no unsupported translation of source hype into fact.  
**Record gate:** all concluded analyses use actual IDs, actual analysis dates and correct previous-analysis supersession; schema checks and import preview occur before entry to the live ledger.

Produce: (a) complete triage coverage table; (b) verdict counts and reason summaries, broken out by discovery channel; (c) unresolved identities and information gaps; (d) candidate research priorities, watch triggers and any proposed new discoveries; (e) one validated `AnalysisRecord.v1` per concluded idea, suitable for supported bulk import. A light first-pass record may legitimately leave valuation and scenario fields null/empty if not assessed, with that limitation in `rationaleMarkdown`.

## 5. Success measures and boundaries

Review the candidate yield, reasoned rejection yield, discovery-source duplication, time/attention cost, disagreement and subsequent observed outcomes—not merely how many ideas were accepted. Do not treat `candidate` as a buy recommendation or claim completed import without ledger confirmation. Portfolio allocation and full cross-sector ranking are Charter C responsibilities.

**Run-manifest minimum:** charter A/version, batch ID, source files/hashes, idea count, evidence cut-off, any exclusions or missing briefs, actual record-chain availability and agreed exceptions.
