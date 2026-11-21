# Research Charter A — Discovery Triage

**Status:** APPROVED · standard charter accompanying the *Investment Research Programme Brief*
**Version:** v1.1 · 21 November 2026
**Purpose:** Efficient, defensible first-pass triage of newly received ideas for the alpha class.

## 1. Invocation and universe

This charter applies to ideas for individual stocks that might qualify for the **alpha class** of the current Investment Strategy. Funds, beta-plus themes and stocks chosen for a beta-plus basket are out of scope: they are handled by the annual review and by Charter D.

Invoke for an incoming batch of internal or external ideas, including ranked lists, screeners, manually agreed discoveries and admission batches arising from a Charter D thesis run. The universe is **all idea IDs in the approved batch**, not a handpicked set of attractive companies. Preserve duplicates as distinct propositions, but investigate common issuers once where possible. An ordinary single ad hoc idea may instead use the Operations Brief directly.

Default inputs: the actual `ResearchBrief` exports and applicable schemas; any known prior analysis history; current Strategy, Operations Brief and Programme Brief; source provenance; for a thesis-derived idea, the thesis it came from and that thesis's field map. Capture archive checksum, idea IDs, source dates, latest reviewed brief ID/version and unresolved identities. No current portfolio or cost-basis details are normally required.

## 2. Research procedure

1. **Validate intake:** reconcile all idea IDs, security and listing IDs, sources, duplicate issuers and differing hypotheses. Verify that source categories (ranked-list mention, screener entry, explicit recommendation, internal thesis) remain distinct. Record each idea's discovery channel and, where there is one, its originating thesis.
2. **Assign a criterion.** For each idea, state which of the Strategy's three alpha criteria its claimed source of exceptional return falls under: **mispricing**, **accelerating leader** or **disruptive technology**; or **none met**. Decide this from the claim, not from the channel: a thesis-derived idea can be an accelerating leader, and a screener idea can be a disruptive-technology case. The assignment is provisional and may be changed later with a recorded reason.
3. **Group work:** group by sector/peer where useful, usually in small packets. Do not let list ranking or screener score substitute for independent judgement.
4. **Triage at proportional depth, using the test for the idea's criterion:**
   - **Mispricing.** Which verified numbers does the price not reflect, and is there a dated event that will settle it? Make a first-pass comparison with the broad tracker and the relevant thematic fund.
   - **Accelerating leader.** What evidence shows growth can run faster and for longer than a cautious model allows (orders, backlog, capacity, share gains), and how much of it is already in consensus? Same first-pass comparison with tracker and fund.
   - **Disruptive technology.** Do not judge on the central case. Apply a light version of the Strategy's five questions: (1) is there a named breakthrough or new market; (3) where is the story (before or after the crowd) and how scarce are pure plays; (4) is there a dated proof point, normally within twelve months. Note (2), whether funding plausibly reaches that proof point without ruinous dilution, and (5), the exit; neither is a gate at triage.
   - **None met.** A sound company that only expresses a theme, with no company-specific source of exceptional return, fails the Strategy's definition of alpha.

   Seek targeted independent verification where decisive, especially before a substantive `reject`.
5. **Calibrate:** compare borderline verdicts across packets within the same criterion; challenge optimistic source claims and unsupported rejections; keep research effort proportionate to the decision being made.
6. **Conclude:** issue an evidence-backed verdict per idea, or explicitly flag a blocked/incomplete case. Do not manufacture a conclusion to satisfy a record-count target.

## 3. Verdict contract

- `candidate`: passes the triage test for its criterion and merits substantive independent research under Charter C; not yet selected for purchase.
- `watch`: potentially worthwhile under its criterion but no reason to prioritise full investigation now; record **why it is deferred** and, where possible, the specific evidence/price/catalyst that could requalify it. Charter B re-checks it.
- `reject`: considered, identifiable investment opportunity with a **substantive documented negative investment rationale**; mere missing evidence or failure to identify immediate upside does not automatically suffice. "No alpha criterion met; the exposure is available through a fund" is a substantive rationale when the triage shows it.
- `not_relevant`: outside mandate or not practically investable (including a listing on a market the sponsor cannot trade); it is **not** a poor-return forecast.

**Convention for ideas awaiting evidence.** `watch` means *not yet worth researching*. An idea that has been researched and is waiting only for a dated proof point before any purchase is a `candidate` with that proof point recorded; Charter C re-checks it each month.

**Recording criterion and thesis.** Every record issued under this charter fills the following fields of `analysis-record.v1.schema.json`:

- `criterion`: `mispricing`, `accelerating_leader`, `disruptive_technology` or `none_met`;
- `criterionRationale`: one line saying why that criterion applies, or why none does;
- `thesis`: the name of the originating thesis as it appears in `thesis.json`, or `null`;
- `fiveQuestions`: for a disruptive-technology idea, the answers reached at triage depth; otherwise `null`.

The schema leaves these fields optional so that records made before 21 November 2026 remain valid; this charter makes them mandatory for new records. The discovery channel is not repeated on the record: it is carried by the idea's `origin` and `discoveryEventType`. A thesis-derived idea names its thesis in `origin.thesisRef` of `idea-submission.v1.schema.json`; the record's `thesis` repeats that name, and differs from it only where an idea from another channel is attributed to a thesis at analysis.

These are precisely the `AnalysisRecord.v1` meanings; use its other verdict values only where truly applicable. A source mention does not imply the source advocated a buy. Do not set quotas for positive or negative verdicts.

## 4. Gates and outputs

**Coverage gate:** every input idea appears in the register and is either concluded or explicitly blocked.
**Criterion gate:** every concluded idea has a criterion, or "none met", with one line of reasoning.
**Calibration gate:** material `reject` and borderline `candidate` cases receive a contrary check; no unsupported translation of source hype into fact.
**Record gate:** all concluded analyses use actual IDs, actual analysis dates and correct previous-analysis supersession; schema checks and import preview occur before entry to the live ledger.

Produce: (a) complete triage coverage table; (b) verdict counts and reason summaries, broken out by discovery channel, by criterion and by thesis; (c) unresolved identities and information gaps; (d) candidate research priorities, watch triggers and any proposed new discoveries; (e) one validated `AnalysisRecord.v1` per concluded idea, suitable for supported bulk import. A light first-pass record may legitimately leave valuation and scenario fields null/empty if not assessed, with that limitation in `rationaleMarkdown`.

## 5. Success measures and boundaries

Review the candidate yield, reasoned rejection yield, discovery-source duplication, time/attention cost, disagreement and subsequent observed outcomes, each by channel, criterion and thesis, not merely how many ideas were accepted. Do not treat `candidate` as a buy recommendation or claim completed import without ledger confirmation. Portfolio allocation and comparative ranking are Charter C responsibilities.

**Run-manifest minimum:** charter A/version, batch ID, source files/hashes, idea count, evidence cut-off, any exclusions or missing briefs, actual record-chain availability, originating thesis and Charter D run where applicable, and agreed exceptions.

## Changes from v1.0

1. Scope limited to ideas for the alpha class.
2. New step: assign one of the Strategy's three criteria (or "none met") before triage.
3. Triage test now depends on the criterion; disruptive-technology ideas are screened on the five questions, not the central case.
4. `reject` may rest on "no alpha criterion met"; `not_relevant` covers untradeable listings.
5. Convention separating `watch` (not yet researched) from `candidate` with a dated proof point (researched, awaiting evidence).
6. Criterion, its rationale, the originating thesis and the five-question answers recorded in new fields of the analysis-record schema; the idea submission's existing `origin.thesisRef` holds the thesis name.
7. Outputs and success measures reported by criterion and thesis as well as channel.
