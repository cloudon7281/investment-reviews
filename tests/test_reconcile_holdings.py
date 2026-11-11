"""`--mode reconcile-holdings` (reconcile_holdings.py): the notes' holdings against the brokers'
holdings exports (investment-reviews#104).

The broker files here are cut-down copies of the real exports' layouts, with invented holdings: H&L's
Windows-1252 file with the account on its first line, ii's file with several byte-order marks, and
IBKR's summary with aggregate and total rows around the per-account positions.
"""

import logging
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import portfolio
import reconcile_holdings as R
import transaction_processor
from csv_parser import parse_stock_transaction_csv
from portfolio_analysis import PortfolioAnalysis

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "anonymised_test_data"

HL_ISA = """HL Stocks & Shares ISA, , , ,
Client Name:,Mr A N Other, , ,
Spreadsheet created at,11-11-2026 16:49, , ,

Stock value:,"545,501.31", , ,

Stock,Units held,Price (pence),Value (£),Cost (£),Gain/loss (£),Gain/loss (%),Day gain/loss (£),Day gain/loss (%),
"Amphenol Corp Class A Com Stk USD0.001 *R","268","6,203.32","16,624.90","14,980.89","1,644.01","10.97","496.39","3.08"
"Legal & General US Index Class C - Accumulation (GBP)","2,106.208","1,561.00","32,877.91","29,917.62","2,960.29","9.89","210.62","0.65"
"Totals","","","49,502.81","44,898.51","4,604.30","10.25","707.01","1.45"

"Shares are valued at the bid-price, delayed by 15 minutes."
"""

HL_TAXABLE = """HL Fund & Share Account, , , ,
Client Name:,Mr A N Other, , ,

Stock,Units held,Price (pence),Value (£),Cost (£),Gain/loss (£),Gain/loss (%),Day gain/loss (£),Day gain/loss (%),
"First Republic Bank USD0.01 *R","43","0.01","","6.75","-6.75","-100.00","",""
"Totals","","","0.00","6.75","-6.75","-100.00","",""
"""

II = ("\ufeff\ufeff\ufeffSymbol,Name,Qty,Price,Day Gain/Loss,Day Gain/Loss %,Market Value £,Market Value,"
      "Book Cost,Gain/Loss,Gain/Loss %,Average Price\n"
      'B0HZNB9,PIMCO GIS GlInGd Crdt Instl GBPH Acc,2169.297,£22.62,£-303.70,-0.62%,"£49,069.50",'
      '"£49,069.50","£47,988.04","£1,081.46",2.25%,£22.121471\n'
      'SSAC,iShares MSCI All Cntry WldUCITSETFUSDAcc GBP,1560,"9,149.00p","£2,418.00",1.72%,'
      '"£142,724.40","£142,724.40","£115,950.82","£26,773.58",23.09%,"7,432.7449p"\n'
      '"",,,Totals,,,,,,,,\n'
      '"",,,GBP,"£7,122.30",0.39%,"£191,793.90","£191,793.90",,,,\n')

IBKR = """\ufeffStatement,Header,Field Name,Field Value
Statement,Data,BrokerName,Interactive Brokers (U.K.) Limited
Open Positions,Header,Asset Category,Currency,Symbol,Account,Quantity,Cost Basis,Close Price,Value,Unrealized P/L
Open Positions,Data,Stocks,CAD,FTG,,2119.2103,14834.4721,33.84,71714.08,56879.607899
Open Positions,Data,Stocks,CAD,FTG,U100,2119.2103,14834.4721,33.84,71714.08,56879.607899
Open Positions,Data,Total,,,,,14834.4721,,71714.08,56879.607899
Open Positions,Data,Total in GBP,,,,,7834.233060731,,37872.9227888,30038.689727541
Open Positions,Data,Mutual Funds,GBP,IE00B43FT809,,487.81,61348.288912,126.6814,61796.46,448.171088
Open Positions,Data,Mutual Funds,GBP,IE00B43FT809,U100,399.38,50143.338912,126.6814,50594.02,450.681088
Open Positions,Data,Mutual Funds,GBP,IE00B43FT809,U200,88.43,11204.95,126.6814,11202.44,-2.51
Cash and Position Activity,Header,Currency,Name,Account,Dividends
"""

ACCOUNTS = {'U100': 'taxable', 'U200': 'isa'}


def write(tmp_path, name, text, encoding='utf-8'):
    path = tmp_path / name
    path.write_bytes(text.encode(encoding))
    return str(path)


def holding(ticker, category, units, value=None, name=None, tag=None, brokers=('HL',), sedol=None):
    return R.Holding(ticker=ticker, category=category, name=name, tag=tag, units=units,
                     value_gbp=units if value is None else value, brokers=frozenset(brokers),
                     tickers={ticker}, sedol=sedol)


def line(broker, category, identifier, units, value=None):
    return R.BrokerLine(broker, category, identifier, identifier, units,
                        units if value is None else value, 'file.csv')


def findings(rows):
    return {(r['finding'], r['ticker'] or r['stock_name']) for r in rows}


ALL_COVERED = {(b, c) for b in R.BROKERS for c in R.CATEGORIES}


# --- Arguments --------------------------------------------------------------------------------

def test_broker_files_are_read_per_broker_whatever_the_case():
    assert R.parse_broker_files_arg('hl=a.csv, b.csv;II=c.csv;IBKR=d.csv') == {
        'HL': ['a.csv', 'b.csv'], 'ii': ['c.csv'], 'IBKR': ['d.csv']}


@pytest.mark.parametrize('spec', ['HL', 'Vanguard=a.csv', 'HL=', ''])
def test_a_broker_files_argument_that_names_no_broker_and_file_is_refused(spec):
    with pytest.raises(R.ReconcileInputError):
        R.parse_broker_files_arg(spec)


def test_broker_accounts_classify_each_ibkr_account(tmp_path):
    path = write(tmp_path, 'accounts.csv', 'account,category\nU100,Taxable\nU200,ISA\n')
    assert R.read_broker_accounts(path) == ACCOUNTS


def test_a_broker_account_with_no_known_category_is_refused(tmp_path):
    path = write(tmp_path, 'accounts.csv', 'account,category\nU100,SIPP\n')
    with pytest.raises(R.ReconcileInputError, match='U100'):
        R.read_broker_accounts(path)


# --- Broker files -----------------------------------------------------------------------------

def test_an_hl_export_names_its_account_and_is_read_in_windows_1252(tmp_path):
    category, lines = R.parse_hl_file(write(tmp_path, 'isa.csv', HL_ISA, 'cp1252'))
    assert category == 'isa'
    assert [(l.identifier, l.units, l.value_gbp) for l in lines] == [
        ('Amphenol Corp Class A Com Stk USD0.001 *R', 268, 16624.90),
        ('Legal & General US Index Class C - Accumulation (GBP)', 2106.208, 32877.91)]


def test_an_hl_fund_and_share_account_is_taxable_and_a_blank_value_is_none(tmp_path):
    category, lines = R.parse_hl_file(write(tmp_path, 'fs.csv', HL_TAXABLE, 'cp1252'))
    assert category == 'taxable'
    assert [(l.units, l.value_gbp) for l in lines] == [(43, None)]


def test_an_hl_export_for_an_unknown_account_is_refused(tmp_path):
    with pytest.raises(R.ReconcileInputError, match='SIPP'):
        R.parse_hl_file(write(tmp_path, 'sipp.csv', HL_TAXABLE.replace('Fund & Share Account', 'SIPP')))


def test_an_ii_export_is_the_pension_and_its_totals_are_skipped(tmp_path):
    lines = R.parse_ii_file(write(tmp_path, 'ii.csv', II))
    assert [(l.category, l.identifier, l.units, l.value_gbp) for l in lines] == [
        ('pension', 'B0HZNB9', 2169.297, 49069.50), ('pension', 'SSAC', 1560, 142724.40)]


def test_an_ibkr_export_is_read_per_account_and_valued_in_gbp(tmp_path):
    rates = {'CAD': 0.5, 'GBP': 1.0}
    lines = R.parse_ibkr_file(write(tmp_path, 'ibkr.csv', IBKR), ACCOUNTS, rates.__getitem__)
    assert [(l.category, l.identifier, l.units, round(l.value_gbp, 2)) for l in lines] == [
        ('taxable', 'FTG', 2119.2103, 35857.04),
        ('taxable', 'IE00B43FT809', 399.38, 50594.02),
        ('isa', 'IE00B43FT809', 88.43, 11202.44)]


def test_an_ibkr_account_the_accounts_file_does_not_classify_is_refused(tmp_path):
    with pytest.raises(R.ReconcileInputError, match='U200'):
        R.parse_ibkr_file(write(tmp_path, 'ibkr.csv', IBKR), {'U100': 'taxable'}, lambda c: 1.0)


def test_an_ibkr_file_needs_the_accounts_file(tmp_path):
    with pytest.raises(R.ReconcileInputError, match='--broker-accounts'):
        R.read_broker_files({'IBKR': [write(tmp_path, 'ibkr.csv', IBKR)]}, None, lambda c: 1.0)


def test_the_files_cover_the_accounts_they_are_exports_of(tmp_path):
    _, covered = R.read_broker_files(
        {'HL': [write(tmp_path, 'fs.csv', HL_TAXABLE, 'cp1252')], 'ii': [write(tmp_path, 'ii.csv', II)],
         'IBKR': [write(tmp_path, 'ibkr.csv', IBKR)]}, ACCOUNTS, lambda c: 1.0)
    assert covered == {('HL', 'taxable'), ('ii', 'pension'), ('IBKR', 'taxable'), ('IBKR', 'isa')}


def test_the_ii_transaction_notes_keep_the_sedol():
    transactions = parse_stock_transaction_csv(str(NOTES / 'Pension' / '2025' / 'ii.csv'))
    assert {t['ticker']: t['sedol'] for t in transactions}['0P00005XM7.L'] == 'B0HZNB9'


# --- Matching ---------------------------------------------------------------------------------

def test_an_hl_line_matches_the_note_name_it_starts_with_longest_first():
    shares = holding('IWFV.L', 'taxable', 136, name='iShares IV plc')
    biotech = holding('BTEK.L', 'taxable', 10681, name='iShares plc')
    hit = R.match_line(line('HL', 'taxable', 'iShares IV plc Edge MSCI World Value Factor', 136),
                       [shares, biotech], {})
    assert hit == [shares]


def test_an_hl_note_name_must_end_at_a_word_boundary():
    assert R.match_line(line('HL', 'isa', 'Cohorts plc Ordinary', 1),
                        [holding('CHRT.L', 'isa', 1, name='Cohort')], {}) == []


def test_an_hl_line_matches_only_holdings_built_from_hl_notes():
    ibkr = holding('ARMR.L', 'taxable', 10, name='Global X', brokers=('IBKR',))
    assert R.match_line(line('HL', 'taxable', 'Global X ETFs Defence Tech', 10), [ibkr], {}) == []


def test_an_ii_line_matches_a_ticker_without_its_suffix_or_a_sedol():
    etf = holding('SSAC.L', 'pension', 1950, brokers=('ii',))
    fund = holding('0P00005XM7.L', 'pension', 2169, brokers=('ii',), sedol='B0HZNB9')
    assert R.match_line(line('ii', 'pension', 'SSAC', 1560), [etf, fund], {}) == [etf]
    assert R.match_line(line('ii', 'pension', 'B0HZNB9', 2169), [etf, fund], {}) == [fund]


def test_an_ibkr_line_matches_a_ticker_with_or_without_its_suffix():
    ftg = holding('FTG.TO', 'taxable', 2119, brokers=('IBKR',))
    fund = holding('IE00B43FT809', 'taxable', 138, brokers=('IBKR',))
    assert R.match_line(line('IBKR', 'taxable', 'FTG', 2119), [ftg, fund], {}) == [ftg]
    assert R.match_line(line('IBKR', 'taxable', 'IE00B43FT809', 399), [ftg, fund], {}) == [fund]


def test_a_holding_converted_to_a_new_ticker_matches_on_it():
    converted = holding('OLD', 'taxable', 5, brokers=('IBKR',))
    converted.tickers.add('NEW.L')
    assert R.match_line(line('IBKR', 'taxable', 'NEW', 5), [converted], {}) == [converted]


def test_an_override_names_the_holding_a_line_is():
    fund = holding('0P0000XYZ.L', 'isa', 10, name='Renamed Fund')
    overrides = {'HL': {'Its New Name Class I': '0P0000XYZ.L'}}
    assert R.match_line(line('HL', 'isa', 'Its New Name Class I', 10), [fund], overrides) == [fund]


def test_of_two_matches_the_one_still_held_wins():
    sold = holding('OLD.L', 'isa', 0, name='Fund')
    held = holding('NEW.L', 'isa', 10, name='Fund')
    assert R.match_line(line('HL', 'isa', 'Fund Class A', 10), [sold, held], {}) == [held]


# --- Findings ---------------------------------------------------------------------------------

def test_whole_units_that_agree_are_not_a_finding_whatever_the_fractions():
    rows, agreed = R.reconcile(
        [line('IBKR', 'taxable', 'FTG', 2119.2103), line('HL', 'taxable', 'BlackRock Continental Class D2', 57.380)],
        [holding('FTG.TO', 'taxable', 2119.21, brokers=('IBKR',)),
         holding('0P0000TI06.L', 'taxable', 57.0, name='BlackRock Continental')], ALL_COVERED)
    assert (rows, agreed) == ([], 2)


def test_each_kind_of_difference_is_reported_as_its_own_finding():
    lines = [
        line('ii', 'pension', 'SSAC', 1560),                                     # PCLS sale, no note
        line('HL', 'isa', 'Waverton European Capital Growth Class I', 3906.086),  # 1.02%: not minor
        line('HL', 'isa', 'Legal & General US Index Class C', 2106.208),          # 1 unit in 2,106
        line('HL', 'taxable', 'First Republic Bank USD0.01 *R', 43, value=None),  # notes have it in ISA
        line('IBKR', 'isa', 'IE00B43FT809', 88.43),                               # no note at all
        line('HL', 'isa', 'Amphenol Corp Class A', 268, value=16624.90),          # price 10% off
    ]
    holdings = [
        holding('SSAC.L', 'pension', 1950, brokers=('ii',)),
        holding('0P0001FG8T.L', 'isa', 3866.976, name='Waverton European Capital Growth'),
        holding('0P000102MM.L', 'isa', 2105.263, name='Legal & General US Index'),
        holding('FRCB', 'isa', 43, name='First Republic Bank'),
        holding('APH', 'isa', 268, value=16624.90 * 1.1, name='Amphenol Corp'),
        holding('HAG.DE', 'isa', -1, name='Hensoldt AG'),                       # sold more than bought
    ]
    rows, agreed = R.reconcile(lines, holdings, ALL_COVERED)
    assert findings(rows) == {
        (R.UNIT_DISCREPANCY, 'SSAC.L'), (R.UNIT_DISCREPANCY, '0P0001FG8T.L'),
        (R.MINOR_DIFFERENCE, '0P000102MM.L'), (R.CATEGORY_MISMATCH, 'FRCB'),
        (R.NO_NOTES, 'IE00B43FT809'), (R.VALUE_DISCREPANCY, 'APH'), (R.NOT_AT_BROKER, 'HAG.DE')}
    assert agreed == 0
    by_ticker = {r['ticker'] or r['stock_name']: r for r in rows}
    assert by_ticker['SSAC.L']['difference'] == '-390 units'
    assert by_ticker['FRCB']['account'] == 'Taxable'
    assert by_ticker['IE00B43FT809']['broker_units'] == 88
    assert [r['finding'] for r in rows] == sorted((r['finding'] for r in rows), key=R.FINDING_ORDER.index)


def test_a_holding_matched_in_its_own_category_is_not_also_a_category_mismatch():
    # IBKR holds the fund in both accounts; the notes have only the Taxable purchase
    rows, _ = R.reconcile([line('IBKR', 'taxable', 'IE00B43FT809', 399.38), line('IBKR', 'isa', 'IE00B43FT809', 88.43)],
                          [holding('IE00B43FT809', 'taxable', 138.83, brokers=('IBKR',))], ALL_COVERED)
    assert [(r['finding'], r['account']) for r in rows] == [(R.UNIT_DISCREPANCY, 'Taxable'), (R.NO_NOTES, 'ISA')]


def test_a_line_matching_two_holdings_is_reported_not_guessed():
    rows, _ = R.reconcile([line('HL', 'isa', 'Fund Class A', 10)],
                          [holding('A.L', 'isa', 10, name='Fund'), holding('B.L', 'isa', 10, name='Fund')],
                          ALL_COVERED)
    # the candidates are named in that finding, not reported again as missing from the broker
    assert [(r['finding'], r['difference']) for r in rows] == [(R.AMBIGUOUS, 'matches A.L, B.L')]


def test_lines_for_one_holding_are_summed():
    rows, agreed = R.reconcile([line('HL', 'taxable', 'Amphenol Corp Class A', 100),
                                line('HL', 'taxable', 'Amphenol Corp Class A', 66)],
                               [holding('APH', 'taxable', 166, name='Amphenol Corp')], ALL_COVERED)
    assert (rows, agreed) == ([], 1)


def test_a_holding_whose_broker_file_was_not_supplied_is_not_reported_missing():
    rows, _ = R.reconcile([], [holding('DRO.AX', 'taxable', 8500, brokers=('IBKR',)),
                               holding('HAG.DE', 'isa', -1, brokers=())], {('HL', 'isa')})
    assert findings(rows) == {(R.NOT_AT_BROKER, 'HAG.DE')}


def test_the_category_filter_applies_to_both_sides():
    rows, _ = R.reconcile([line('ii', 'pension', 'NOPE', 5)],
                          [holding('APH', 'isa', 268, name='Amphenol Corp')], ALL_COVERED,
                          include_categories=['taxable'])
    assert rows == []


def test_the_tag_filters_apply_through_the_matched_holding_but_never_hide_an_unmatched_line():
    lines = [line('HL', 'isa', 'Amphenol Corp Class A', 1), line('HL', 'isa', 'Unknown plc', 5)]
    holdings = [holding('APH', 'isa', 268, name='Amphenol Corp', tag='AI'),
                holding('CHRT.L', 'isa', 800, name='Cohort plc', tag='Defence')]
    rows, _ = R.reconcile(lines, holdings, ALL_COVERED, exclude_tags=['ai'])
    assert findings(rows) == {(R.NO_NOTES, 'Unknown plc'), (R.NOT_AT_BROKER, 'CHRT.L')}


def test_only_a_minor_difference_does_not_fail_the_run():
    assert not R.has_material_findings([{'finding': R.MINOR_DIFFERENCE}])
    assert R.has_material_findings([{'finding': R.MINOR_DIFFERENCE}, {'finding': R.NO_NOTES}])


# --- The mode, end to end ---------------------------------------------------------------------

def _priced_at_a_pound(_analysis, portfolio_review, value_over_time_days=None):
    """full-history without the market: every unit worth £1."""
    rows = []
    for category, notes in portfolio_review.stock_notes.items():
        for note in notes:
            if note.transactions:
                units = transaction_processor.calculate_transactions_through_date(
                    note.transactions, datetime.now())['units_held']
                rows.append({'ticker': note.ticker, 'account_type': 'ISA' if category == 'isa' else category.capitalize(),
                             'units_held': units, 'current_value': max(units, 0.0)})
    return {'individual_stocks': pd.DataFrame(rows)}


def test_the_mode_reports_the_anonymised_pension_against_an_ii_export(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(PortfolioAnalysis, 'process_full_history', _priced_at_a_pound)
    monkeypatch.setenv('HOME', str(tmp_path))  # the note cache lives under ~/.cache
    ii = write(tmp_path, 'ii.csv',
               "Symbol,Name,Qty,Market Value £\n"
               "BMJJJF9,HSBC FTSE All-World Index C Acc,42849.54,£42849.54\n"
               "B0HZNB9,PIMCO GIS GlInGd Crdt Instl GBPH Acc,2712.297,£2712.30\n"
               "SSAC,iShares MSCI All Cntry WldUCITSETFUSDAcc GBP,1560,£1560\n"
               "NEWF,A fund with no notes,10,£10\n")
    args = SimpleNamespace(broker_files=f'ii={ii}', broker_accounts=None, base_dir=str(NOTES),
                           rebuild_cache=True, output_file=None)
    status = portfolio.run_reconcile_holdings(args, None, None, None)
    out = capsys.readouterr().out
    assert status == portfolio.EXIT_HOLDINGS_DIFFER
    assert '4 broker lines read; 2 holdings agree' in out
    for expected in ('SSAC.L', '-390 units', 'A fund with no notes', 'AGGG.L'):
        assert expected in out
    # holdings built from H&L and IBKR notes are not reported: no file for them was supplied
    assert 'PLTR' not in out and 'FTG.TO' not in out
