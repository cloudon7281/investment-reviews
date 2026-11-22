"""Loading and validation of the thesis candidate configuration file.

The file is JSON with the schema:

    {
      "schema_version": 2,
      "theses": [
        {
          "name": "Data-centre infrastructure",
          "kind": "allocation",
          "status": "adopted",
          "candidates": [
            {"ticker": "VRT", "name": "Vertiv Holdings"}
          ]
        },
        {
          "name": "AI rack power architecture",
          "parent": "Data-centre infrastructure",
          "kind": "discovery",
          "status": "adopted",
          "candidates": [
            {"ticker": "VICR", "name": "Vicor"}
          ]
        }
      ]
    }

Each entry is a thesis or, when it names a `parent`, a sub-thesis of that thesis (one level
deep). `kind` and `status` take Charter D's values. An adopted entry needs at least one
candidate; any other may have none, and an entry with no candidates produces no basket.

Whether a candidate is currently held is derived from the parsed portfolio and
is deliberately not recorded here.
"""

import json
from typing import Dict, List
from logger import logger

SUPPORTED_SCHEMA_VERSION = 2
KINDS = ('allocation', 'discovery', 'both')
STATUSES = ('proposed', 'adopted', 'parked', 'rejected', 'retired')


def load_thesis_config(path: str) -> List[Dict]:
    """Load and validate a thesis candidate configuration file.

    Args:
        path: Path to the JSON thesis configuration file

    Returns:
        List of thesis dictionaries, each with 'name', 'kind', 'status', 'candidates'
        (a list of {'ticker', 'name'} dictionaries) and, for a sub-thesis, 'parent'

    Raises:
        ValueError: If the file cannot be read or fails validation
    """
    try:
        with open(path) as f:
            config = json.load(f)
    except FileNotFoundError:
        raise ValueError(f"Thesis configuration file not found: {path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Thesis configuration file {path} is not valid JSON: {e}")

    if not isinstance(config, dict):
        raise ValueError(f"Thesis configuration file {path} must contain a JSON object")

    schema_version = config.get('schema_version')
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"Thesis configuration file {path} has schema_version {schema_version!r}; "
            f"expected {SUPPORTED_SCHEMA_VERSION}"
        )

    theses = config.get('theses')
    if not isinstance(theses, list) or not theses:
        raise ValueError(f"Thesis configuration file {path} must contain a non-empty 'theses' list")

    for index, thesis in enumerate(theses):
        if not isinstance(thesis, dict):
            raise ValueError(f"Thesis at position {index} in {path} must be an object")

        name = thesis.get('name')
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"Thesis at position {index} in {path} must have a non-empty 'name'")

        for field, allowed in (('kind', KINDS), ('status', STATUSES)):
            if thesis.get(field) not in allowed:
                raise ValueError(
                    f"Thesis '{name}' in {path} has {field} {thesis.get(field)!r}; "
                    f"expected one of {', '.join(allowed)}"
                )

        candidates = thesis.get('candidates')
        if not isinstance(candidates, list):
            raise ValueError(f"Thesis '{name}' in {path} must have a 'candidates' list")
        if not candidates and thesis['status'] == 'adopted':
            raise ValueError(f"Adopted thesis '{name}' in {path} must have at least one candidate")

        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise ValueError(f"Each candidate of thesis '{name}' in {path} must be an object")
            for field in ('ticker', 'name'):
                value = candidate.get(field)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(
                        f"Candidate {candidate!r} of thesis '{name}' in {path} "
                        f"must have a non-empty '{field}'"
                    )

    names = [t['name'] for t in theses]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ValueError(f"Thesis names in {path} must be unique; repeated: {', '.join(duplicates)}")

    top_level = {t['name'] for t in theses if 'parent' not in t}
    for thesis in theses:
        if 'parent' in thesis and thesis['parent'] not in top_level:
            raise ValueError(
                f"Sub-thesis '{thesis['name']}' in {path} has parent {thesis['parent']!r}, "
                f"which is not a thesis without a parent in the file"
            )

    total_candidates = sum(len(t['candidates']) for t in theses)
    logger.info(f"Loaded {len(theses)} theses with {total_candidates} candidates from {path}")

    return theses
