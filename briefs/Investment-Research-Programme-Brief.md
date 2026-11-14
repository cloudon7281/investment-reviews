# Investment Research Programme Brief

**Status:** Agreed
**Version:** v1.0 · 14 November 2026  
**Scope:** Coordinating repeatable, sometimes parallel, research across investment ideas, watched opportunities, competing securities and current holdings.  
**Companions:** `Investment-Research-Charter-A-Discovery-Triage-v1.0.md`, `Investment-Research-Charter-B-Watch-Requalification-v1.0.md`, `Investment-Research-Charter-C-Comparative-Research-v1.0.md`.

## 1. Purpose, authority and boundaries

This brief governs **the conduct of a research programme**, not which investments are attractive. It supplies standard charters, a common programme register, bounded research assignments, evidence and challenge controls, comparative ranking and reproducible hand-offs. Use it when the volume or interdependence of research warrants coordinated work; its lightweight charters also apply to routine batches and watch checks.

Authority remains divided:

| Authority | Governs |
|---|---|
| Most recent agreed *Investment Strategy* | Objectives; broad-market beta, thematic beta-plus and alpha-seeking stock roles; selection, valuation, allocation and risk rules |
| *Investment Operations Brief* | Monthly/annual review sequence; discussions and approvals; new ideas and analysis records; actual investment decisions and reporting |
| Current `thesis.md` / `thesis.json` | Maintained theses, watchpoints and reference candidate baskets |
| `investment-analysis` specification and canonical schemas | Discovery, versioned ResearchBriefs, idea identities, `AnalysisRecord` verdicts, supersession, observation and evaluation |
| `investment-reviews` and its authoritative reports | Broker activity, holdings/performance evidence, Periodic Review, annual accounting, decision outcomes and execution-decision YAML |
| This brief and its charters | Research orchestration, delegation, work-package review and comparative-analysis artefacts |

No charter authorises a trade, changes a strategy rule, creates a new application interface, or substitutes an internal programme ranking for an official `AnalysisRecord`. Programmes use exported application data when live authorised access is absent. Never infer successful imports, current holdings or latest analysis IDs from a previous chat or an earlier export.

## 2. The three standard charters

The charter is **a reusable operating mode**, not a fresh methodology negotiation at every run.

| Charter | Standard trigger | Default universe | Decisive question | Usual hand-off |
|---|---|---|---|---|
| **A — Discovery Triage** | Incoming external/internal idea batch | Every idea in that batch | Investigate, monitor, reject or mark not relevant? | Dated first-pass `AnalysisRecord`s for concluded ideas |
| **B — Watch Requalification** | Before each monthly review; optionally ad hoc | **All** ideas whose latest verdict is `watch` at the frozen intake | Has a material favourable change made the idea worth substantive research? | Coverage report; new `candidate` analyses **only for promotions** |
| **C — Comparative Investment Research** | Monthly and annual active-investment reviews; major comparative ad hoc work | All current `candidate` ideas **plus in-scope current holdings**, with approved additions | Which investments justify fresh or retained capital at today's terms? | Dossiers, cross-sector ranking, research judgements, and portfolio-aware proposals when applicable |

Individual ad hoc investigations remain under the *Investment Operations Brief* and need not instantiate a programme. A substantial ad hoc peer-group or industry investigation uses Charter C, with its purpose and starting universe stated in the run manifest. Charters may be run sequentially or by delegated workers; tool capabilities do not change the methodology.

**Routine review linkage.** A monthly review normally runs B before C and also consumes `investment-reviews` Periodic Review. An annual review applies C to thematic beta-plus and alpha-seeking opportunities alongside its broader portfolio-level examination. The broad-market beta fund review remains in the annual Operations/Strategy process, **outside** `investment-analysis`'s stock-oriented pipeline. See §§5–7 and the amended Operations Brief.

### 2.1 Per-run manifest: specify exceptions, not a new process

For each run, record a short, immutable-at-start manifest containing:

1. **Identity and purpose:** programme/run ID, A/B/C charter version, initiator, decision date/period and any special question.
2. **Universe:** exact exported idea and issuer identifiers, reference population/as-of date, holdings scope where applicable, explicit exclusions, and source archive/file checksums. Record unresolved identity rather than guessing.
3. **Authority and inputs (default):** approved Strategy/Operations/Programme brief versions, current thesis/benchmark definitions, relevant `investment-analysis` briefs/latest analyses and, for portfolio reviews, `investment-reviews` Periodic/Annual reports.
4. **Evidence policy (default):** factual as-of/known-at discipline, source/retrieval dates, a transparent price/FX comparison cut-off, applicable horizons and currencies, licensing/privacy permissions and explicit evidence coverage gaps.
5. **Outputs and gates (charter default):** the charter's defined depth, reporting format, work package assignments, challenge, QA and sponsor review gates. Record only capacity or scope exceptions.
6. **Known limitations/overrides:** unavailable exports, stale data, unresolved tickers/share classes, missing portfolio data, explicit variations approved by the user and dependencies.

The user normally need only request the charter and supply/identify the input universe. The programme lead fills defaults, identifies blockers and records any material scope expansion as a **dated amendment**. Do not silently add names or switch the analysis date. A signed-off run manifest should be reproducible from its input hashes.

## 3. Units of work and research identity

- **Idea:** the source-specific, dated proposition with an authentic `ideaId`. Several ideas can refer to one issuer; preserve their original source, time and hypothesis separately.
- **Issuer/security case:** reusable economic analysis of an operating business, vehicle and relevant listing. Do not merge distinct legal entities, ADR/share classes or currency lines by ticker alone.
- **Work package:** one bounded, assigned evidence-gathering, checking, comparative or challenging task. Its provisional output is not a verdict.
- **Programme decision:** an internal conclusion, issue, ranking or scope decision, with an explicit owner and date; not an execution decision.
- **`AnalysisRecord.v1`:** one official dated research judgement per registered idea, only after a conclusion is reached; immutable, with exact brief version and latest-analysis supersession link.

The programme register maps every original idea to a canonical research case and every case to its peer groups, shared risk factors, work packages and research state. A company-level dossier can support several distinct idea-specific records. Rank issuers/securities for investment attractiveness; score source discovery and idea-level verdicts separately.

For thematic ETFs, use the same comparative research discipline but a fund-specific dossier (underlying holdings, index construction, constituent valuation, concentration, fees, liquidity and tracking). Existing `ResearchBrief.v4` fields principally support equities; do not invent stock-style financial metrics or claim an unsupported ETF import contract.

## 4. Roles and delegation

The roles are obligations, not necessarily different people or concurrent model instances.

| Role | Accountable for |
|---|---|
| User / programme sponsor | Authorising material scope changes, reviewing decisive judgements, approving **actual** capital decisions |
| Programme lead / integrator | Register integrity, assignments, consistency, gates, cross-sector comparison, discovery proposals and final research recommendations |
| Issuer/vehicle researcher | Primary evidence dossier, fact/claim separation, financial calculations, competing hypotheses and provisional conclusion |
| Sector/peer comparator | Reusable industry context, real economic peers, factor overlap and comparative opportunity ordering |
| Independent challenger | Strongest supported countercase, valuation/financing vulnerabilities, missed competitors and dissent |
| Evidence/contract QA | Provenance, timestamps, source permissions, ID integrity, data conflicts, arithmetic and schema validation |
| Record preparer | Portable per-idea `AnalysisRecord` output after judgement; checking the latest known supersession chain |

Researchers can work in parallel on disjoint packages of ~5–8 cases; ~3–4 concurrent packages is an **initial operational default**, not a strategy threshold. Shared sector context should be prepared once and versioned. The challenger must not merely rewrite the researcher's view. The integrator does **not** average agents' scores or let analysts select their own winners unreviewed.

Workers receive no private holdings, entry prices or personal account detail unless explicitly authorised and necessary for their role. Research agents can be holdings-blind while the programme lead separately owns the holdings-review stream.

## 5. Common workflow, with charter-specific depth

All three charters use a common programme spine: **freeze inputs → normalise → gather/test evidence → compare or detect changes → review → publish**. The number and depth of packages depend on the decision.

### Gate 0 — Initialise and freeze sources

Apply the charter defaults, inspect the actual versioned input, record source checksums and IDs, and reconcile previous analyses where exports permit. State what is known only from an archive and what has been checked against the live ledger. For B, freeze the entire `watch` population. For C, freeze candidate and relevant holdings populations separately so a holdings omission cannot be hidden by a candidate list.

**Pass when:** the universe, missing data, evidence date and authority are explicit. Only ask the sponsor to resolve a substantive scope change or blocker.

### Phase 1 — Normalise and plan

Build the programme register, identify shared issuers/duplicate propositions and corporate identity issues, select genuine economic peer groups and cross-cutting exposures, and assign bounded work packages. For C, include in-scope holdings for coverage, but do **not** pass cost basis or unrealised P&L into the holdings-neutral investment-merit analysis. For B, retain watch rationale/previous triggers; an idea lacking a meaningful trigger remains covered, not automatically promoted.

**Pass when:** every input idea/holding is covered or explicitly blocked; no idea is silently merged or dropped.

### Phase 2 — Investigate proportionately

- **A / triage:** inspect source claim, listing, critical financial and other available evidence; verify enough to support each proposed verdict; avoid full modelling absent decision value.
- **B / watch:** compare new market/business evidence since the last covered watch check (or earlier dated watch verdict) with the documented reason for deferral. Detect material changes in valuation, commercial proof, funding, regulation, competitive position and risk. Use issuer-level shared observations across duplicate ideas; assess promotion **per idea**.
- **C / research:** create a sector context note and a substantive, source-cited dossier for each issuer/vehicle, refreshing prior work rather than pointlessly starting over. Include economics, actual filings, per-share capital structure and dilution, valuation and market expectations, adverse/base/exceptional outcomes where supportable, alternatives, falsifiers, dated milestones, gaps and a provisional view. Distinguish source assertions from independent findings.

All workers distinguish economic observation date from source availability or retrieval date. Flag stale/missing/conflicting financial evidence. An incomplete dossier is *incomplete*, not necessarily `reject`.

### Phase 3 — Compare, challenge and identify new opportunities

- **A:** calibrate verdict definitions across packets; challenge borderline `reject`/`candidate` distinctions and avoid treating unverified claims as negative investment proof.
- **B:** challenge proposed promotions: does the new evidence actually resolve the previous reason to wait and warrant deep research? If not, retain `watch` and record the monitoring result in the programme coverage report. A separate material adverse event may be flagged for targeted triage; B's routine output remains promotion-focused.
- **C:** challenge material leading cases independently, normalise within-sector comparisons, identify the closest real competitor and passive alternatives, then create a provisional all-universe cross-sector ranking. The challenger should actively search for a stronger alternative, not only rebut the target company.

**Discovery is a first-class output in every research programme**, especially C: log competitors, suppliers, technologies and otherwise overlooked investable instruments when investigation reveals an interesting alternative. Record the proposed security, new hypothesis, source evidence, relationship to existing cases and why further research could alter the ranking. A mention is not automatically an idea: see §8.

### Phase 4 — Programme-wide calibration and decision gates

Use the **same Strategy** and source-quality standards for all charter packets, but never rank unlike businesses by raw scenario multiples or uncalibrated numeric scores.

- **A:** report full coverage and verdict counts, cases requiring additional evidence, duplicate-source incidence and significant disagreements.
- **B:** report full watch coverage, newly detected material changes, promotions, unresolved triggers and cases requiring manual follow-up. A no-change result does not create a new `watch` analysis.
- **C:** present a holdings-neutral ranking (relative tiers, close pairwise comparisons and confidence) for all issuer cases, with leading alternatives and shared factor exposures. Agree which decisive uncertainties justify a deeper research wave; shortlist size is a workload choice, **not** a quota. Identify all mandatory holdings-review issues in a **parallel**, initially separate stream.

**Gate:** sponsor can inspect the complete universe, challenge outcomes and proposed research deepening/scope changes before final decisions.

### Phase 5 — Resolve decisive questions and integrate portfolio context

This stage is normally light or skipped for A and B, unless a disputed verdict needs narrow follow-up. For C, commission focused source checks, models, technical/customer/competitor verification and adversarial head-to-head work where another fact could change the outcome. Preserve previous analyses and date all substantive reassessments.

For portfolio-review C programmes, reconcile the holdings-neutral ranking with the holdings-review stream and `investment-reviews` Periodic/Annual inputs. Only **now** apply current position sizes, concentration, wrapper, entry price where relevant to tax or the Strategy's mechanics, switching costs, liquidity and implementation constraints. A higher-ranked alternative need not force a sale if its benefit does not clear the real switching hurdle.

**Non-negotiable:** every Strategy-mandated holding review trigger identified in Periodic Review must receive a documented conclusion or an explicit unresolved/escalated status, even if the issuer ranks poorly or no action is proposed. The trigger affects research priority and governance; it is not evidence of inferior investment merit.

### Phase 6 — Conclude and publish

Preserve all coverage, rejected alternatives, disagreements and non-actions. Report the independent investment ranking **separately** from portfolio-specific proposed actions. Issue only evidence-supported, concluded new `AnalysisRecord`s; no arbitrary record quota or manufactured scenarios. Await the user's portfolio decisions before any actual-execution YAML. Detailed charter outputs appear in the companion templates.

## 6. The two streams within Charter C

**Investment-merit stream (holdings-neutral).** Current holdings and eligible candidates enter the *same* competitive universe. Research their prospective economics, price, return distribution, alternatives and risks without credit for current ownership or historic gain. A holdings flag may be visible to the integrator for coverage; researchers should not receive entry prices, profit/loss or position weights unless required for an authorised specific task. Produce a zero-based prospective opportunity ranking.

**Holdings-review stream (holdings-aware, initially separate).** Use `investment-reviews` Periodic Review and prior decisions to identify all in-scope positions, prior `New`/`Increased`/`Retained`/`Sold` decision outcomes, distance from doubling, the **absolute 90-calendar-day closing high** and its mandatory review/default-exit triggers, smoothed/P90 spike context, 90-day volatility versus the two-quarter persistence rule, moonshot decision windows and changes in position or risk. These trigger checks are mandatory even when no further issuer research is warranted. The Strategy, not this procedure, owns thresholds.

**Integration.** Assess whether an investment that earns its place on merits still earns a place in the actual portfolio, after costs, taxes, correlated exposures and available capital. Distinguish explicitly: (i) would buy with fresh cash; (ii) would add to an existing holding; (iii) would retain current capital; (iv) would rotate out; and (v) no action despite a better-ranking alternative because switching does not justify the cost. Neither research merit nor a change in share price alone constitutes an executed trade.

**Zero-based capital judgement does not require zero-based research effort.** Reuse verified dossiers, refresh price and material evidence, and direct deepening toward cases where it could change the choice. The whole comparative universe must still receive a current, documented assessment. No historic `strong_retain` or `conditional_retain` label exempts a position from competition.

## 7. Periodic and annual review integration

A monthly review normally consumes, in addition to current Strategy/theses and candidate briefs:

1. **Charter B watch coverage/promotions**, completed before freezing the Charter C candidate universe; if the watch export/check cannot be completed, record the gap rather than silently treating the watchlist as unchanged.
2. **`investment-reviews` Periodic Review**, including prior decision-outcome groups and current holdings risk/performance indicators, as a separate authoritative input.
3. **Charter C** prospective research for eligible candidates plus current in-scope positions, then a portfolio overlay and the existing review's discussion and decision sequence.

The Periodic Review remains the authoritative source for its outcome measures. `New`/`Increased`/`Retained`/`Sold` are **prior-period decision groups**, not lifetime returns, and `Sold` is counterfactual. Progress to doubling and drawdown from high are governance signals, not merits scores. The smoothed high and P90 provide context but **do not replace the absolute-high trigger**; one 90-day volatility figure does not establish two-quarter persistence. Retain explicit recording of holds and no-action conclusions.

The annual review uses the **same Charter C research method** for thematic beta-plus and alpha-seeking opportunities and the same zero-based merit/portfolio split. It additionally runs the Operations Brief's consolidated portfolio, pensions, risk, funding, tax and broad-market beta/fund-compliance review. The annual fund compliance assessment is not replaced by C. At the monthly review, thematic beta-plus is assessed for **opportunity merit/competition** where in scope; this is **not** a new monthly obligation to perform every annual fund tracking, fee and compliance test. The usual individual-stock monthly scope and pension-account boundary in the Operations Brief still apply unless explicitly varied.

An existing `investment-analysis` E-v1 portfolio-activity feed is **trades and corporate actions only**; it does not reconstruct the Periodic Review's holdings, P&L, triggers or decision outcomes. Do not duplicate `investment-reviews` reporting or invent a joined live interface. Where thematic ETFs or other funds lack a supported `investment-analysis` research contract, keep a clearly attributed programme dossier and existing Operations decision report rather than fabricate an official record.

## 8. Discovery and admission of new ideas during research

Every researcher and challenger may propose candidates discovered through competitors, suppliers, adjacent technologies, geographic alternatives or other analysis. The **Discovery Register** is a distinct *internal* programme artefact, initially not an official `investment-analysis` idea.

Each proposed entry records: discovered name and identified listing (or unresolved status), proposed investable hypothesis, evidence/citation, link to existing research cases, why it might improve the opportunity set, proposer attribution, date and suggested next action (`comparator_only`, `propose_admission`, `already_registered`, `insufficient_evidence`). Never claim a third-party publisher proposed an idea actually originated in our research.

Two default discovery checkpoints: after shared sector research and after cross-sector comparison. The programme lead removes false duplicates and recommends admission only where the new opportunity has a plausible chance to change the research ranking. **The user agrees candidate admission** under the Operations Brief §3.1; only then issue `IdeaSubmission.v1`, import/enrich it, and add it through a dated scope amendment. A named competitor may still be compared without creating an official idea. The originating programme and source discovery event are retained for later evaluation.

A material new proposition concerning an already-registered issuer is assessed for same idea versus claim revision versus a genuinely distinct idea, per the existing interface A contract. No generated idea ID is inferred before import. A new idea admitted to a programme does not receive a retroactively dated verdict.

## 9. Delegated work-package contract

Every assignment to an agent, person or script includes:

| Field | Requirement |
|---|---|
| Identity | Programme ID, charter, package ID/version, researcher, issuer/security/idea references and exact upstream artefact versions/hashes |
| Boundaries | Research question, role, sector, in/out of scope, allowed source/data permissions, maximum workload and evidence cut-off |
| Inputs | Relevant ResearchBrief and last analysis exports, shared industry notes and comparison assumptions; restricted holdings details only if role-approved |
| Outputs | Cited claims/evidence log, transparent calculations, unresolved gaps, provisional finding, strongest rival/contrary case and **new discovery proposals** |
| Quality | Source timestamps, independent verification, currency/share reconciliation, corporate-action identity checks and reproducibility checklist |
| Failure and revision | Explicit `blocked` / `incomplete` / `needs_review` state with cause; revision creates a new output, never overwrites completed work |

An independent challenger gets a bounded instruction to **seek disconfirmation** and must record objections and the lead's disposition. A sector comparator cannot silently declare an unresearched competitor a final winner. Package results remain provisional until central reconciliation and sponsor review.

## 10. Programme register, storage and resumption

Keep durable, versioned programme artefacts; no programme's state may depend on a single conversation's context window. Example structure:

```text
research-programmes/<programme-id>/
  run-manifest.md
  inputs/                   # original exports / hashes / versions
  register.json             # internal programme register, not an app contract
  work-packages/
  sector-context/
  issuer-dossiers/
  challenges/
  discovery-register.md
  rankings/
  portfolio-triggers.md    # charter C portfolio reviews only; restricted
  portfolio-overlay.md     # charter C portfolio reviews only; restricted
  output/
  audit-log.md
```

Track each package's identity, owner, dependencies, state (`queued`, `running`, `blocked`, `review`, `complete`, `superseded`), source cut-off, last verified work, retries and checksum. On restart, reopen the manifest/register/completed outputs; do not presume prior model context. Mark stale evidence, preserve completed versions and create dated revisions. Explicitly distinguish a research proposal from user agreement and live import.

The programme coverage report records included/omitted cases, evidence coverage, unresolved conflicts, challenges completed, discovered opportunities, decisions reached, work still outstanding and quality failures. Evaluate source yield and research decision quality later, without merging historical revisions or attributing outcomes to the wrong timestamp.

## 11. Analysis, evaluation and execution hand-offs

**From `investment-analysis`:** use genuine exported idea IDs, latest available analysis history, dated briefs, source classifications and observation data. Do not assume live service access. Any exported B-v4 brief is an evidence pack, not a conclusion.

**To `investment-analysis`:** produce a new, immutable `AnalysisRecord.v1` only for an actually concluded judgement; correct `ideaId`, cited `briefId`/`briefVersion` or legitimate null pair, `analyst`, distinct current `analysisId`/`analysedAt`, `supersedesAnalysisId` naming the latest known analysis, and evidence-limited rationale. Do not overwrite an accepted analysis. Validate JSON and any batch manifest. Since the ledger may change after export, **preview live import** for stale links before committing. Do not re-send superseded originals or change earlier timestamps. Never treat `watch` as `reject` merely to create an evaluation contrast.

**To `investment-reviews`:** the programme never records actual execution or runs broker accounting. The user approves purchases/sales through the Operations Brief's decision process; then the appropriate decision YAML is generated and later execution is observed from the authoritative trade/action records. Neither the research verdict nor a portfolio recommendation is itself a transaction.

**For evaluation:** maintain the original discovery thesis, research verdict and actual execution as distinct dated anchors; retain rejected and unselected ideas in observation; do not score a source's list mention as an explicit authored buy recommendation. Retrospective performance of analysed ideas is measured from its analysis date, not backfilled from a later conclusion.

## 12. Evidence discipline, QA and acceptance

The Strategy supplies investment criteria. This brief supplies reproducibility controls:

- Every source-derived material claim identifies primary/secondary provenance, date and factual status; financial periods, currencies, share counts and dilution assumptions are visible.
- Use comparable price and FX dates for close comparisons, or clearly report refreshed dates; preserve actual reporting horizons and do not invent probability or scenario precision.
- Distinguish *attractiveness*, *evidence confidence*, *research completeness*, *portfolio fit* and *source quality*. A high-quality dossier does not imply an attractive investment.
- Publish a explained relative ordering or tiers for the **whole** Charter C universe; allow justified ties/incomparable cases rather than a spurious decimal ranking.
- Flag under-verified cases as `research_incomplete` **internally**; this is not an `AnalysisRecord` verdict. If a substantive conclusion cannot be reached, use the correct official verdict only when its semantics fit and the judgement is documented.
- Maintain independence between primary researcher and challenger to the extent tools permit; record unresolved disagreements and the lead's decision.
- All contracted outputs and official JSON must pass structural and coverage checks; missing input, partial failure or stale chain is visible, not a silent pass.

Acceptance checks: (1) every charter-universe item appears once in a register and relevant coverage report; (2) repeated idea/source identities remain traceable; (3) material numerical claims are verifiable; (4) every leading C case has real challenge; (5) cross-sector ranking is explainable and holdings-neutral until overlay; (6) all monthly Periodic Review triggers have closure or escalation; (7) discovered candidates follow explicit admission; (8) official records validate and retain correct supersession; (9) work can resume without conversation memory.

## 13. Tooling and confidentiality

The procedure is tool-neutral. It can run as sequential conversations, ChatGPT Work/Deep Research work packets, parallel Codex sessions or a dedicated API/Agents SDK orchestrator. None is assumed to exist in this chat, and none replaces deterministic source checks or final human approval. Start with a small, reviewable multi-package pilot and automate only proven contracts and bottlenecks.

A future orchestrator should be a thin task/state/validation layer, **not** a second `investment-analysis` application or an execution service. `investment-analysis` currently authorises narrow model use for third-party article summaries; its permission is **not** implicit authorisation for that application—or any new agent—to send private positions, broker/account information or paid publisher content to additional endpoints. Any expanded permissions or integration require explicit approval and security review. Preserve publication content rights.

## 14. Adoption and change control

The three companion charters are normative supplements to this brief. Their defaults can be overridden in a per-run manifest by the user; changes to the general method require a new agreed brief/charter version. Operational tuning (packet sizes, concurrency, shortlist size) is a run decision, not an Investment Strategy amendment.

No change in this document alters the Investment Strategy or the official application contracts. The proposed Operations Brief v1.2 supplies cross-references and review integration; adopt that file explicitly in the project sources rather than silently modifying the earlier approved v1.1.

**Change log — v1.0 (14 November 2026):** replaced open-ended chartering with A/B/C templates; added watch requalification; clarified annual versus monthly scope, holdings-neutral and holdings-review streams, mandatory Periodic Review integration, discoveries from competitor research, and charter-specific outputs/gates. Retained the v0.1 evidence/delegation/reproducibility design.
