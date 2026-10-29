"""The decision outcomes report (investment-reviews#96).

The cases in the requirement's section 11 come first, named after it, then the treatments
agreed in the issue: only logged trades are decisions, FIFO within an account, bed-and-ISA,
demergers, delisting, annualising and horizons.

Every case replays synthetic trades against synthetic GBP prices, and its expected figures
are worked out by hand in the test, not by the code under test.
"""

import os
import tempfile
import textwrap
import unittest
from datetime import datetime

import pandas as pd
import pyxirr

import decision_outcomes as do
from decision_log import Decision
from market_data_fetcher import MarketDataFetcher
from portfolio_review import StockNote, StockTransaction


def day(text):
    return datetime.strptime(text, '%Y-%m-%d')


def txn(kind, when, quantity, amount=0.0, new_quantity=None):
    return StockTransaction(date=day(when), transaction_type=kind, quantity=quantity,
                            price_per_share=amount / quantity if quantity else 0.0, total_amount=amount,
                            new_quantity=new_quantity, source_file=f"{kind}_{when}.pdf")


def buy(when, quantity, amount):
    return txn('BUY', when, quantity, amount)


def sell(when, quantity, amount):
    return txn('SELL', when, quantity, amount)


def holding(ticker, account, *transactions):
    return StockNote(file_path=f"/notes/{ticker}.pdf", category=account, subcategory='2025', review_date=None,
                     stock_name=ticker, ticker=ticker, transactions=list(transactions))


def decision(decided, action, ticker, start=None, end=None):
    return Decision(decision_id=f"{decided}/{action}/{ticker}", decision_date=day(decided),
                    window_start=day(start or decided), window_end=day(end or start or decided), ticker=ticker,
                    action=action, primary_reason='thesis' if action == 'buy' else 'time', secondary_reasons=(),
                    investment_type='growth', commentary=None, linked_decision_id=None, classification_version=1,
                    source_file=f"{decided}.yaml")


def closes(**by_date):
    """A GBP close series from keyword dates, e.g. closes(d2025_01_10=10.0)."""
    index = pd.DatetimeIndex([day(key[1:].replace('_', '-')) for key in by_date])
    return pd.DataFrame({'Close': list(by_date.values())}, index=index)


def run(holdings, decisions, price_data, eval_date):
    """Each decision's outcomes, keyed by decision ID and then by when it was measured."""
    stock_notes = {'isa': [], 'taxable': [], 'pension': []}
    for note in holdings:
        stock_notes[note.category].append(note)
    movements = do.follow_decisions(stock_notes, decisions)
    prices = do.Prices(price_data, do.current_tickers(stock_notes))
    outcomes = do.measure_all(decisions, movements, prices, day(eval_date))
    return {d_id: {o.measured_at: o for o in results} for d_id, results in outcomes.items()}, outcomes


class Section11(unittest.TestCase):
    """The minimum cases of the requirement's section 11, in its order."""

    def test_purchase_retained_price_doubles(self):
        d = decision('2025-01-10', 'buy', 'AAA')
        by_id, outcomes = run([holding('AAA', 'isa', buy('2025-01-10', 100, 1000.0))], [d],
                              {'AAA': closes(d2026_01_10=20.0)}, '2026-01-10')
        o = by_id[d.decision_id][do.AS_OF]
        self.assertAlmostEqual(o.total_value, 2000.0)
        self.assertAlmostEqual(o.total_return, 1.0)
        stats = do.cohort_stats([o])
        self.assertEqual((stats['x2'], stats['profitable'], stats['x5']), (1, 1, 0))

    def test_purchase_retained_price_falls_30_percent(self):
        d = decision('2025-01-10', 'buy', 'AAA')
        by_id, _ = run([holding('AAA', 'isa', buy('2025-01-10', 100, 1000.0))], [d],
                       {'AAA': closes(d2026_01_10=7.0)}, '2026-01-10')
        stats = do.cohort_stats([by_id[d.decision_id][do.AS_OF]])
        self.assertAlmostEqual(by_id[d.decision_id][do.AS_OF].total_return, -0.3)
        self.assertEqual((stats['loss_under_20'], stats['loss_20_to_50'], stats['loss_over_50']), (0, 1, 0))

    def test_purchase_fully_sold_at_profit(self):
        d = decision('2025-01-10', 'buy', 'AAA')
        by_id, _ = run([holding('AAA', 'isa', buy('2025-01-10', 100, 1000.0), sell('2025-06-02', 100, 1500.0))],
                       [d], {'AAA': closes(d2026_01_10=30.0)}, '2026-01-10')
        o = by_id[d.decision_id][do.AS_OF]
        self.assertAlmostEqual(o.realised, 1500.0)
        self.assertAlmostEqual(o.held_value, 0.0)
        self.assertAlmostEqual(o.pnl, 500.0)
        self.assertFalse(o.still_held)

    def test_purchase_partly_sold(self):
        d = decision('2025-01-10', 'buy', 'AAA')
        by_id, _ = run([holding('AAA', 'isa', buy('2025-01-10', 100, 1000.0), sell('2025-06-02', 40, 600.0))],
                       [d], {'AAA': closes(d2026_01_10=12.0)}, '2026-01-10')
        o = by_id[d.decision_id][do.AS_OF]
        self.assertAlmostEqual(o.realised, 600.0)
        self.assertAlmostEqual(o.held_value, 60 * 12.0)
        self.assertAlmostEqual(o.total_value, 600.0 + 720.0)
        self.assertTrue(o.still_held)

    def test_two_purchases_at_different_prices(self):
        """Each is measured on its own shares; a later sale takes the older shares first."""
        first, second = decision('2025-01-10', 'buy', 'AAA'), decision('2025-03-10', 'buy', 'AAA')
        trades = holding('AAA', 'isa', buy('2025-01-10', 100, 1000.0), buy('2025-03-10', 100, 2000.0),
                         sell('2025-05-12', 100, 1800.0))
        by_id, _ = run([trades], [first, second], {'AAA': closes(d2026_01_10=15.0)}, '2026-01-10')
        a, b = by_id[first.decision_id][do.AS_OF], by_id[second.decision_id][do.AS_OF]
        self.assertAlmostEqual(a.total_value, 1800.0)
        self.assertAlmostEqual(a.total_return, 0.8)
        self.assertAlmostEqual(b.total_value, 1500.0)
        self.assertAlmostEqual(b.total_return, -0.25)

    def test_sale_followed_by_50_percent_price_decline(self):
        d = decision('2025-06-02', 'sell', 'AAA')
        by_id, _ = run([holding('AAA', 'isa', buy('2024-01-10', 100, 800.0), sell('2025-06-02', 100, 1000.0))],
                       [d], {'AAA': closes(d2026_01_10=5.0)}, '2026-01-10')
        o = by_id[d.decision_id][do.AS_OF]
        self.assertAlmostEqual(o.total_value, 500.0)
        self.assertAlmostEqual(do.cohort_stats([o])['value_added'], 500.0)

    def test_sale_followed_by_100_percent_price_increase(self):
        d = decision('2025-06-02', 'sell', 'AAA')
        by_id, _ = run([holding('AAA', 'isa', buy('2024-01-10', 100, 800.0), sell('2025-06-02', 100, 1000.0))],
                       [d], {'AAA': closes(d2026_01_10=20.0)}, '2026-01-10')
        stats = do.cohort_stats([by_id[d.decision_id][do.AS_OF]])
        self.assertEqual(stats['x2'], 1)
        self.assertAlmostEqual(stats['value_added'], -1000.0)

    def test_sale_of_20_percent_of_holding(self):
        d = decision('2025-06-02', 'sell', 'AAA')
        by_id, _ = run([holding('AAA', 'isa', buy('2024-01-10', 1000, 8000.0), sell('2025-06-02', 200, 2000.0))],
                       [d], {'AAA': closes(d2026_01_10=20.0)}, '2026-01-10')
        self.assertAlmostEqual(by_id[d.decision_id][do.AS_OF].total_value, 200 * 20.0)

    def test_purchase_sold_before_six_month_horizon(self):
        d = decision('2025-01-10', 'buy', 'AAA')
        by_id, outcomes = run([holding('AAA', 'isa', buy('2025-01-10', 100, 1000.0), sell('2025-03-03', 100, 1300.0))],
                              [d], {'AAA': closes(d2025_04_10=9.0, d2026_01_10=1.0)}, '2026-01-10')
        six = by_id[d.decision_id]['6 months']
        self.assertEqual(six.date, day('2025-07-10'))
        self.assertAlmostEqual(six.total_value, 1300.0)
        self.assertAlmostEqual(six.total_return, 0.3)
        cohort = do.cohort_table([d], outcomes, '6 months')
        self.assertEqual(cohort.iloc[0]['decisions'], 1)
        self.assertEqual(cohort.iloc[0]['profitable'], 1)

    def test_decision_less_than_12_months_old(self):
        d = decision('2025-01-10', 'buy', 'AAA')
        by_id, outcomes = run([holding('AAA', 'isa', buy('2025-01-10', 100, 1000.0))], [d],
                              {'AAA': closes(d2025_04_10=11.0, d2025_07_10=12.0, d2025_12_01=13.0)}, '2025-12-01')
        self.assertEqual(sorted(by_id[d.decision_id]), ['3 months', '6 months', do.AS_OF])
        self.assertTrue(do.cohort_table([d], outcomes, '12 months').empty)

    def test_missing_historical_price(self):
        """No price within 14 days of the horizon: N/A and flagged, never a zero or a loss."""
        d = decision('2025-01-10', 'buy', 'AAA')
        by_id, _ = run([holding('AAA', 'isa', buy('2025-01-10', 100, 1000.0))], [d],
                       {'AAA': closes(d2025_01_10=10.0, d2026_01_10=12.0)}, '2026-01-10')
        three = by_id[d.decision_id]['3 months']
        self.assertIsNone(three.total_value)
        self.assertIsNone(three.total_return)
        self.assertIn('no price', three.flag)
        stats = do.cohort_stats([three])
        self.assertEqual((stats['unpriced'], stats['loss_over_50'], stats['flat']), (1, 0, 0))
        self.assertIsNone(stats['invested'])

    def test_split_or_consolidation(self):
        """Yahoo's prices are split-adjusted, so a split or a consolidation leaves value unchanged."""
        for ratio in (2, 0.1):
            with self.subTest(ratio=ratio):
                d = decision('2025-01-10', 'buy', 'AAA')
                trades = holding('AAA', 'isa', buy('2025-01-10', 100, 1000.0),
                                 txn('STOCK_CONVERSION', '2025-05-01', 100, new_quantity=100 * ratio))
                # £10 a share bought, quoted after the split at 10 / ratio
                by_id, _ = run([trades], [d], {'AAA': closes(d2026_01_10=10.0 / ratio)}, '2026-01-10')
                self.assertAlmostEqual(by_id[d.decision_id][do.AS_OF].total_value, 1000.0)

    def test_different_purchase_execution_dates(self):
        d = decision('2025-01-10', 'buy', 'AAA', '2025-01-10', '2025-01-24')
        trades = holding('AAA', 'isa', buy('2025-01-10', 100, 1000.0), buy('2025-01-24', 100, 1100.0))
        by_id, _ = run([trades], [d], {'AAA': closes(d2026_01_10=12.0)}, '2026-01-10')
        o = by_id[d.decision_id][do.AS_OF]
        expected = pyxirr.xirr([day('2025-01-10'), day('2025-01-24'), day('2026-01-10')], [-1000.0, -1100.0, 2400.0])
        self.assertAlmostEqual(o.invested, 2100.0)
        self.assertAlmostEqual(o.annualised, expected)

    def test_multiple_decisions_in_one_cohort(self):
        """The month's row is the sum of its decisions' rows."""
        first, second = decision('2025-01-10', 'buy', 'AAA'), decision('2025-01-10', 'buy', 'BBB')
        by_id, outcomes = run([holding('AAA', 'isa', buy('2025-01-10', 100, 1000.0)),
                               holding('BBB', 'isa', buy('2025-01-10', 50, 3000.0))],
                              [first, second], {'AAA': closes(d2026_01_10=15.0), 'BBB': closes(d2026_01_10=30.0)},
                              '2026-01-10')
        month = do.cohort_table([first, second], outcomes, do.AS_OF).iloc[0]
        detail = do.outcome_table([first, second], outcomes)
        detail = detail[detail.measured_at == do.AS_OF]
        self.assertEqual(month['decisions'], 2)
        self.assertAlmostEqual(month['invested'], detail['invested'].sum())
        self.assertAlmostEqual(month['pnl'], detail['pnl'].sum())
        self.assertAlmostEqual(month['pnl'], 500.0 - 1500.0)
        self.assertAlmostEqual(month['aggregate_return'], -1000.0 / 4000.0)
        self.assertEqual((month['profitable'], month['loss_20_to_50']), (1, 1))
        flows = sorted(f for o in (by_id[first.decision_id][do.AS_OF], by_id[second.decision_id][do.AS_OF])
                       for f in o.cash_flows)
        self.assertAlmostEqual(month['cohort_annualised'], pyxirr.xirr([d for d, _ in flows], [v for _, v in flows]))

    def test_multi_currency_transaction(self):
        """A US stock: paid for in GBP, valued from its USD close converted at the day's rate."""
        d = decision('2025-01-10', 'buy', 'USX')
        usd = pd.Series([10.0, 12.0], index=pd.DatetimeIndex([day('2025-01-10'), day('2026-01-10')]))
        rates = pd.Series([0.8, 0.75], index=usd.index)
        gbp = MarketDataFetcher()._convert_prices_to_gbp(usd, rates, usd.index)
        by_id, _ = run([holding('USX', 'isa', buy('2025-01-10', 100, 800.0))], [d],
                       {'USX': pd.DataFrame({'Close': gbp})}, '2026-01-10')
        o = by_id[d.decision_id][do.AS_OF]
        self.assertAlmostEqual(o.total_value, 100 * 12.0 * 0.75)
        self.assertAlmostEqual(o.total_return, 900.0 / 800.0 - 1)

    def test_decision_before_report_start_date(self):
        """Left out of the report, but its shares are still the first a later sale takes."""
        trades = holding('AAA', 'isa', buy('2025-01-10', 100, 1000.0), buy('2025-06-10', 100, 1000.0),
                         sell('2025-07-10', 100, 1200.0))
        with tempfile.TemporaryDirectory() as log_dir:
            for decided in ('2025-01-10', '2025-06-10'):
                with open(os.path.join(log_dir, f"{decided}.yaml"), 'w') as fh:
                    fh.write(textwrap.dedent(f"""\
                        classification_version: 1
                        decision_date: {decided}
                        execution_window: {{start: {decided}, end: {decided}}}
                        decisions:
                          - {{ticker: AAA, action: buy, primary_reason: thesis, investment_type: growth}}
                        """))
            results = do.process_decision_outcomes(
                FakeReview([trades]), log_dir, day('2025-03-01'), None, day('2026-01-10'),
                FakeFetcher({'AAA': closes(d2026_01_10=15.0)}))
        self.assertEqual(list(results['decisions']['decision_id']), ['2025-06-10/buy/AAA'])
        as_of = results['purchase_outcomes'][results['purchase_outcomes'].measured_at == do.AS_OF].iloc[0]
        self.assertAlmostEqual(as_of['realised'], 0.0)
        self.assertAlmostEqual(as_of['held_value'], 100 * 15.0)


class FakeReview:
    """The parsed notes, as process_decision_outcomes reads them."""

    def __init__(self, holdings):
        self.stock_notes = {'isa': [], 'taxable': [], 'pension': []}
        for note in holdings:
            self.stock_notes[note.category].append(note)


class FakeFetcher:
    """Serves fixed prices; tickers in `errors` failed to fetch."""

    def __init__(self, price_data, errors=()):
        self.price_data = price_data
        self.fetch_errors = set(errors)
        self.requested = None

    def batch_get_stock_prices(self, tickers, start_date, end_date):
        self.requested = (sorted(tickers), start_date, end_date)
        return {t: self.price_data.get(t, pd.DataFrame()) for t in tickers}


class AgreedTreatments(unittest.TestCase):
    """The treatments agreed in #96 beyond section 11."""

    def test_unlogged_trades_are_not_decisions_but_still_move_shares(self):
        """A dividend reinvestment is nobody's decision, and a later sale takes it after older lots."""
        d = decision('2025-01-10', 'buy', 'AAA')
        trades = holding('AAA', 'isa', buy('2025-01-10', 100, 1000.0), buy('2025-03-01', 5, 60.0),
                         sell('2025-06-02', 102, 1530.0))
        by_id, outcomes = run([trades], [d], {'AAA': closes(d2026_01_10=20.0)}, '2026-01-10')
        self.assertEqual(list(outcomes), [d.decision_id])
        o = by_id[d.decision_id][do.AS_OF]
        self.assertAlmostEqual(o.realised, 1530.0 * 100 / 102)
        self.assertAlmostEqual(o.held_value, 0.0)

    def test_lots_are_matched_within_each_account(self):
        """The Taxable sale takes the Taxable shares, though the ISA's are older."""
        d = decision('2025-01-10', 'buy', 'AAA')
        by_id, _ = run([holding('AAA', 'isa', buy('2025-01-10', 100, 1000.0)),
                        holding('AAA', 'taxable', buy('2025-02-03', 100, 500.0), sell('2025-06-02', 100, 1500.0))],
                       [d], {'AAA': closes(d2026_01_10=12.0)}, '2026-01-10')
        o = by_id[d.decision_id][do.AS_OF]
        self.assertAlmostEqual(o.realised, 0.0)
        self.assertAlmostEqual(o.held_value, 1200.0)

    def test_bed_and_isa_carries_the_purchase_into_the_isa(self):
        d = decision('2025-01-10', 'buy', 'AAA')
        by_id, _ = run([holding('AAA', 'taxable', buy('2025-01-10', 100, 1000.0), txn('TRANSFER', '2025-04-07', -100, -1000.0)),
                        holding('AAA', 'isa', txn('TRANSFER', '2025-04-07', 100, 1000.0), sell('2025-09-01', 100, 1700.0))],
                       [d], {'AAA': closes(d2026_01_10=30.0)}, '2026-01-10')
        o = by_id[d.decision_id][do.AS_OF]
        self.assertAlmostEqual(o.realised, 1700.0)
        self.assertAlmostEqual(o.held_value, 0.0)

    def test_demerger_shares_go_to_the_lots_held_before_it(self):
        """As Kongsberg: the parent gives up cost, the child arrives, and a same-day purchase is not entitled."""
        early, same_day = decision('2025-01-10', 'buy', 'PAR'), decision('2025-04-23', 'buy', 'PAR')
        parent = holding('PAR', 'isa', buy('2025-01-10', 100, 1000.0), buy('2025-04-23', 50, 600.0),
                         txn('TRANSFER', '2025-04-23', 0, -200.0))
        child = holding('KID', 'isa', txn('TRANSFER', '2025-04-23', 100, 200.0))
        by_id, _ = run([parent, child], [early, same_day],
                       {'PAR': closes(d2026_01_10=10.0), 'KID': closes(d2026_01_10=3.0)}, '2026-01-10')
        self.assertAlmostEqual(by_id[early.decision_id][do.AS_OF].held_value, 100 * 10.0 + 100 * 3.0)
        self.assertAlmostEqual(by_id[same_day.decision_id][do.AS_OF].held_value, 50 * 10.0)

    def test_a_share_grant_goes_to_the_lots_held_before_it(self):
        """As Teck's class B shares: new shares without a conversion, shared by the lots held."""
        d = decision('2025-01-10', 'buy', 'AAA')
        trades = holding('AAA', 'isa', buy('2024-01-10', 100, 500.0), buy('2025-01-10', 300, 3000.0),
                         txn('STOCK_CONVERSION', '2025-05-01', 0, new_quantity=40))
        by_id, _ = run([trades], [d], {'AAA': closes(d2026_01_10=10.0)}, '2026-01-10')
        self.assertAlmostEqual(by_id[d.decision_id][do.AS_OF].held_value, (300 + 30) * 10.0)

    def test_delisted_is_zero_at_as_of_and_na_at_horizons(self):
        d = decision('2025-01-10', 'buy', 'GONE')
        by_id, _ = run([holding('GONE', 'isa', buy('2025-01-10', 100, 1000.0))], [d],
                       {'GONE': pd.DataFrame()}, '2026-01-10')
        as_of, three = by_id[d.decision_id][do.AS_OF], by_id[d.decision_id]['3 months']
        self.assertAlmostEqual(as_of.total_return, -1.0)
        self.assertIn('delisted', as_of.flag)
        self.assertIsNone(three.total_value)
        self.assertIn('delisted', three.flag)

    def test_a_failed_price_fetch_fails_the_report(self):
        trades = holding('AAA', 'isa', buy('2025-01-10', 100, 1000.0))
        with tempfile.TemporaryDirectory() as log_dir:
            with open(os.path.join(log_dir, 'r.yaml'), 'w') as fh:
                fh.write("classification_version: 1\ndecision_date: 2025-01-10\n"
                         "execution_window: {start: 2025-01-10, end: 2025-01-10}\ndecisions:\n"
                         "  - {ticker: AAA, action: buy, primary_reason: thesis, investment_type: growth}\n")
            with self.assertRaises(do.PriceFetchError):
                do.process_decision_outcomes(FakeReview([trades]), log_dir, day('2025-01-01'), None,
                                             day('2026-01-10'), FakeFetcher({}, errors=['AAA']))

    def test_annualised_returns_wait_three_months(self):
        d = decision('2025-11-01', 'buy', 'AAA')
        by_id, _ = run([holding('AAA', 'isa', buy('2025-11-01', 100, 1000.0))], [d],
                       {'AAA': closes(d2026_01_10=12.0)}, '2026-01-10')
        o = by_id[d.decision_id][do.AS_OF]
        self.assertAlmostEqual(o.total_return, 0.2)
        self.assertIsNone(o.annualised)

    def test_horizons_are_calendar_months_clamped_to_month_end(self):
        d = decision('2025-08-31', 'buy', 'AAA')
        by_id, _ = run([holding('AAA', 'isa', buy('2025-08-31', 100, 1000.0))], [d],
                       {'AAA': closes(d2025_11_28=10.0, d2026_02_27=11.0)}, '2026-03-10')
        self.assertEqual(by_id[d.decision_id]['6 months'].date, day('2026-02-28'))

    def test_a_flat_outcome_is_neither_a_gain_nor_a_loss(self):
        d = decision('2025-01-10', 'buy', 'AAA')
        by_id, _ = run([holding('AAA', 'isa', buy('2025-01-10', 100, 1000.0))], [d],
                       {'AAA': closes(d2026_01_10=10.0)}, '2026-01-10')
        stats = do.cohort_stats([by_id[d.decision_id][do.AS_OF]])
        self.assertEqual((stats['flat'], stats['profitable'], stats['loss_under_20']), (1, 0, 0))

    def test_a_trade_after_a_horizon_does_not_change_it(self):
        d = decision('2025-01-10', 'buy', 'AAA')
        by_id, _ = run([holding('AAA', 'isa', buy('2025-01-10', 100, 1000.0), sell('2025-09-01', 100, 2500.0))],
                       [d], {'AAA': closes(d2025_04_10=11.0, d2025_07_10=13.0, d2026_01_10=1.0)}, '2026-01-10')
        six = by_id[d.decision_id]['6 months']
        self.assertAlmostEqual(six.realised, 0.0)
        self.assertAlmostEqual(six.held_value, 100 * 13.0)
        self.assertAlmostEqual(by_id[d.decision_id][do.AS_OF].realised, 2500.0)

    def test_the_20_to_50_percent_loss_band_includes_both_ends(self):
        for close, band in ((8.0, 'loss_20_to_50'), (5.0, 'loss_20_to_50'), (4.99, 'loss_over_50'),
                            (8.01, 'loss_under_20')):
            with self.subTest(close=close):
                d = decision('2025-01-10', 'buy', 'AAA')
                by_id, _ = run([holding('AAA', 'isa', buy('2025-01-10', 100, 1000.0))], [d],
                               {'AAA': closes(d2026_01_10=close)}, '2026-01-10')
                stats = do.cohort_stats([by_id[d.decision_id][do.AS_OF]])
                bands = {k: stats[k] for k in ('loss_under_20', 'loss_20_to_50', 'loss_over_50')}
                self.assertEqual(bands, {k: int(k == band) for k in bands})

    def test_a_sale_measures_only_its_own_trades_shares(self):
        """A later purchase of the same stock does not change what the sold shares would be worth."""
        d = decision('2025-06-02', 'sell', 'AAA')
        trades = holding('AAA', 'isa', buy('2024-01-10', 100, 800.0), sell('2025-06-02', 100, 1000.0),
                         buy('2025-08-01', 300, 3000.0))
        by_id, _ = run([trades], [d], {'AAA': closes(d2026_01_10=12.0)}, '2026-01-10')
        self.assertAlmostEqual(by_id[d.decision_id][do.AS_OF].total_value, 1200.0)


if __name__ == "__main__":
    unittest.main()
