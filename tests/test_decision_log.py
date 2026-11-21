"""The decision log: classification, validation and linking to trades (investment-reviews#96).

The cases in the requirement's Amendment 6 come first, named after it, then the linking rules.
Each test writes real log files to a temporary directory and loads them the way a run does.
"""

import os
import tempfile
import textwrap
import unittest
from datetime import datetime
from unittest import mock

import decision_log
from decision_log import DecisionLogError, Trade, link_decisions, load_decision_log


def entry(ticker, action, primary, investment_type='growth', **fields):
    lines = [f"  - ticker: {ticker}", f"    action: {action}", f"    primary_reason: {primary}",
             f"    investment_type: {investment_type}"]
    lines += [f"    {key}: {value}" for key, value in fields.items()]
    return "\n".join(lines)


def log_file(decision_date, start, end, *entries, version=1):
    return textwrap.dedent(f"""\
        classification_version: {version}
        decision_date: {decision_date}
        execution_window: {{start: {start}, end: {end}}}
        decisions:
        """) + "\n".join(entries) + "\n"


def trade(ticker, action, day, account='isa', quantity=10, value=1000.0, source='note.pdf'):
    return Trade(stock_name=ticker, ticker=ticker, account=account, date=datetime.strptime(day, '%Y-%m-%d'),
                 action=action, quantity=quantity, value=value, source_file=source)


class LogTestCase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, content):
        with open(os.path.join(self.dir, name), 'w') as fh:
            fh.write(content)

    def load(self):
        return load_decision_log(self.dir)

    def problems(self):
        with self.assertRaises(DecisionLogError) as caught:
            self.load()
        return caught.exception.problems

    def assertRejected(self, fragment):
        problems = self.problems()
        self.assertTrue(any(fragment in p for p in problems), problems)


class Amendment6(LogTestCase):
    """The minimum cases the requirement lists for classification."""

    def test_valid_purchase_classification_is_accepted(self):
        self.write('2026-11-02.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13',
                                                entry('RHM.DE', 'buy', 'thesis', secondary_reasons='[valuation]',
                                                      commentary='Re-rating of European defence.')))
        [d] = self.load()
        self.assertEqual(d.decision_id, '2026-11-02/buy/RHM.DE')
        self.assertEqual((d.action, d.primary_reason, d.secondary_reasons, d.investment_type),
                         ('buy', 'thesis', ('valuation',), 'growth'))
        self.assertEqual(d.commentary, 'Re-rating of European defence.')
        self.assertEqual(d.classification_version, 1)
        self.assertEqual((d.window_start, d.window_end), (datetime(2026, 11, 2), datetime(2026, 11, 13)))

    def test_valid_sale_classification_is_accepted(self):
        self.write('r.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13',
                                      entry('PLTR', 'sell', 'profit-take', secondary_reasons='[rebalance]')))
        [d] = self.load()
        self.assertEqual((d.action, d.primary_reason, d.secondary_reasons), ('sell', 'profit-take', ('rebalance',)))

    def test_purchase_using_a_sale_only_reason_is_rejected(self):
        self.write('r.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13', entry('RHM.DE', 'buy', 'profit-take')))
        self.assertRejected("primary_reason 'profit-take' is not a buy reason")

    def test_sale_using_a_purchase_only_reason_is_rejected(self):
        self.write('r.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13', entry('PLTR', 'sell', 'thesis')))
        self.assertRejected("primary_reason 'thesis' is not a sell reason")

    def test_a_secondary_reason_from_the_other_action_is_rejected(self):
        self.write('r.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13',
                                      entry('PLTR', 'sell', 'profit-take', secondary_reasons='[moonshot]')))
        self.assertRejected("secondary reason 'moonshot' is not a sell reason")

    def test_duplicate_secondary_reason_is_rejected(self):
        self.write('r.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13',
                                      entry('RHM.DE', 'buy', 'thesis', secondary_reasons='[valuation, valuation]')))
        self.assertRejected("duplicate secondary reasons ['valuation']")

    def test_primary_reason_duplicated_as_secondary_is_rejected(self):
        self.write('r.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13',
                                      entry('RHM.DE', 'buy', 'thesis', secondary_reasons='[thesis]')))
        self.assertRejected("primary reason 'thesis' is repeated as a secondary reason")

    def test_invalid_investment_type_is_rejected(self):
        self.write('r.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13',
                                      entry('RHM.DE', 'buy', 'thesis', investment_type='speculative')))
        self.assertRejected("investment_type must be one of core, growth, moonshot, not 'speculative'")

    def test_moonshot_purchase_classified_as_valuation_keeps_its_investment_type(self):
        self.write('r.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13',
                                      entry('AEVA', 'buy', 'valuation', investment_type='moonshot',
                                            secondary_reasons='[moonshot]')))
        [d] = self.load()
        self.assertEqual((d.primary_reason, d.secondary_reasons, d.investment_type),
                         ('valuation', ('moonshot',), 'moonshot'))

    def test_multiple_transactions_linked_to_one_decision(self):
        self.write('r.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13', entry('RHM.DE', 'buy', 'thesis')))
        decisions = self.load()
        trades = [trade('RHM.DE', 'buy', '2026-11-03', 'isa'), trade('RHM.DE', 'buy', '2026-11-05', 'taxable')]
        links = link_decisions(decisions, trades)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(links.trades_by_decision['2026-11-02/buy/RHM.DE'], trades)
        self.assertEqual(links.unlogged, [])

    def test_multiple_decisions_for_the_same_security_keep_independent_classifications(self):
        self.write('a.yaml', log_file('2026-10-01', '2026-10-01', '2026-10-10',
                                      entry('RHM.DE', 'buy', 'thesis', investment_type='growth')))
        self.write('b.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13',
                                      entry('RHM.DE', 'buy', 'valuation', investment_type='core')))
        october, november = self.load()
        self.assertEqual((october.primary_reason, october.investment_type), ('thesis', 'growth'))
        self.assertEqual((november.primary_reason, november.investment_type), ('valuation', 'core'))
        first, second = trade('RHM.DE', 'buy', '2026-10-02'), trade('RHM.DE', 'buy', '2026-11-04')
        links = link_decisions([october, november], [first, second])
        self.assertEqual(links.trades_by_decision[october.decision_id], [first])
        self.assertEqual(links.trades_by_decision[november.decision_id], [second])

    def test_historical_transaction_without_classification_stays_reportable(self):
        """A trade before the log starts is neither linked nor flagged as unlogged."""
        self.write('r.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13', entry('RHM.DE', 'buy', 'thesis')))
        old = trade('MSFT', 'buy', '2024-03-15')
        links = link_decisions(self.load(), [old])
        self.assertEqual(links.unlogged, [])
        self.assertNotIn(old, [t for ts in links.trades_by_decision.values() for t in ts])

    def test_historical_classification_supplied_later_links_without_changing_the_trades(self):
        past = trade('MSFT', 'buy', '2024-03-15')
        trades = [past]
        before = list(trades)
        self.assertEqual(link_decisions(self.load(), trades).trades_by_decision, {})
        self.write('2024-03-12.yaml', log_file('2024-03-12', '2024-03-12', '2024-03-22', entry('MSFT', 'buy', 'thesis')))
        links = link_decisions(self.load(), trades)
        self.assertEqual(links.trades_by_decision['2024-03-12/buy/MSFT'], [past])
        self.assertEqual(trades, before)

    def test_linked_replacement_decisions_trace_both_ways(self):
        self.write('r.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13',
                                      entry('TECK', 'sell', 'better-expression-available'),
                                      entry('FCX', 'buy', 'replacement', linked_decision_id='2026-11-02/sell/TECK')))
        decisions = self.load()
        buy = next(d for d in decisions if d.action == 'buy')
        self.assertEqual(buy.linked_decision_id, '2026-11-02/sell/TECK')
        self.assertEqual(link_decisions(decisions, []).linked_from, {'2026-11-02/sell/TECK': ['2026-11-02/buy/FCX']})

    def test_historical_taxonomy_version_remains_interpretable(self):
        """A later version that drops a code leaves records made under the earlier one valid."""
        v2 = {**decision_log.CLASSIFICATION_VERSIONS[1]}
        v2['sell'] = {k: v for k, v in v2['sell'].items() if k != 'time'}
        with mock.patch.dict(decision_log.CLASSIFICATION_VERSIONS, {2: v2}):
            self.write('old.yaml', log_file('2026-10-01', '2026-10-01', '2026-10-10', entry('PLTR', 'sell', 'time')))
            [d] = self.load()
            self.assertEqual((d.primary_reason, d.classification_version), ('time', 1))
            self.write('new.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13',
                                            entry('MSFT', 'sell', 'time'), version=2))
            self.assertRejected("primary_reason 'time' is not a sell reason")

    def test_subsequent_trades_do_not_modify_the_classification(self):
        """Linking reads no prices and returns the records unchanged, whatever the trades did."""
        self.write('r.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13', entry('RHM.DE', 'buy', 'thesis')))
        decisions = self.load()
        link_decisions(decisions, [trade('RHM.DE', 'buy', '2026-11-03', value=1000.0),
                                   trade('RHM.DE', 'sell', '2027-11-03', value=10.0)])
        self.assertEqual(decisions, self.load())


class Validation(LogTestCase):

    def test_other_is_a_valid_reason_for_both_actions(self):
        self.write('r.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13',
                                      entry('RHM.DE', 'buy', 'other'), entry('PLTR', 'sell', 'other')))
        self.assertEqual([d.primary_reason for d in self.load()], ['other', 'other'])

    def test_overlapping_windows_for_the_same_stock_and_action_are_rejected(self):
        self.write('a.yaml', log_file('2026-10-01', '2026-10-01', '2026-10-10', entry('RHM.DE', 'buy', 'thesis')))
        self.write('b.yaml', log_file('2026-10-10', '2026-10-10', '2026-10-20', entry('RHM.DE', 'buy', 'valuation')))
        self.assertRejected("2026-10-01/buy/RHM.DE and 2026-10-10/buy/RHM.DE: execution windows overlap")

    def test_overlapping_windows_are_allowed_for_different_stocks_or_actions(self):
        self.write('a.yaml', log_file('2026-10-01', '2026-10-01', '2026-10-10', entry('RHM.DE', 'buy', 'thesis')))
        self.write('b.yaml', log_file('2026-10-05', '2026-10-05', '2026-10-20',
                                      entry('RHM.DE', 'sell', 'profit-take'), entry('MSFT', 'buy', 'thesis')))
        self.assertEqual(len(self.load()), 3)

    def test_adjacent_windows_do_not_overlap(self):
        self.write('a.yaml', log_file('2026-10-01', '2026-10-01', '2026-10-10', entry('RHM.DE', 'buy', 'thesis')))
        self.write('b.yaml', log_file('2026-10-11', '2026-10-11', '2026-10-20', entry('RHM.DE', 'buy', 'thesis')))
        self.assertEqual(len(self.load()), 2)

    def test_a_link_to_an_unrecorded_decision_is_rejected(self):
        self.write('r.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13',
                                      entry('FCX', 'buy', 'replacement', linked_decision_id='2026-11-02/sell/TECK')))
        self.assertRejected("linked_decision_id '2026-11-02/sell/TECK' is not a recorded decision")

    def test_an_unknown_field_is_rejected(self):
        self.write('r.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13',
                                      entry('RHM.DE', 'buy', 'thesis', secondary_reason='[valuation]')))
        self.assertRejected("unknown field 'secondary_reason'")

    def test_a_missing_required_field_is_rejected(self):
        self.write('r.yaml', textwrap.dedent("""\
            classification_version: 1
            decision_date: 2026-11-02
            execution_window: {start: 2026-11-02, end: 2026-11-13}
            decisions:
              - ticker: RHM.DE
                action: buy
                primary_reason: thesis
            """))
        self.assertRejected("missing field 'investment_type'")

    def test_an_unknown_classification_version_is_rejected(self):
        self.write('r.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13', entry('RHM.DE', 'buy', 'thesis'),
                                      version=9))
        self.assertRejected("unknown classification_version 9")

    def test_a_window_that_ends_before_it_starts_is_rejected(self):
        self.write('r.yaml', log_file('2026-11-02', '2026-11-13', '2026-11-02', entry('RHM.DE', 'buy', 'thesis')))
        self.assertRejected("execution_window starts after it ends")

    def test_the_same_decision_recorded_twice_is_rejected(self):
        self.write('r.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13',
                                      entry('RHM.DE', 'buy', 'thesis'), entry('RHM.DE', 'buy', 'valuation')))
        self.assertRejected("2026-11-02/buy/RHM.DE: recorded twice")

    def test_every_fault_is_reported_not_just_the_first(self):
        self.write('a.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13', entry('RHM.DE', 'buy', 'profit-take')))
        self.write('b.yaml', log_file('2026-12-01', '2026-12-01', '2026-12-10', entry('PLTR', 'sell', 'thesis')))
        problems = self.problems()
        self.assertTrue(any(p.startswith('a.yaml') for p in problems), problems)
        self.assertTrue(any(p.startswith('b.yaml') for p in problems), problems)

    def test_a_missing_directory_is_an_empty_log(self):
        self.assertEqual(load_decision_log(os.path.join(self.dir, 'absent')), [])


class Linking(LogTestCase):

    def setUp(self):
        super().setUp()
        self.write('r.yaml', log_file('2026-11-02', '2026-11-02', '2026-11-13',
                                      entry('RHM.DE', 'buy', 'thesis'), entry('XYZ', 'buy', 'thesis')))
        self.decisions = self.load()

    def test_the_window_includes_both_ends(self):
        first, last = trade('RHM.DE', 'buy', '2026-11-02'), trade('RHM.DE', 'buy', '2026-11-13')
        links = link_decisions(self.decisions, [first, last])
        self.assertEqual(links.trades_by_decision['2026-11-02/buy/RHM.DE'], [first, last])

    def test_a_decision_with_no_trade_is_not_executed(self):
        links = link_decisions(self.decisions, [trade('RHM.DE', 'buy', '2026-11-03')])
        self.assertEqual([d.decision_id for d in links.not_executed], ['2026-11-02/buy/XYZ'])

    def test_trades_the_log_does_not_cover_are_unlogged(self):
        wrong_action = trade('RHM.DE', 'sell', '2026-11-03')
        outside_window = trade('RHM.DE', 'buy', '2026-11-14')
        other_stock = trade('MSFT', 'buy', '2026-11-03')
        before_log = trade('MSFT', 'buy', '2026-11-01')
        links = link_decisions(self.decisions, [wrong_action, outside_window, other_stock, before_log])
        self.assertEqual(links.unlogged, [wrong_action, outside_window, other_stock])

    def test_trades_from_reads_buys_and_sells_only(self):
        txn = lambda kind: mock.Mock(transaction_type=kind, date=datetime(2026, 11, 3), quantity=1,
                                     total_amount=1.0, source_file=f'{kind}.pdf')
        note = mock.Mock(stock_name='Rheinmetall AG', ticker='RHM.DE',
                         transactions=[txn('BUY'), txn('SELL'), txn('TRANSFER'), txn('STOCK_CONVERSION')])
        review = mock.Mock(stock_notes={'isa': [note]})
        self.assertEqual([(t.action, t.source_file) for t in decision_log.trades_from(review)],
                         [('buy', 'BUY.pdf'), ('sell', 'SELL.pdf')])


if __name__ == '__main__':
    unittest.main()


def entry_v2(ticker, action, primary, investment_class='alpha', criterion='mispricing', **fields):
    lines = [f"  - ticker: {ticker}", f"    action: {action}", f"    primary_reason: {primary}",
             f"    investment_class: {investment_class}"]
    if criterion is not None:
        lines.append(f"    criterion: {criterion}")
    lines += [f"    {key}: {value}" for key, value in fields.items()]
    return "\n".join(lines)


class ClassificationVersion2(LogTestCase):
    """Version 2 (investment-analysis#1, Phase 7d; Operations Brief v1.3 §8): investment_class, and a criterion for
    alpha, in place of investment_type; the low-volatility sale reason retired. Version 1 files stay as they are."""

    def write_v2(self, *entries):
        self.write('2026-11-23.yaml', log_file('2026-11-23', '2026-11-23', '2026-12-04', *entries, version=2))

    def test_an_alpha_decision_carries_its_criterion_and_other_classes_none(self):
        self.write_v2(entry_v2('RHM.DE', 'buy', 'thesis', criterion='accelerating-leader'),
                      entry_v2('VWRP.L', 'buy', 'rebalance', investment_class='pure-beta', criterion=None),
                      entry_v2('DFNS.L', 'sell', 'rebalance', investment_class='beta-plus', criterion=None))
        by_ticker = {d.ticker: d for d in self.load()}
        self.assertEqual({t: (d.investment_class, d.criterion, d.investment_type, d.classification_version)
                          for t, d in by_ticker.items()},
                         {'RHM.DE': ('alpha', 'accelerating-leader', None, 2),
                          'VWRP.L': ('pure-beta', None, None, 2), 'DFNS.L': ('beta-plus', None, None, 2)})

    def test_an_alpha_decision_without_a_criterion_is_rejected(self):
        self.write_v2(entry_v2('RHM.DE', 'buy', 'thesis', criterion=None))
        self.assertRejected("an alpha decision needs a criterion, one of mispricing, accelerating-leader, "
                            "disruptive-technology")

    def test_a_criterion_on_a_decision_that_is_not_alpha_is_rejected(self):
        self.write_v2(entry_v2('VWRP.L', 'buy', 'rebalance', investment_class='pure-beta'))
        self.assertRejected("criterion is for alpha decisions only, not pure-beta")

    def test_an_unknown_class_or_criterion_is_rejected(self):
        self.write_v2(entry_v2('RHM.DE', 'buy', 'thesis', investment_class='growth', criterion=None))
        self.assertRejected("investment_class must be one of pure-beta, beta-plus, alpha, not 'growth'")
        self.write_v2(entry_v2('RHM.DE', 'buy', 'thesis', criterion='moonshot'))
        self.assertRejected("criterion must be one of mispricing, accelerating-leader, disruptive-technology, "
                            "not 'moonshot'")

    def test_each_version_has_its_own_fields(self):
        self.write_v2(entry_v2('RHM.DE', 'buy', 'thesis', investment_type='growth'))
        self.assertRejected("unknown field 'investment_type'")
        self.write_v2("  - {ticker: RHM.DE, action: buy, primary_reason: thesis}")
        self.assertRejected("missing field 'investment_class'")
        os.remove(os.path.join(self.dir, '2026-11-23.yaml'))
        self.write('old.yaml', log_file('2026-10-01', '2026-10-01', '2026-10-10',
                                        entry('RHM.DE', 'buy', 'thesis', investment_class='alpha')))
        self.assertRejected("unknown field 'investment_class'")

    def test_the_low_volatility_reason_is_retired_in_version_2_but_stays_valid_in_version_1(self):
        self.write('old.yaml', log_file('2026-10-01', '2026-10-01', '2026-10-10', entry('PLTR', 'sell', 'low-volatility')))
        [d] = self.load()
        self.assertEqual((d.primary_reason, d.classification_version), ('low-volatility', 1))
        self.write_v2(entry_v2('MSFT', 'sell', 'low-volatility'))
        self.assertRejected("primary_reason 'low-volatility' is not a sell reason")

    def test_a_version_1_moonshot_reports_as_alpha_disruptive_technology_and_growth_and_core_stay_unclassified(self):
        self.write('old.yaml', log_file('2026-10-01', '2026-10-01', '2026-10-10',
                                        entry('AEVA', 'buy', 'moonshot', investment_type='moonshot'),
                                        entry('RHM.DE', 'buy', 'thesis', investment_type='growth'),
                                        entry('VWRP.L', 'buy', 'rebalance', investment_type='core')))
        self.assertEqual({d.ticker: (d.investment_type, d.investment_class, d.criterion) for d in self.load()},
                         {'AEVA': ('moonshot', 'alpha', 'disruptive-technology'),
                          'RHM.DE': ('growth', None, None), 'VWRP.L': ('core', None, None)})

    def test_both_versions_report_together_with_their_class_and_criterion(self):
        self.write('old.yaml', log_file('2026-10-01', '2026-10-01', '2026-10-10',
                                        entry('AEVA', 'buy', 'moonshot', investment_type='moonshot')))
        self.write_v2(entry_v2('RHM.DE', 'buy', 'thesis'))
        decisions = self.load()
        table = decision_log.check_tables(decisions, link_decisions(decisions, []))['decisions']
        cells = table[['ticker', 'investment_type', 'investment_class', 'criterion']]
        self.assertEqual(cells.astype(object).where(cells.notna(), None).values.tolist(),          # missing as None
                         [['AEVA', 'moonshot', 'alpha', 'disruptive-technology'], ['RHM.DE', None, 'alpha', 'mispricing']])
