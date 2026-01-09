"""
Various mappings used to get the correct ticker name; a mix of:
- TICKER_MAPPING when the stock note has no ticker code
- EXCHANGE_SUFFIX_MAP for appending the correct exchange suffix to the ticker name
- SPECIAL_EXCHANGE_SUFFIX_MAP for special cases where there are multiple bourses for the same country
"""

TICKER_MAPPING = {
    'Rocket Lab USA Inc': 'RKLB',
    'Barrick Gold Corp': 'ABX.TO',
    'Celestica Inc': 'CLS.TO',
    'Artemis US Smaller Companies': '0P00013YAP.L',
    'Rathbone Global Opportunities': '0P0001FE43.L',
    'Blackrock ICS Sterling Liquidity': '0P0000UHZA.L',
    #'AXA Framlington American Growth': '0P00000DJJ.L',
    'AXA Framlington American Growth': '0P0000VKOU.L', # was converted from class R to class Z
    'Man GLG Japan CoreAlpha': '0P0000810W.L',
    #'ASI Latin American Equity': '0P0000SHRZ.L',
    'ASI Latin American Equity': '0P0000XOMV.L', # ASI was renamed abrdn and with a stock conversion
    'abrdn Latin American Equity': '0P0000XOMV.L',
    'Polar Capital Biotechnology': '0P0000ZVG5',  # Converted from IE00B42P0H75 on 2020-11-24
    'Threadneedle European Select': '0P0000X3IE.L',
    'Waverton European Capital Growth': '0P0001FG8T.L',
    'Smith & Williamson Artificial Intelligence': '0P0001PGKI.L',
    'Landseer Global Artificial Intelligence': '0P0001PGKI.L',
    'AXA Framlington Global Technology Fund': '0P0000XNBQ.L',
    'Legal & General US Index': '0P000102MM.L',
    'GS India Equity Portfolio': '0P0000XTCF.L',
    #'JPMorgan Emerging Markets': '0P0000K7VW.L',
    'JPMorgan Emerging Markets': '0P000013TQ.L', # was converted from class B to class C
    'Baillie Gifford High Yield Bond': '0P000090AH.L',
    'Jupiter Global Value Equity': '0P0001CWV4.L',
    'FSSA Global Emerging Markets Focus': '0P0001EEMN.L',
    'Kensington Capital Acquisition Corp': 'QS',
    'Piedmont Lithium Ltd': 'PLL',
    'Lucid Group Inc': 'LCID',
    'Kwesst Micro Systems Inc': 'KWE',
    'Skillz Inc': 'SKLZ', 
    'Invesco Perpetual High Income': '0P00000DII.L',
    'Churchill Capital Corp IV': 'LCID',
    'Federal Realty Investment Trust': '0IL1.L',
    'Workhorse Group Inc': '1WO.BE',
    'Everbridge Inc': 'EVBG',
    'Hennessy Capital Acquisition Corp IV': 'GOEV',
    'M&G Global Macro Bond': '0P0000UR3O.L',
    'Rathbone Ethical Bond': '0P0001D2M9.L',
    } 

# UK tickers that YF returns with currency='GBP' but are actually priced in POUNDS (not pence)
# Most UK funds return currency='GBP' but prices are in PENCE (requiring /100 conversion)
# This list contains the EXCEPTIONS where YF returns 'GBP' and prices are truly in pounds
# 
# Maintenance: If a UK ticker shows 100x valuation errors, it's likely incorrectly in this list
# Audit was last run: 2025-10-12
UK_TICKERS_IN_POUNDS = [
                        # UK Funds - GBP in pounds (verified 2025-10-12)
                        '0P00013YAP.L',  # Artemis US Smaller Companies
                        '0P0001FE43.L',  # Rathbone Global Opportunities
                        '0P0000VKOU.L',  # AXA Framlington American Growth
                        '0P0000810W.L',  # Man GLG Japan CoreAlpha
                        '0P0000XOMV.L',  # abrdn Latin American Equity
                        '0P0000X3IE.L',  # Threadneedle European Select
                        '0P0001FG8T.L',  # Waverton European Capital Growth
                        '0P0001PGKI.L',  # Smith & Williamson Artificial Intelligence
                        '0P0000XNBQ.L',  # AXA Framlington Global Technology
                        '0P000102MM.L',  # Legal & General US Index
                        '0P000090AH.L',  # Baillie Gifford High Yield Bond
                        # REMOVED 2025-10-13: YF actually returns these in PENCE, not pounds
                        # '0P000013TQ.L',  # JPMorgan Emerging Markets
                        # '0P0001CWV4.L',  # Jupiter Global Value Equity
                        '0P0001EEMN.L',  # FSSA Global Emerging Markets Focus
                        '0P0001D2M9.L',  # Rathbone Ethical Bond
                        '0P0000UR3O.L',  # M&G Global Macro Bond
                        '0P00018MM4.L',  # Fidelity Cash W Acc (Pension)
                        '0P0000Z8P7.L',  # Royal London Short Term Money Mkt Y Acc (Pension)
                        '0P00013P6I.L',  # HSBC FTSE All-World Index C Acc
                        ]

# Mapping from country code (first 2 chars of ISIN) to exchange suffix
EXCHANGE_SUFFIX_MAP = {
    'US': '',  # US stocks have no suffix
    'GB': '.L',  # London Stock Exchange
    'DE': '.DE',  # Deutsche Börse
    'FR': '.PA',  # Euronext Paris
    'IT': '.MI',  # Borsa Italiana
    'CA': '.V'  # Vancouver
}

# Special case mapping for tickers that need different exchange suffixes
SPECIAL_EXCHANGE_SUFFIX_MAP = {
    'ASML': '.AS',  # ASML trades on Euronext Amsterdam despite being a Dutch company
    'ING': '.AS',   # ING trades on Euronext Amsterdam
    'KPN': '.AS',   # KPN trades on Euronext Amsterdam
    'NN': '.AS',    # NN Group trades on Euronext Amsterdam
    'UNA': '.AS',   # Unilever trades on Euronext Amsterdam
    'UBS': '.SW',   # UBS trades on SIX Swiss Exchange
    'NOVN': '.SW',  # Novartis trades on SIX Swiss Exchange
    'ROG': '.SW',   # Roche trades on SIX Swiss Exchange
    'NESN': '.SW',  # Nestle trades on SIX Swiss Exchange
    'MAL': '.TO',   # Magellan trades on the Toronto Stock Exchange
    'TECK': '',     # Teck is just weird
    'BYDDY': '',    # BYD has no suffix
    'PGY': '',      # Pagaya has no suffix
    'FTG': '.TO',   # FTG is FTGFF in Toronto
    'NATO': '.L',   # NATO is NATO.L in London
    'IDFN': '.L',   # IDFN is IDFN.L in London
    'DFNS': '.L',   # DFNS is DFNS.L in London
    'PRIUA': '.PR', # Primoco is PRIUA.PR in Prague
    'GOMX': '.ST',  # GOMX is GOMX.ST in Stockholm
    'MILDEF': '.ST',# MILDEF is MILDEF.ST in Stockholm
    'KOG': '.OL',   # KOG is KOG.OL in Oslo
    'POET': '',     # POET has no suffix
    'CLS': '.TO',   # CLS is CLS.TO in Toronto
    'SSLV': '.L',   # SSLV is SSLV.L in London
}

STOCK_RENAME_MAP = {
    #'KWE':'DFSC'    # Kwesst renamed to Defense Security
}
