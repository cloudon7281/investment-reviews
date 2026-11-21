# Research Charter D — Thesis Development and Review

**Status:** APPROVED · standard charter accompanying the *Investment Research Programme Brief*
**Version:** v1.0 · 21 November 2026
**Purpose:** Propose, test, classify and adopt or reject investment theses; map the field of a discovery thesis and set its benchmark; hand its ideas to Charter A; and review or retire theses over time.

A thesis is a belief about a market or technology. It is not an idea and not a verdict. This charter produces thesis decisions, field maps, benchmarks and admission proposals. It never produces an `AnalysisRecord` and never authorises a trade.

## 1. Invocation and universe

Invoke when:

- the sponsor or the programme lead proposes a new thesis or sub-thesis;
- several Discovery Register entries cluster around a subject no thesis covers;
- an adopted thesis is due its periodic review (normally quarterly), or an event bears on one of its falsifiers.

The universe is the thesis itself and, for a discovery thesis, its field: every listed company the sponsor can trade that is a pure or near-pure expression of it, with private and untradeable companies noted as context.

Default inputs: the current Strategy; `thesis.md` and `thesis.json`; the Discovery Register; evaluation reports where a thesis already has history. No holdings, entry prices or position sizes are needed, and none are given to delegated workers.

## 2. Procedure for a new thesis

1. **State.** Record the thesis in the sponsor's own words: the claim, the mechanism, why now, and its boundaries. Split it into sub-theses where parts could be true independently.
2. **Critique.** Give the statement a genuine independent challenge. Cover at least:
   - the evidence for and against, with dates, and how old the evidence is relative to the technology it measures;
   - whether the claim is already consensus, and what a holder would have to believe that the market does not;
   - where the real bottleneck sits and who owns the scarce complement (data, plant, regulatory standing, customers);
   - who else captures the value: incumbents, suppliers, platform or model owners;
   - what fixes the pace: a regulator's mandated process, a customer's qualification, or manufacturing scale-up.

   Record the sponsor's rebuttals and what changed. Finish with a **restated thesis** that both sides accept as the version being tested. If the critique shows that the thesis does not stand, the sponsor may **reject the entire thesis** at this point; record the reason and stop.
3. **Classify each sub-thesis** using the Strategy's two kinds:
   - **Allocation thesis:** a market expected to grow by more than is priced in, where broad exposure is wanted. Test: *would I own this theme's index if I could not pick stocks?* An allocation thesis leaves this charter here and goes to the Strategy's beta-plus written case and the annual review. Its benchmark is the index of the fund named in that written case or, where there is no suitable fund, a stock list drawn up as in step 4.
   - **Discovery thesis:** ground likely to produce individual winners. Continue to step 4.
   - A sub-thesis may be both. One that is neither is rejected.
4. **Map the field (discovery sub-theses).** Before adoption, list the whole tradeable field, not a favoured few. For each company record: what it does and how purely it expresses the thesis; listing and whether the sponsor can trade it; size; its place in the value chain; and a first guess at its alpha criterion. Note the private and untradeable leaders so the map shows what is missing. Cite sources and date the map. Screening notes are allowed; verdicts are not.

   From the map, propose the thesis **benchmark**: the list of tradeable stocks that most purely express the sub-thesis. Choose them for purity, not for expected upside, and include them whether or not the sponsor holds them. The benchmark is the yardstick against which stocks later picked under the thesis are compared; it is not a buy list.
5. **Investability gate.** Ask whether the map contains enough tradeable companies, close enough to the thesis, to justify the attention. A thesis can be right and still not investable.
6. **Decide.** The sponsor decides for the thesis as a whole and for each sub-thesis:
   - **Adopt**, with falsifiers, dated leading indicators, a review date and the agreed benchmark list recorded;
   - **Park**, with the event that would reopen it (for example a private leader listing);
   - **Reject**, with the reason. The outcome may be to **reject the entire thesis**, not only a sub-thesis.
7. **Hand off.** For an adopted discovery thesis, enter the mapped names in the Discovery Register and propose admissions. The sponsor agrees each admission under Operations Brief §3.1. Agreed names become an `IdeaSubmission.v1` batch (`origin.kind=internal`, `discoveryEventType=internal_thesis`, `thesis` set to the thesis name, accurate proposer attribution, duplicate check stated) and enter **Charter A**. Names not admitted stay on the register as comparators.
8. **Record.** Propose the updates to the thesis documents: thesis identifier, statement, kind per sub-thesis, status, date and version, falsifiers, leading indicators, review date, a reference to the field map, and the **benchmark**: the dated list of stocks agreed at step 6, recorded as that thesis's `candidates` in `thesis.json`. A proposed change is not effective until the sponsor agrees it.

## 3. Procedure for a periodic review

For each adopted thesis:

1. Check every falsifier and dated leading indicator; record pass, fail or not yet due.
2. Refresh the field map and the benchmark: new listings, delistings, acquisitions, private leaders that have become tradeable. Record each change to the benchmark with its date; do not rewrite its history.
3. Report the yield: names mapped, ideas admitted, candidates, stakes taken, and outcomes so far, by criterion.
4. Recommend **retain**, **amend**, **reclassify** (allocation to discovery or the reverse), **park** or **retire**.

Retiring or amending a thesis does not change any verdict. Ideas that depended on it are flagged for the next Charter C run. For an allocation thesis, the periodic check of its written case belongs to the annual review; this charter only records whether the thesis itself still stands.

## 4. Gates

**Statement gate:** the thesis is written down in the sponsor's words before any critique.
**Challenge gate:** the critique covers the five points in step 2 and the restated thesis is agreed.
**Classification gate:** every sub-thesis has a kind.
**Map gate:** the field map covers the tradeable field, names what is not tradeable, and is dated and sourced; the proposed benchmark is drawn from it.
**Sponsor gate:** adopt, park or reject, for the whole thesis or a sub-thesis, is the sponsor's decision, as are the benchmark list and each admission.
**Boundary gate:** no `AnalysisRecord`, no verdict language and no purchase proposal has been produced for an unregistered name.

## 5. Outputs

(a) Thesis statement, critique and restated thesis; (b) classification per sub-thesis; (c) dated field map; (d) the decision, which may be the rejection of the entire thesis, with falsifiers, indicators and review date where adopted; (e) for each adopted sub-thesis, the benchmark: the list of stocks that comprise it; (f) Discovery Register entries and admission proposals; (g) the agreed `IdeaSubmission.v1` batch for Charter A; (h) proposed thesis-document updates, including the benchmark; (i) for reviews, the indicator check, refreshed map and benchmark, yield report and recommendation.

## 6. Boundaries

- Exploratory work on a single company during a thesis run is a field-map note. It has no official status until the company is admitted and passes through Charter A.
- This charter does not select funds or write the beta-plus case; it only classifies a thesis as an allocation thesis and hands it over.
- It does not change the Strategy's criteria.

**Run-manifest minimum:** charter D/version; thesis identifier and whether new or under review; initiator; evidence cut-off; sources and permissions; markets the sponsor cannot trade; work-package plan including the independent challenger; agreed exceptions.
