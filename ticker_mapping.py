"""
Various mappings used to get the correct ticker name; a mix of:
- TICKER_MAPPING when the stock note has no ticker code
- EXCHANGE_SUFFIX_MAP for appending the correct exchange suffix to the ticker name
- SPECIAL_EXCHANGE_SUFFIX_MAP for special cases where there are multiple bourses for the same country
"""

TICKER_MAPPING = {
    'abrdn Latin American Equity': '0P0000XOMV.L',
    'Artemis US Smaller Companies': '0P00013YAP.L',
    'ASI Latin American Equity': '0P0000XOMV.L', # ASI was renamed abrdn and with a stock conversion
    'AXA Framlington American Growth': '0P0000VKOU.L', # was converted from class R to class Z
    'AXA Framlington Global Technology Fund': '0P0000XNBQ.L',
    'Baillie Gifford High Yield Bond': '0P000090AH.L',
    'Baillie Gifford American': '0P00000VC9.L',
    'Barrick Gold Corp': 'ABX.TO',
    'BlackRock Continental European Flexible': '0P0000TI06.L',
    'BlackRock European Dynamic Fund': '0P0000ZZBQ.L',
    'Blackrock ICS Sterling Liquidity': '0P0000UHZA.L',
    'Celestica Inc': 'CLS.TO',
    'Churchill Capital Corp IV': 'LCID',
    'CT European Select': '0P0000X3IE.L',
    'DEFSEC Technologies Inc': 'DFSC',
    'Everbridge Inc': 'EVBG',
    'Federal Realty Investment Trust': '0IL1.L',
    'FSSA Global Emerging Markets Focus': '0P0001EEMN.L',
    'Fundsmith Equity': '0P0000RU81.L',
    'GS India Equity Portfolio': '0P0000XTCF.L',
    'Hennessy Capital Acquisition Corp IV': 'GOEV',
    'Invesco Perpetual High Income': '0P00000DII.L',
    'JPMorgan Emerging Markets': '0P000013TQ.L', # was converted from class B to class C
    'Jupiter Global Value Equity': '0P0001CWV4.L',
    'Jupiter India': '0P00018LFD.L',
    'Kensington Capital Acquisition Corp': 'QS',
    'Kwesst Micro Systems Inc': 'KWE',
    'Landseer Global Artificial Intelligence': '0P0001PGKI.L',
    'Legal & General US Index': '0P000102MM.L',
    'Lucid Group Inc': 'LCID',
    'M&G Global Macro Bond': '0P0000UR3O.L',
    'M&G Japan': '0P0000WN3Z.L',
    'Man GLG Japan CoreAlpha': '0P0000810W.L',
    'Man Japan CoreAlpha': '0P0000810W.L',
    'Piedmont Lithium Ltd': 'PLL',
    'Polar Capital Biotechnology': '0P0000ZVG5',  # Converted from IE00B42P0H75 on 2020-11-24
    'Rathbone Ethical Bond': '0P0001D2M9.L',
    'Rathbone Global Opportunities': '0P0001FE43.L',
    'Rocket Lab USA Inc': 'RKLB',
    'Skillz Inc': 'SKLZ', 
    'Smith & Williamson Artificial Intelligence': '0P0001PGKI.L',
    'Threadneedle European Select': '0P0000X3IE.L',
    'T. Rowe Price US Smaller Companies Equity': '0P0001A1SC.L',
    'Waverton European Capital Growth': '0P0001FG8T.L',
    'Workhorse Group Inc': '1WO.BE',
    #'ASI Latin American Equity': '0P0000SHRZ.L',
    #'AXA Framlington American Growth': '0P00000DJJ.L',
    #'JPMorgan Emerging Markets': '0P0000K7VW.L',
    } 

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
    'ARMR': '.L',   # ARMR is ARMR.L in London
    # Irish- and Guernsey-domiciled funds listed in London.  EXCHANGE_SUFFIX_MAP is keyed
    # on the ISIN's country of domicile, which for these says nothing about where they
    # trade, so without an entry here they reach Yahoo as bare tickers and cannot be
    # priced at all (investment-reviews#39).  Retiring this map in favour of the venue the
    # note already states is investment-reviews#40.
    'BTEK': '.L',   # BTEK is BTEK.L in London (IE00BYXG2H39)
    'DFND': '.L',   # DFND is DFND.L in London
    'FEML': '.L',   # FEML is FEML.L in London (GG00B4L0PD47)
    'IWFV': '.L',   # IWFV is IWFV.L in London
    'LTAM': '.L',   # LTAM is LTAM.L in London
}

STOCK_RENAME_MAP = {
    #'KWE':'DFSC'    # Kwesst renamed to Defense Security
}
