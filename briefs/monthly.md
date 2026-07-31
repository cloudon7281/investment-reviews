# Introduction

This is your standing brief for my regular monthly review of investments.

# Scope

The part of my portfolio that is in scope for monthly reviews is the part I actively manage i.e. individual stocks held in both ISA wrappers and general, taxable stocks and shares funds; it excludes pension investments, funds of stocks and bonds, and cash/money market funds.

From time to time I may broaden the scope to include some of these other investment types: if so I will explicitly prompt you on what extra I am including.

# Purpose

The purpose of these reviews is to:

- review the outcome of the decisions taken at the last monthly review (or annual review, if this is February) and identify if that should trigger any re-assessment of the overall strategy (e.g. recommend changes in decision criteria)

- briefly review whether our core investment theses are sound, or whether there has been any material change in them since the last review; treat thesis and candidate performance as evidence, not as an automatic trading rule: one-month relative performance may reveal information or prompt investigation, but does not by itself establish that a thesis is valid or invalid, or that the strongest recent performer is the best stock to buy

- assess all current stock holdings against the criteria for individual stocks set out in my Investment Strategy (see below), namely:
  - scaled profit-taking (sell 20% on ~doubling, while letting exceptional performance ride where overall portfolio risk is acceptable)
  - stop-loss (mandatory review at 20% fall from recent highs; mandatory sale at 30% fall unless documented exception)
  - low volatility (I am looking for growth stocks which typically implies high volatility, so sell stocks with <25% annualised volatility over 2 quarters)
  - time held (review but do not necessarily sell any stocks held more than a year)
  - change in fundamentals (sell if change in fundamentals e.g. 2 sucessive quarters of earnings misses)
  - maintain a short rolling list of process watchpoints: tentative cross-review observations that may matter for future decision-making, but which do not yet justify any change to the Investment Strategy document

- but to do so in the context of my core investment theses; there is a significant difference between a whole thesis area falling because of short-term market sentiment, a thesis weakening fundamentally, and an individual stock underperforming the wider set of candidate expressions of the same thesis because of poor execution, inferior exposure, valuation or other company-specific factors

- assess whether each currently held stock remains one of the best available expressions of its thesis, rather than merely whether it remains defensible in isolation

- use the configured thesis candidate universes and their monthly performance to compare held stocks with plausible unheld alternatives, distinguish thesis-level performance from stock-selection performance, assess whether market performance is broad or concentrated, and inform the thesis review, individual stock review and reinvestment decision

- based on that, make a hold/increase/profit take/exit decision on each stock

- agree how to re-invest any funds arising from profit taking/stock exits.

Again, from time to time I may want to vary these at a particular review; if so, my prompt will explicitly say how.

# Review sequence

Unless varied in the prompt for a particular month, conduct the review in the following sequence:

1. Review the outcome of the previous month's decisions.
2. Review each investment thesis, including fundamental evidence and the performance of its full candidate universe.
3. Review each individual holding, including whether it remains a preferable expression of its thesis compared with available candidates.
4. Agree any hold, increase, profit-take or exit decisions.
5. Assess where to reinvest capital released by sales, drawing first on the maintained thesis candidate universes before conducting an open-ended search.
6. Review process and thesis watchpoints.
7. Produce the final written report only after discussion and agreement in the chat session.

# Attached documents

You should find attached the following documents.

- My latest Investment Strategy document titled 'Investment Strategy (MMM YYYY).pdf': this sets out my overall strategy, and you should read it first.

- A PDF titled 'Investment Decisions - <month> <year>.docx', which documents the decisions we took at our previous monthly review.

- A spreadsheet (in Excel form) titled 'Portfolio Report <month> 2026 Periodic Review.xlsx' showing performance since the previous review.  This has the following tabs.
  -  Periodic Review Summary (<start date> to <end date>, evaluated on <evaluation date>).  This shows the outcome of all the buy and sell decisions taken during the previous review period of [start date, end date], with current prices evaluated as of the evaluation date (typically today or yesterday at the point we hold this review).  This shows performance bucketed as follows:
    - New = stocks bought for the first time as a result of the previous investment review.
    - Retained = stocks we decided to retain.
    - Increased = stocks where we decided to increase our holding.
    - Sold = stocks where we decide to exit; these are shown here so we can do a counter-factual review and assess the outcome of that exit decision.
    - Benchmarks are for comparison with broad market indices.
    - Each of these categories is then further broken down by tags corresponding to the investment thesis that drove the decision to invest.
  - The New|Retained|Increase|Sold tabs have the per-stock breakdowns.
  - The Benchmark tab shows specific market benchmarks e.g. the Nasdaq.
  - In each of these tables, Start Value refers to the vaue of the relevant investment *at the point of the last investment review* (i.e. since last month), *not* the original purchase value.  Similarly, P&L and ROI show the performance *since the last review*, not since purchase.
  - The spreadsheet also includes columns providing data to assess the other criteria:
    - profit-taking: "progress to 2x" records the ratio of the stock *since purchase or the last profit taking*, and '# doublings' shows how many doublings there have been *since purchase*
    - stop-loss: '% of high', together with current price and 90d high, records the relevant info
    - low volatility: the 'volatility' column records annualised volatility over the last 90 days
    - time" 'days held' shows how long I have held the stock.
    - I do not currently have any automated way to provide information on fundamentals.

  - The `Periodic Review Summary` tab also includes a thesis-level monthly performance table derived from `thesis.json`. For each thesis it shows, as available:
    - equal-weight return of the complete configured candidate basket
    - equal-weight return of the subset of candidates currently held
    - held-basket return relative to the full candidate basket
    - positive candidate count, evaluated candidate count, configured candidate count and breadth
  - A `Thesis Performance` tab provides candidate-level detail, including thesis, ticker, company name, held status, effective start and end dates and prices, monthly return, and any missing-data or calculation status.
  - The thesis basket is a diagnostic equal-weight comparison, not a representation of the actual portfolio return.
  - Use the thesis information to ask whether performance was broad or concentrated, whether held expressions outperformed the wider opportunity set, whether different expression types behaved differently, and whether market evidence corroborates or conflicts with fundamental evidence.
  - Do not assume that the best-performing candidate over the previous month is the best current purchase.

- A description of my current investment theses titled `thesis.md`. This is the authoritative qualitative statement of the theses and explains the candidate-expression universes.

- A machine-readable candidate configuration titled `thesis.json`. This is a deliberately narrow mapping of thesis names to candidate tickers and display names, used by the portfolio-review tooling.

# Desired output

The final output will be a downloadable document in Word format, with the sections detailed below.  Do not attempt to produce this final version after the initial prompt: produce a draft reply in the chat session, which we will discuss and iterate before I ask you to produce the final output document.

- Executive Summary
  - 3 paragraphs summarising the full report, covering headline results, thesis validity, and actions (key stock entry/exit decisions).

- Outcome of last month's decisions
  - Start with the headlines: performance of each of the New, Increased, Retained and Sold buckets, with comparison to Benchmarks.
  - Commentary on that outcome, where clearly we want New, Increased and Retained to outperform both Sold and Benchmarks.
  - Commentary on any lessons to learn and suggestions for changes in strategy.
  - Compare relevant decisions with the performance of their thesis candidate baskets, so that a stock decision is assessed against the opportunity set rather than only against the broad market.
  - Avoid judging decisions solely by one month's subsequent price movement.

- Review of core investment thesis areas
  - This section briefly discusses each existing investment thesis and whether we judge it still valid.
  - For each thesis, summarise materially relevant fundamental evidence since the previous review and interpret candidate-basket return, held-basket return, held-versus-candidate performance and breadth.
  - Identify whether price performance was broad, concentrated or divided by expression type, and distinguish thesis weakness from poor stock selection or short-term valuation and sentiment effects.
  - It also identifies any additional thesis we have identified and their status e.g. watch and review in N months; invest now.
  - It suggests changes to `thesis.md` or `thesis.json`, if required. Candidate universes should be systematically reviewed quarterly, with interim changes only where material new information justifies them.

- Individual stock recommendations
  - One table per investment thesis, with columns as follows:
    - stock name
    - proposed action (profit take/hold/increase/exit)
    - performance versus the relevant thesis candidate basket
    - principal alternative expression or comparator
    - justification with reference to the criteria above, fundamentals, thesis validity, valuation and comparative quality as an expression of the thesis.
  - For each held stock, explicitly consider: would we buy this stock today rather than the best credible alternative expression of the same thesis?

- Summary of required actions
  - A table showing for each existing stock we decide to buy (decision = increase) or sell (decision = profit-take or exit) with columns as follows:
    - thesis
    - stock name
    - increase/profit-take/sell
    - amount:
      - increase: amount in GBP to buy
      - profit-take: amount in GBP to sell
      - exit: value in GBP of current holding.

- Re-investment decisions
  - A commentary summarising our discussions on how to re-invest any capital freed by selling existing stocks. Begin with the maintained thesis candidate universes, but permit wider research where no existing candidate is attractive or material evidence suggests an omitted company.
  - Consider the strongest existing holding worth increasing, strongest unheld candidate, best asymmetric candidate, best lower-risk or diversified expression, and the option of allocating to a money-market fund where no stock offers attractive risk/reward.
  - Guard against performance-chasing and double-counting overlapping thesis exposures.
  - A table with an entry for each stock we propose to buy, with columns of:
    - thesis
    - stock
    - amount in GBP to buy
    - candidate role or expression type
    - brief justification, including why it is preferable to the principal alternatives.

- Process watchpoints
  - A short section capturing any tentative lessons or emerging patterns that are worth monitoring across reviews, but which do not yet justify a change to the Investment Strategy.
  - This section is for persistence and continuity only: it must not be used to smuggle in rule changes without explicit discussion.
  - Include a table with columns:
    - issue being monitored
    - why it might matter
    - first noted
    - evidence so far
    - trigger for escalation
    - current status
  - At each monthly review, briefly revisit any existing watchpoints and for each one decide whether to:
    - keep monitoring
    - close as noise / resolved
    - recommend explicit amendment to the Investment Strategy document