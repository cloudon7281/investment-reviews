# Code review on Claude refactoring

I've reviewed the refactoring.  Overall, a good attempt, but there is more we
refactoring to do, some things to check and some code to tidy up.

## Further refactoring

### Logic for evaluating value of holdings in stock X at date Y

We have similar but different logic across full_history_processor, 
periodic_review_processor and value_over_time_processor for calculating the
value of holding in stock X on date Y.
-   periodic_review_processor simply calls
holdings_calculator.get_stock_valuations_at_date, which includes logic to
worry about subsequent stock splits and internally calls
get_stock_price_from_data which includes logic to cope with missing data by
searching backwards up to 14 days.
-   full_history_processor has its own logic in lines 185-218 which ignores
stock splits and doesn't appear to search backwards.
-   calculate_value_over_time lines 129-142 also ignores stock split and looks
forward rather than backward for prices.

This seems inconsistent and overly complicated.  Analyse how we can just simply
call get_stock_valuations_at_date in all cases.

### Facade pattern in roi_calculator.py

I am not a fan of the facade pattern we use to shim the APIs to the
transaction_processor, market_data_fetcher, financial_metrics and 
holdings_calculator, as well as the internal methods within the full history,
periodic review, tax report and value over time processors themselves.  What 
does this add?  Also, we use it inconsistently: 
transaction_processor.calculate_mwrr_for_transactions is called directly!

Unless you can convince me off value that is being added, I think we should
retire the entire facade pattern and simply call the functions directly.

### Remnants from legacy code

batch_get_stock_prices now returns all prices in GBP.  It used to return them
in native prices and we subsequently converted to GBP.  We have some leftovers
from this that we can remove: have a look at the use of current_native_price in
ful_history_processor and periodic_review_processor, and the native price
returned by get_stock_valuations_at_date.

Aggregation rows: we used to have a horrible pattern where aggregated data for
categories and tags would be passed as faked-up rows in the dataframes with the
name starting TAG_SUMMARY.  We got rid of this, but it looks like we still
put them in but then strip them out in the reporter!  See 
periodic_review_processor lines 561-583 & 624-651, portfolio_reporter lines 329-330.

## Things to check

-   periodic_review_processor line 78-84 maps price data from new->old ticker names:
    should full_history_processor also do this?

-   For MWRR calculations, should we add fake SELL transaction for stocks we still
    hold in full_history to match what we do in periodic_review?

-   periodic_review_processor has logic to check for STOCK_CONVERIONS changing the 
    ticker name then copying prices for the new name back to the old name - see
    lines 59-84. full_history_processor doesn't appear to have this.  Does it
    need it, or is it only useful for the value_over_time function?

## Tidy-ups

### Code not exercised

-   financial_metrics.calculate_roi is defined but not used e.g. see
    full_history_processor line 224, periodic_review_processor line 317

-   ROICalculator.today is not used - we inline calls to datetime.now() in 
    various places

### Code inconsistency

-   look at create_portfolio_summaries: we pass a dataframe which includes data
    such as amount invested and received, and we additionally pass MWRR info, 
    only to copy the original dataframe adding in the MWRR data!  Why not put
    it directly into the dataframe first time?
