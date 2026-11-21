# Research Charter C — Comparative Investment Research

**Status:** APPROVED · standard charter accompanying the *Investment Research Programme Brief*
**Version:** v1.1 · 21 November 2026
**Purpose:** Produce a holdings-neutral assessment of prospective investment merit for the alpha class, ranked within each alpha criterion, and, when used for a portfolio review, separately derive **portfolio-aware** recommendations.

## 1. Invocation, inputs and universe

Use for **monthly and annual reviews of the alpha class**, and for substantial ad hoc comparative investigations of individual stocks. The default universe comprises **all currently recorded `candidate` ideas plus current alpha holdings in the review's agreed scope**, in every wrapper including the pension. In-scope holdings remain covered regardless of their prior analysis verdict; admit additional discoveries only through the approved scope-change process.

**Out of scope.** Pure beta and beta plus are not researched under this charter. A beta-plus theme is tested through its written case at the annual review and through Charter D. Thematic funds appear here only as the alternative an alpha stock must beat. A private holding counted as alpha is covered for allocation limits only.

**Monthly:** consume the completed Charter B promotion report (or a recorded statement that no `watch` population exists), latest candidate ResearchBriefs/analyses, the Strategy/theses, and the authoritative `investment-reviews` **Periodic Review** plus previous decisions/proof points.

**Annual:** same method, plus the Operations Brief's broader consolidated performance, asset allocation, cash/tax and fund review. Fund compliance, the pure beta review and the renewal of each beta-plus written case are **not** this charter.

**Ad hoc:** state the exact universe and comparative question; no Periodic Review required unless an actual holdings review/portfolio recommendation is requested.

## 2. Two deliberately separated streams

**Stream 1 — Investment merit, holdings-neutral.** Treat a held security and a newly discovered one as equally eligible. Researchers do **not** score a stock for purchase price, unrealised P&L, position weight or incumbent status. All cases receive a current judgement, though previously verified dossiers may be refreshed rather than rewritten from scratch.

Every case carries one of the Strategy's criteria, set at triage and confirmed or changed here with a recorded reason. The dossier and the test follow the criterion:

| Criterion | Test | Dossier must show |
|---|---|---|
| Mispricing | Does the case beat the broad tracker and the relevant thematic fund on adverse, central and exceptional scenarios? | The verified numbers the price does not reflect; the dated event that settles it; per-share value after dilution |
| Accelerating leader | Same scenario test | Evidence that growth can run faster and longer than a cautious model; what consensus already assumes |
| Disruptive technology | The Strategy's five questions. The central case is not the test | (1) breakthrough or new market; (2) worth on fundamentals if it happens, after dilution, as the floor; (3) likely market reaction to a proof point: stage of the story, scarcity of pure plays, dated legible events, ability to move, history of re-ratings; (4) evidence and dates; (5) exit. Also the case's place in its thesis field map and its nearest rivals |
| None met | — | Why no criterion applies |

**Ranking.** Produce tiers **within each criterion** for the whole universe, with close pairwise comparisons and confidence. Do not merge the criteria into one list: a disruptive-technology case and a mispricing case are not comparable on one scale. A short cross-criterion summary names the leading cases in each, their shared exposures, and any holding with no criterion.

**Stream 2 — Holdings governance, holdings-aware.** Run in parallel under the programme lead using actual `investment-reviews` outputs: previous `New`, `Increased`, `Retained`, `Sold` decision outcomes; current positions; path-to-doubling/profit-taking checkpoints; previous exceptions, dates, pending trades and concentration. Apply the Strategy's exit rule for each holding's class and criterion:

- **Mispricing and accelerating leader:** the price stop by default (review beyond 20% below the absolute 90-day closing high, default exit beyond 30%, with smoothed/P90 context for transient spikes).
- **Disruptive technology:** the moonshot framework. Check each decision point, success criterion and failure evidence; price-only stops are relaxed before the decision point.
- **All alpha holdings:** profit-taking, change in fundamentals, and time held.
- **Recorded exceptions** are honoured and listed.

**Proof-point register.** List every dated proof point attached to a holding or to an unheld `candidate`. Each one whose date has passed gets a pass, fail or recorded extension.

Verify strategy triggers without confusing last-period P&L with lifetime return or the `Sold` counterfactual with actual performance. **Every mandatory holding trigger must reach a documented resolution/escalation**, independently of ranking.

**Integration:** after the independent assessment, apply actual position sizes, wrappers, taxes, liquidity, correlations, investment constraints and switching costs. Check the Strategy's limits: alpha as a share of the portfolio; disruptive-technology positions as a share of alpha; beta plus and alpha together; the stake guide; and the tax strategy's mapping of classes to wrappers. A holding with no criterion must, under the Strategy, qualify, join a basket or be sold. State separately investment merit and whether to buy, add, retain, reduce, rotate or take no action. A better-ranking investment does not mechanically force rotation when switching cost offsets the benefit.

## 3. Research procedure and parallel assignments

1. **Normalise:** reconcile candidate/holding coverage and genuine issuer/security IDs; preserve multiple distinct idea histories; group by economically meaningful peer set and common factor. Confirm each case's criterion and originating thesis.
2. **Share research:** prepare reusable sector context, reusing the Charter D field map where one exists, then a substantive company dossier per case built to its criterion's test.
3. **Challenge:** separate researchers test the assumptions, adverse cases, strongest rival instruments and alternate technologies. For a disruptive-technology case the challenger tests the five answers, especially who else could capture the value. Record objections and disposition, not merely a confidence number.
4. **Compare within sectors:** use consistent assumptions and explicit pairwise choices, with ties and incomparability where evidence is limited.
5. **Calibrate within each criterion:** produce holdings-neutral tiers per criterion covering the whole universe; identify factor overlap and, for mispricing and accelerating-leader cases, the leading alternatives against broad-market and relevant thematic options. Shortlist only for intensive *additional* research where it can change choices; no predetermined winner quota.
6. **Discover:** at sector and cross-sector checkpoints, log stronger competitors or adjacent opportunities. A comparator is not automatically an official idea; recommend admission to the user where justified; use the Operations Brief `IdeaSubmission` approval/ingestion path. A cluster of discoveries that suggests a new thesis is referred to Charter D.
7. **Focus and integrate:** deepen the highest-value unresolved questions, then combine with holdings governance to prepare practical allocation proposals. Retain conditional positions only with appropriately dated proof; do not assume buying is required to fill an allocation budget.

## 4. Gates and outputs

**Coverage gate:** every in-scope candidate and holding is researched/reassessed or visibly blocked. No winner-only reporting.
**Criterion gate:** every case has a criterion or "none met"; every change of criterion is recorded with its reason.
**Challenge gate:** every material leading case receives a genuine independent challenge and strongest-alternative comparison.
**Calibration gate:** the per-criterion tiering is explainable and not the average of incompatible subagent scores.
**Portfolio gate (reviews only):** the Periodic/Annual Review outcome discussion, **all mandatory holdings triggers** and all due proof points are addressed; actual allocation proposals are separate from ranking.
**Record gate:** only concluded new research judgements produce official, dated, superseding `AnalysisRecord`s; no trade YAML before explicit agreement.

**Verdict conventions.** A researched idea awaiting a dated proof point before any purchase is `candidate` with the proof point recorded. When the proof point passes it may become `select`; when it fails, `reject`. Every record fills `criterion`, `criterionRationale`, `thesis` and, for a disruptive-technology case, `fiveQuestions`, as defined in `analysis-record.v1.schema.json` and required by Charter A.

Produce: (a) full issuer/idea research register; (b) shared sector notes and individual dossiers; (c) independent challenges and peer rankings; (d) per-criterion tiers for the whole universe with research-confidence/gap fields, and the cross-criterion summary; (e) Discovery Register and admission proposals; (f) a **separate** holdings-trigger closure sheet, proof-point register and portfolio-aware allocation recommendations when applicable; (g) decision-ready deep dossiers for leading cases; (h) appropriate schema-validated research records and import manifests; (i) the monthly/annual discussion outputs required by the *Investment Operations Brief*, including holds and no-action conclusions.

## 5. Working principles and exceptions

Investment criteria are exclusively those of the current Strategy; no separate numeric score or hidden return hurdle. Initial candidate or holding status does not pre-ordain the result. Source disagreements, currency/share-count conflicts, stale filings and speculative probabilities must remain visible. Use a common price/FX cut-off where possible, distinguish sector-specific valuation methods, and avoid confusing thematic enthusiasm with company-specific shareholder alpha. Portfolio-aware output can disagree with the merits tiers; **explain why**.

**Run-manifest minimum:** charter C/version, review type (monthly/annual/ad hoc), candidate snapshot, holdings scope and authoritative report versions, dated metrics/cut-off, baseline analyses, exclusions, permissions, research-package plan, agreed gates and scope amendments.

## Changes from v1.0

1. Scope limited to the alpha class, in every wrapper; thematic funds are comparators only; beta plus moves to the annual review and Charter D.
2. Each case carries a criterion; dossier and test follow it; disruptive-technology cases are judged on the five questions.
3. Ranking is by tiers within each criterion, with a cross-criterion summary, in place of one all-universe list.
4. Holdings governance applies exits by class and criterion; low-volatility check removed; recorded exceptions listed.
5. New proof-point register covering holdings and unheld candidates.
6. Integration checks the Strategy's class limits, stake guide and tax strategy.
7. New criterion gate; verdict convention for candidates awaiting a proof point.
