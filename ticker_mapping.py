"""Mappings from what a broker note says to what Yahoo Finance calls the same security.

The mappings themselves live in ticker_mappings.yaml.  They are reference data, and a
tool that maintains them should not be editing Python (investment-reviews#59); keeping
them in the repo rather than a state directory keeps a change reviewable and revertible,
which matters because a wrong mapping misprices a holding silently.

This module loads that file and exposes the same four names it always did, so nothing
downstream has to know where they came from.
"""

import os
from typing import Any, Dict

import yaml

MAPPINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'ticker_mappings.yaml')


def _flatten(section: Dict[str, Any], value_key: str) -> Dict[str, str]:
    """Take the value out of each entry, whether or not it carries a note.

    An entry is either a plain value or a mapping with the value under `value_key` and a
    `note` saying why it is not obvious.  Both forms exist because most mappings need no
    explanation and the ones that do need it badly.
    """
    flat = {}
    for key, entry in (section or {}).items():
        if isinstance(entry, dict):
            if value_key not in entry:
                raise ValueError(f"{MAPPINGS_FILE}: entry {key!r} has no {value_key!r}")
            flat[key] = entry[value_key]
        else:
            flat[key] = entry
    return flat


def load_mappings(path: str = None) -> Dict[str, Dict[str, str]]:
    """Read the mappings file.  Raises rather than returning empty maps.

    An unreadable mappings file would leave every holding to be identified by its bare
    ticker, which is how investment-reviews#50 priced a defence ETF off a leveraged ARM
    fund.  Failing loudly at import is the lesser harm.
    """
    path = path or MAPPINGS_FILE
    try:
        with open(path, encoding='utf-8') as handle:
            data = yaml.safe_load(handle) or {}
    except Exception as error:
        raise RuntimeError(f"cannot read the ticker mappings at {path}: {error}") from error

    return {
        'names': _flatten(data.get('names'), 'yahoo'),
        'exchange_suffixes': _flatten(data.get('exchange_suffixes'), 'suffix'),
        'ticker_suffixes': _flatten(data.get('ticker_suffixes'), 'suffix'),
        'renames': _flatten(data.get('renames'), 'to'),
    }


_MAPPINGS = load_mappings()

# The stock name a note carries, for notes that carry no ticker.
TICKER_MAPPING = _MAPPINGS['names']

# The Yahoo suffix implied by an ISIN's country of domicile.
EXCHANGE_SUFFIX_MAP = _MAPPINGS['exchange_suffixes']

# Per-ticker overrides, because domicile is not listing venue.
SPECIAL_EXCHANGE_SUFFIX_MAP = _MAPPINGS['ticker_suffixes']

# A ticker that became another ticker.
STOCK_RENAME_MAP = _MAPPINGS['renames']
