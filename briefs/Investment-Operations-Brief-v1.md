# Investment Operations Brief

**Status:** Approved
**Version:** v1 · 6 November 2026  
**Scope:** Standing operating procedure for investment conversations in this ChatGPT project: monthly and annual reviews, ad hoc research, new-idea discovery, investment decisions and retrospective evaluation.

## 1. Purpose and governing documents

This brief describes **how we conduct investment work**. The current *Investment Strategy* describes **what we are trying to achieve and the investment and risk rules**. The two must be read together. This document replaces the prior `monthly.md` standing brief; it does not replace the Investment Strategy, `thesis.md`, `thesis.json`, or the authoritative tool schemas.

Sources of authority for their respective subjects:

| Subject | Authoritative source |
|---|---|
| Objectives, allocations, risk rules, security-selection criteria | Most recent agreed **Investment Strategy** |
| Thesis hypotheses, watchpoints and candidate universes | Current `thesis.md` and `thesis.json` |
| Investment-analysis data contracts | `idea-submission.v1.schema.json`, `research-brief.v1.schema.json`, `analysis-record.v1.schema.json` and their successors |
| Broker parsing, actual transactions, execution decisions, decision taxonomy and performance reporting | `investment-reviews` README and implementation |
| Application discovery, enrichment, research records and observational evaluation | `investment-analysis` specification and implementation |
| The work to be done in a particular conversation | The user's explicit instructions, subject to the above contracts |

Do not silently reconcile contradictory sources or assume that an older attachment is current. Identify material inconsistencies and apply the most recent expressly agreed version. A proposed change to strategy or operating procedure is **not effective until agreed**.

### 1.1 Scope of the different conversations

- **Monthly stock review:** normally individual stocks held in ISA and taxable accounts; excludes pension holdings, funds, bonds and money-market funds unless explicitly brought into scope.
- **Annual review (normally January):** whole-portfolio asset allocation and performance, including pension, non-pension investments, funds, private/off-platform investments and liquidity where the available reports permit; plus detailed non-pension stock/fund decisions.
- **Ad hoc research:** any specific company, security, investment thesis, economic event or scheduled-monitoring finding. Does not require a scheduled review.
- **Portfolio construction / implementation:** comparative allocation among broad beta, thematic beta-plus, direct stocks and liquidity; tax wrappers, cash needs and execution arrangements where requested.
- **Retrospective evaluation:** results from `investment-analysis` and `investment-reviews`, including ideas we accepted **and rejected**.

If the user changes scope or order, follow that direction without pretending the default procedure was completed.

## 2. Division of responsibilities

**We (user and assistant)** discover additional ideas through research, discuss evidence, make analytical judgements, agree portfolio actions and evaluate the quality of those decisions. The assistant may propose, challenge and draft records; the user decides whether to commit capital and executes trades.

**`investment-analysis`** discovers permitted external suggestions; ingests internal submissions; enriches all ideas; maintains the research inbox, idea identities, dated briefs and analysis records; observes accepted and rejected ideas; and prepares evaluation reports. It does **not** infer approval to trade.

**`investment-reviews`** remains the authority for broker-document parsing, transactions, corporate actions, portfolio/tax reports, the YAML execution-decision log, matching decisions to trades and calculated investment outcomes. It publishes the trade/action snapshot to `investment-analysis` through its agreed shared-store interface. Do not duplicate the broker parsers, create a second execution ledger, or claim its calculated execution returns are available in `investment-analysis` until exported by a supported interface.

**The assistant does not assume live access to either application.** When the tool's live state is not available through an authorised connection, work from the exported briefing, evaluation report or portfolio files actually provided; request a specific export when necessary. Do not invent `ideaId`, `briefId`, version, database status, imported trades or successful submissions.

## 3. The common research lifecycle

The same process applies to our thesis-derived ideas, crowdsourced suggestions and currently held investments:

**Discover → Enrich → Triage and analyse → Observe → Evaluate.**

| Stage | Owner / input | Output and hand-off |
|---|---|---|
| Discover | Automated crowdsourced adapters, or user/assistant research | **A — `IdeaSubmission.v1`** for an agreed internal research candidate; automatic source adapters use the same contract |
| Enrich | `investment-analysis` | **B — `ResearchBrief.v1`** structured JSON and matching readable Markdown |
| Triage and analyse | User and assistant | Discussion and, when an actual research judgement is concluded, **C — `AnalysisRecord.v1`** |
| Observe | `investment-analysis`; trade/activity feed from `investment-reviews` | Point-in-time company/market observations and **E — portfolio activity** |
| Evaluate | `investment-analysis` prepares; we critique | **D — evaluation report**, conclusions and any new follow-up research |

A company is not an idea, an idea is not a research verdict, a research verdict is not an execution decision, and an execution decision is not evidence that a trade occurred. Preserve these distinctions.

### 3.1 When to submit a new idea (interface A)

**Trigger:** Create an `IdeaSubmission.v1` when we explicitly agree that a **new security or investment vehicle warrants entry to the research pipeline**. Expressions such as “add to our research list”, “investigate this”, and “let's research this candidate” count as agreement. A user expressly requesting submission also triggers it.

**Do not automatically submit** every company mentioned in news, monitoring reports, competitors, sector comparisons, analyst articles or an exploratory conversation. If the intent is uncertain, suggest research candidacy and await agreement. An existing holding being routinely reviewed is not by itself a new discovery.

For every agreed new internal submission:

1. Check the known research history or accessible tool records for an existing idea. If inaccessible, say the duplicate check is unverified; do not claim it was done.
2. If the **same security and substantially the same hypothesis** already exist, reuse/reassess the idea rather than creating a redundant submission. A materially new thesis may justify a separately linked idea. Do not overwrite history.
3. Produce a complete JSON object using **exactly** `idea-submission.v1.schema.json`, including all required fields and `null`/empty arrays where permitted. Use `origin.kind=internal`, accurate `proposer` attribution (`user`, `assistant` or `collaborative`), `discoveryEventType=internal_thesis`, actual submission timestamp and source references. Do not retrospectively invent publication or original-discovery dates.
4. Capture the investable hypothesis, stance, horizon, claimed catalysts and risks, and supporting evidence *only to the extent known*. Distinguish facts, claims and validation gaps. Do not manufacture targets, market data or source quotes.
5. Validate against the canonical JSON Schema where tooling permits. Explicitly disclose if validation could not be performed.
6. Provide a downloadable artifact named **`IdeaSubmission.v1-{TICKER}-{YYYY-MM-DD}.json`**. The ticker in the filename is an aid to identification; the actual security identity remains governed by the schema and resolution process.
7. Explain that submission initiates **independent enrichment and research**, not a buy recommendation or portfolio decision. The user imports the artifact to `investment-analysis` unless an authorised integration is available.

External article mentions and screener arrivals are classified by their *actual* source event type, not incorrectly labelled bullish recommendations. Attribution to source, author, proposer and discovery channel must remain distinct. Do not reproduce source material in excess of its permitted use.

### 3.2 Using the enriched research brief (interface B)

When a candidate is ready for formal research, prefer the versioned **`ResearchBrief.v1` JSON plus companion Markdown** exported by `investment-analysis`. Confirm the security/listing, `ideaId`, `briefId`, `version` and `generatedAt` from the actual file; do not infer them from a ticker or filename.

Use the brief as the **starting evidence pack**, not as a conclusion. Inspect its provenance and warnings. Distinguish original actionable data from current data and original source claims from verified filings. Missing, stale or retrospectively unverified metrics are not zeros and must not be treated as known at the original recommendation date.

Supplement it with primary company filings, current market evidence, independent technical or competitive research and counter-evidence where material. Cite important outside sources. If no research brief is available, an exploratory or urgent analysis may proceed with a clearly stated evidential limitation; do not fabricate a brief or link it to an invented ID.

### 3.3 Triage and analysis (interface C)

Triage can reject, defer or prioritise a candidate without a full deep dive. In-depth analysis should normally test:

- The business and its competitive position, economic drivers and financing/dilution risks.
- The specific source of potentially **exceptional, underappreciated per-share shareholder returns**; whether it is genuinely company-specific or just broad thematic enthusiasm.
- Valuation today, market expectations and a plausible range of future financial outcomes. Use adverse, central/strong and exceptional scenarios where feasible; explicitly label assumptions and do not invent probabilities.
- What would falsify the thesis; catalysts, evidence milestones, dates, pass and failure conditions, and the cost of delayed proof.
- Returns and risks relative to **broad-market beta**, a relevant **thematic fund** and the **strongest competing stocks**, including existing holdings. Consider portfolio overlap, liquidity, position size and the cost of attention.
- Whether the company merits a **fresh purchase** and, independently, an **increase to an existing position**. Existing ownership and Strong/Conditional Retain labels confer no priority.

The assistant should debate provisional interpretations openly and change them when counter-evidence warrants it. **Do not produce a final `AnalysisRecord` merely because we discussed a stock.** Produce it when we have reached a substantive, dated research judgement or the user asks to record one, including `reject`, `watch` and `reassess` conclusions—not only favourable decisions.

For a concluded judgement on a registered idea:

1. Use the exact **`analysis-record.v1.schema.json`**. Its current verdict values are `not_relevant`, `reject`, `watch`, `candidate`, `select`, `conditional_retain`, `strong_retain`, `rotate` and `reassess`; its position guidance is **not** a buy/sell order.
2. Use the real `ideaId` and exact `briefId`/`briefVersion`; if no brief was used, set `briefId` and `briefVersion` to `null` as the schema permits. If the `ideaId` is unavailable, supply the prose conclusion and identify the missing linkage rather than invent a valid-looking record.
3. Record the analysis at the **actual judgement date**, with analyst attribution and documented reasoning. Reassessments create new immutable records linked through `supersedesAnalysisId` where known; never alter an earlier verdict to make history look more accurate.
4. Include assumptions, valuation basis, scenarios, falsification conditions, proof points, benchmark alternatives, sizing guidance and source references as supported; retain the full reasoning in `rationaleMarkdown`.
5. Validate if feasible; state when validation was not possible. Provide a downloadable, importable JSON artifact using a clear filename such as **`AnalysisRecord.v1-{TICKER}-{YYYY-MM-DD}.json`**.

The analysis record does not authorise a trade. A negative or watch verdict remains tracked by `investment-analysis` in the same way as a selected idea. Where multiple ideas concern one security, identify which economic hypothesis the judgement applies to.

### 3.4 Observation and evaluation (interfaces D and E)

`investment-analysis` observes ideas regardless of whether we selected them, including rejected ideas, later-delisted shares, missed catalysts and revised hypotheses. Its evaluation report should distinguish:

- **Original proposal:** performance from the first realistically actionable original suggestion, with appropriate benchmark, horizon and evidence limitations.
- **Our dated research verdict:** returns of selected *and rejected* candidates from the date our judgement became actionable, and whether proposed business/catalyst outcomes occurred.
- **Actual investment activity:** imported broker trades and corporate actions; do not equate this to theoretical idea returns. Execution-decision matching, performance and tax remain authoritative in `investment-reviews`.
- **Source/proposer quality:** complete eligible cohorts, benchmark-relative and horizon-matched returns, sample sizes, uncertainty and attribution. A screener arrival or ranked-list mention is not automatically a personal buy recommendation.

When an evaluation report is supplied, examine not just the winners and losers but whether the **original reasoning was well supported by information available at the time**. Distinguish good decisions with disappointing outcomes from flawed decisions with lucky outcomes. Separate true out-of-sample results from retrospective backfills. Record emerging findings as process watchpoints; propose—but do not silently enact—strategy changes.

## 4. Shared investment and evidence discipline

The **current Investment Strategy** governs all thresholds and allocation targets. In particular:

- The non-pension portfolio has **broad-market beta, thematic beta-plus and alpha-seeking individual stocks**, plus liquidity; themes are intentional systematic tilts, not automatically diversified beta or assured alpha. Assess look-through overlap, especially common defence and AI-capex exposures.
- Select stocks for credible, underappreciated *shareholder* outcomes at current valuation, not technological excitement, headline growth or already-recognised quality. Include permanent-loss risk and opportunity cost.
- Compare **business evidence** with the credibility of the original claim: company assertion; customer/partner corroboration; independent technical evidence; and, where available, a commercially relevant adversarial comparison against strong competitors. Customer deployment does not by itself demonstrate superiority.
- For material M&A or financing, analyse purchase price, organic versus acquired growth, leverage, dilution, execution, cash conversion, ROIC and **per-share** economics—not just strategic rationale.
- Keep the strategy's profit-taking, absolute-high stop-loss review/default-exit thresholds, spike-context exception, volatility and time-held checks, and the separate dated **moonshot proof-window** rules. Do not let conditional holdings or extensions become indefinite avoidance of an exit.
- Review actions for genuine prospective merit. A rise, fall, historical gain/loss, or attractive thesis does not itself decide the allocation. Reinvest only when alternatives exceed the appropriate hurdle; the allocation target is a risk budget, not a purchase quota.

Do not duplicate numerical rule definitions in schemas or tools when the strategy is their authority. In reports, name the applicable rule and its contemporaneous value, including any written exception.

## 5. Structured monthly stock review

### 5.1 Normal scope, cadence and inputs

Run when requested, usually monthly during higher-volatility periods and otherwise at the cadence directed by the strategy. Normally covers **individual shares in ISA and taxable accounts**; exclude SIPP/pension, collective funds, bonds, private investments and MMFs from the stock-by-stock monthly scope unless explicitly included. Consider those other assets for relevant *portfolio-level correlation, capital and liquidity context* without pretending they are part of the per-stock workbook.

Read the latest available:

- Investment Strategy; current `thesis.md` and `thesis.json`.
- Previous monthly/annual decisions report and any agreed watchpoints/proof-point table.
- `investment-reviews` **Periodic Review** workbook, and where available its decision-outcomes/check-decisions reports or decision log.
- Relevant `investment-analysis` briefs, candidate inbox and evaluation reports exported for this review.
- Primary filings and material news since the prior review, especially for holdings meeting strategy triggers.

Do **not** mistake the periodic workbook's **Start Value, P&L or ROI since the previous review** for lifetime investment return. `New`, `Retained`, `Increased` and `Sold` are prior-period decision outcome groups, and `Sold` is a counterfactual view. The thesis candidate basket is an equal-weighted diagnostic, **not** an actual portfolio return.

Stop-loss: the **absolute 90-calendar-day closing high** determines the >20% review / >30% default-exit trigger under the current strategy. The 10-trading-day smoothed high and P90 high are context for transient spikes; they do **not** replace the trigger. Volatility in the workbook is a 90-day estimate; the low-volatility rule needs persistence over **two successive quarters**, not a single reading.

### 5.2 Conversation sequence

Unless explicitly changed by the user:

1. **Previous decisions:** compare New/Increased/Retained/Sold outcomes with broad benchmarks and relevant thesis-candidate baskets. Check completed versus pending trades; avoid overinterpreting one month's price changes.
2. **Theses:** review fundamental changes and whole candidate baskets, held versus unheld expressions, breadth and possible omissions. Revisit `thesis.json` candidate universes systematically each quarter; make interim changes for material new evidence.
3. **Holdings:** evaluate every in-scope stock against risk rules **and** today's prospective return relative to competing candidates, thematic ETFs and broad-market beta. Distinguish a hold from a recommendation to add.
4. **Evidence checkpoints:** review dated pre-proof tests, acquisitions/financings, exceptions and slipped catalysts. Record pass/failure criteria and reasons for any one-time extension.
5. **Provisional decisions:** discuss and agree retain, conditional retain, watch, rotate, partial profit-take, increase or exit. Separate research verdicts from executable trades.
6. **Capital allocation:** consider existing and newly discovered candidates **on equal terms**; include alternatives within and outside our themes, diversified trackers, thematic funds and MMFs. Do not give the thesis list automatic preference just because it is maintained.
7. **Process watchpoints:** revisit and close, continue or escalate; identify any proposed (not automatic) strategy or thesis edits.
8. **Final artefacts:** after discussion and user agreement, produce the Word decision report and, when buy/sell decisions were made, `investment-reviews` YAML. Produce applicable interface A/C records for **new or substantively reanalysed registered ideas**; do not bulk-create ideas for every routine mention or unchanged hold.

Long reviews can proceed by company group. Keep an interim checkpoint of agreed versus unresolved decisions when needed; never describe preliminary recommendations as already approved or executed.

### 5.3 Monthly Word report: required sections

Produce the **downloadable Word report only after the user asks for the final version**. Its structure is:

1. **Executive Summary:** approximately three paragraphs on headline outcomes, thesis validity and significant decisions.
2. **Outcome of previous decisions:** New/Increased/Retained/Sold versus benchmarks and candidate baskets; commentary on selection quality, not just short-term return.
3. **Core thesis areas:** fundamental developments, candidate/held baskets, breadth, expressions, new watchpoints; proposed `thesis.md`/`thesis.json` changes.
4. **Stock recommendations:** one table per thesis with stock, proposed action, relative candidate-basket performance, principal competitor/alternative, and the reasoning. State separately **would buy today?** and **would add today?** Include proof points and material M&A/shareholder-value assessment where relevant.
5. **Agreed actions:** table of thesis, stock, action and GBP amount/value for each increase, partial sale/profit-take or exit.
6. **Reinvestment decisions:** rationale and alternatives, including best existing position, unheld candidate, asymmetric candidate, lower-risk/fund alternative and MMF; wrapper placement, overlap and purchasing table (thesis, security, GBP amount, role, justification).
7. **Conditional increases/proof-point capital:** stock, why withheld, next event/date, pass/fail evidence and status; no automatic drift of deadlines.
8. **Material acquisitions and financing:** transaction, strategic purpose, price/dilution/leverage, evidence of per-share value creation, next checkpoint, assessment.
9. **Process watchpoints:** issue, why it matters, first noted, evidence, escalation trigger and status; specifically exception creep, M&A/capital-allocation drift and candidate-basket statistical distortions.

Where a section is genuinely not applicable, state that briefly rather than manufacturing content. Retain sufficient substance on **holds and no-action conclusions**, not only trades. Distinguish proposed edits to strategy/thesis documents from changes already accepted.

## 6. Annual investment review

Conduct the annual review normally in **January**, using the Investment Strategy and supplied `investment-reviews` **Annual Review**, full-history, fund and tax/decision reports as applicable. The annual scope is **the consolidated economic portfolio**: pension and non-pension wrappers, off-platform/private holdings and cash where data is available; wrapper-specific implementation remains distinct.

Review in the following order unless directed otherwise:

1. **Reconcile the year:** starting/ending values, external contributions/withdrawals, money-weighted return where available, results by wrapper, stock/fund/asset category and appropriate benchmarks. Treat price gains and external cash flows separately.
2. **Whole-portfolio risk:** allocations to equities, bonds, alternatives, liquidity; drawdown tolerance; concentrated/correlated exposures across wrappers and off-platform assets.
3. **Three-tranche non-pension model:** broad beta (diversification, cost, index composition), thematic beta-plus (sector valuation, overlap, cost, index methodology), active stocks (distribution of expected returns, proof points, position sizes, new versus existing candidates). Assess whether the normal allocation and risk budget remain suitable.
4. **Fund review:** assess strategy's annual rules for loss, two-year benchmark underperformance and unexpected volatility, plus active-manager risk for any remaining active funds. Test thematic funds against broad beta rather than presuming sector attractiveness.
5. **Active-stock review:** assess the year's winners/losers, exits, retain/rotation decisions, realised versus hypothetical outcomes and opportunity cost. Apply the same forward-looking test as the monthly review; include new discovery candidates.
6. **Discovery and decision quality:** discuss available `investment-analysis` evaluation reports and `investment-reviews` outcomes, including accepted/rejected ideas, author/source cohorts, internal discovery, decision timing, risk-adjusted returns and attention cost.
7. **Tax, cash and allocation plan:** consider foreseeable withdrawals, taxable gains/losses, wrapper capacity, liquidity reserves and a staged rebalancing/implementation plan. Distinguish investment judgement from tax-driven implementation.
8. **Governance:** decide which watchpoints warrant formally revising the Investment Strategy, theses, proof-point rules or this operating brief.

Discuss in stages before drafting conclusions. The final report should provide an executive summary, annual performance and attribution, allocation/risk review, fund/tranche reviews, active-stock decisions, discovery/process evaluation, action plan and agreed governance changes. Produce a dated Word report on request and a separate YAML execution-decision file for any agreed buys/sells covered by the existing decision-log scope. Do not invent transaction details or tax calculations absent from the authoritative reports.

## 7. Ad hoc conversations, scheduled monitoring and special reviews

This procedure applies equally to developments discovered during scheduled tasks, a direct user question, a news item, new technology investigation, a candidate found outside our maintained theses, and a focused revisit of a holding.

**Default ad hoc sequence:**

1. **Establish what changed:** identify the event, date, source quality, affected theses/securities and whether it is a fact, claim or hypothesis.
2. **Assess significance:** distinguish (a) information about an existing idea, (b) a new potential candidate, (c) a thesis/watchpoint development, and (d) a portfolio risk requiring prompt attention.
3. **For a new candidate:** if explicitly agreed for research, create **interface A**; otherwise record or suggest it without silently creating a submission.
4. **For an existing registered idea:** use its existing record and dated brief where available. If the news materially changes the case and we reach a new conclusion, create a new **interface C**, linked to the earlier analysis; do not create a duplicate A unless it is a genuinely distinct thesis.
5. **When the user requests immediate assessment:** answer the question with available sources even if formal enrichment has not yet happened, identifying what remains unverified and what is needed for an importable record.
6. **If an actual purchase or sale is agreed:** document the rationale and produce/update an `investment-reviews` decision YAML as appropriate; do not treat the decision as an executed trade.
7. **Update continuity:** propose adjustments to `thesis.md`, watchpoints, candidate universes or proof-point dates where warranted; do not modify the standing Investment Strategy without explicit agreement.

A scheduled monitoring task is a **discovery/evidence channel, not an autonomous buyer or a blanket authorisation to create ideas**. Routine monitoring alerts may be triaged and discarded without producing structured artefacts.

A one-off portfolio restructuring, fund selection exercise or tax/liquidity review may depart from the monthly stock scope and report outline. Specify the actual scope and distinguish strategic selection, tax consequences and trade execution.

## 8. Execution decisions and the investment-reviews YAML log

The research verdict (interface C) and an investment decision implemented through brokerage are **separate records**. The authoritative syntax, matching semantics and taxonomy for execution decisions are in the `investment-reviews` README, **Decision Log**. Follow that source if it changes.

For each session in which buys or sells are **actually agreed**, prepare a downloadable YAML file named **`YYYY-MM-DD.yaml`**, using the *decision date* (not necessarily the calendar month the review covers). Default execution window: **decision date through decision date + 14 days**, unless the user specifies another window. Multiple buy/sell entries may belong to the same file. If decisions are phased, an **interim sale-only file** may be provided and augmented later with further agreed actions; keep the date/window consistent and avoid conflicting decisions.

Required structure:

```yaml
classification_version: 1
decision_date: YYYY-MM-DD
execution_window: {start: YYYY-MM-DD, end: YYYY-MM-DD}
decisions:
  - ticker: EXAMPLE.N
    action: sell
    primary_reason: better-expression-available
    investment_type: growth
    commentary: "Why we agreed this action at the time."
```

Populate exact Yahoo Finance symbols as recognised by `investment-reviews`; use the README's controlled **purchase/sale reason codes**, optional `secondary_reasons`, and `linked_decision_id` for an actual replacement. The primary reason is the **reason to act now**, not a general description of the company. `investment_type` remains `core`, `growth` or `moonshot` as defined by the existing tool—not our new beta/beta-plus/alpha shorthand.

**Include** agreed new buys, increases, reductions, profit-takes and exits. **Exclude** holds, rejected ideas, mere research selections and orders we never agreed. Distinguish a trade intended in a decision window from its later actual execution; the tool links them independently. Execution windows and entries must satisfy the `investment-reviews` decision-log checks.

If an ad hoc buy/sell is agreed outside a review's decision date/window, use its own dated record unless the existing window legitimately covers it. Do not backfill an investment rationale from later market outcomes. Do not silently mix taxable liquidity/fund disposals into a stock-only monthly report; include them in the execution log only if they fall within the log's intended scope and are agreed and classifiable.

## 9. Artefact creation and hand-off rules

| Situation | Output | Timing / constraints |
|---|---|---|
| Agreed **new** candidate for research | `IdeaSubmission.v1-{TICKER}-{DATE}.json` | At agreement, before tool enrichment; validate if possible, check duplicates |
| Tool delivers completed enrichment | `ResearchBrief.v1` JSON + paired Markdown | **Read** and analyse the actual version; normally produced by `investment-analysis`, not reconstructed by the assistant |
| Concluded research verdict on a registered idea | `AnalysisRecord.v1-{TICKER}-{DATE}.json` | After substantive conclusion; real IDs, immutable, validate if possible |
| Monthly / annual review discussion | Chat analysis and interim checkpoints | Iterative; provisional decisions remain clearly provisional |
| Completed monthly / annual review | Dated Word decision report | Only when requested after conclusions agreed |
| Agreed buy/sell decisions | `YYYY-MM-DD.yaml` | At final or interim decision checkpoint; exact `investment-reviews` format |
| Tool-generated retrospective evaluation | Evaluation report / exported data | Discuss quality of reasoning and outcomes; don't fabricate missing tool evidence |
| Thesis/strategy/process revisions | Proposed replacement Markdown/Word document | Only when separately requested or accepted; don't silently edit project sources |

Where multiple artifacts would be useful, offer them without claiming they were imported or persisted. An attachment is not proof of successful ingestion into the local application. Provide download links only for files actually generated and checked.

An ad hoc research discussion need not force a Word report or execution YAML; conversely a periodic portfolio review should not omit its agreed reporting requirements merely because `investment-analysis` now exists.

## 10. Research outcomes, comparison discipline and self-evaluation

All candidates—including current holdings, external crowdsourced discoveries and our own thematic ideas—compete within one pool under the same investment hurdle. Conditional Retain means *eligible to compete*, not a commitment to keep. A Strong Retain is also reconsidered when materially better alternatives appear.

At the point of selection or rejection record, where relevant:

- What the market appears to be underpricing, what economic improvement is needed, and what it would mean **per diluted share**.
- Adverse/central/exceptional scenarios with explicit horizon, evidence and valuation assumptions; avoid a binary rule requiring an arbitrary 5× outcome.
- Whether the alternative broad tracker, thematic ETF or another stock offers better risk-adjusted prospective returns.
- Why the candidate is in scope, whether the proof point has a meaningful date, and what would change the verdict.
- Whether the decision is a research judgement, executable instruction, or actual imported transaction.

For retrospective evaluation, **track misses as well as successes**. Compare rejected and accepted idea cohorts from comparable actionable dates and horizons; include delistings, corporate actions and coverage gaps. Separate source discovery value from source recommendation quality, our research value-add from implementation, and business-thesis correctness from price return. Avoid rewarding prolific reprints, correlated repeated recommendations, survivorship bias or a small number of 10× outliers.

Treat conclusions as provisional when the evidence is incomplete. If research, outcome data and investment-review reports disagree, identify why (different dates, FX, corporate actions, price adjustment, capital flows, benchmark or missing records) before drawing behavioural lessons.

## 11. Review continuity and changes to this procedure

At the end of a substantive review or research programme, summarise **agreed decisions, unresolved questions, watchpoints, specific proof events/dates, next research candidates and tool-record hand-offs**. Record source dates and distinguish commitments from options. An interim checkpoint is appropriate when a long review spans sessions.

Do not change investment rules in response to a single outlier. Explicitly identify proposals to amend the Investment Strategy, `thesis.md`, `thesis.json`, schemas, the `investment-analysis` tool or this brief. The user must approve the proposed change before it is adopted. The existing code/schema owners, not this operating brief, define valid interchange formats and live data semantics.

---

## Proposed replacement project instructions

Keep the project-level instructions short; the full operating procedure should live in this document, attached to the project sources:

> For all investment-related conversations, use the latest **Investment Strategy** and **Investment Operations Brief** in project sources. The Investment Operations Brief defines the procedures for periodic reviews, ad hoc research, `investment-analysis` hand-offs, evaluation and `investment-reviews` decision recording. Follow its triggers, authoritative schemas and artifact requirements; do not assume access to unprovided tool records.

*This draft is an operating procedure. It does not itself change the Investment Strategy or the applications' schemas.*
