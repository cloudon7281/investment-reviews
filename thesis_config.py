"""Loading and validation of the thesis candidate configuration file.

The file is JSON with the schema:

    {
      "schema_version": 1,
      "theses": [
        {
          "name": "European Defence",
          "candidates": [
            {"ticker": "RHM.DE", "name": "Rheinmetall"}
          ]
        }
      ]
    }

Whether a candidate is currently held is derived from the parsed portfolio and
is deliberately not recorded here.
"""

import json
from typing import Dict, List
from logger import logger

SUPPORTED_SCHEMA_VERSION = 1


def load_thesis_config(path: str) -> List[Dict]:
    """Load and validate a thesis candidate configuration file.

    Args:
        path: Path to the JSON thesis configuration file

    Returns:
        List of thesis dictionaries, each with 'name' and 'candidates'
        (a list of {'ticker', 'name'} dictionaries)

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

        candidates = thesis.get('candidates')
        if not isinstance(candidates, list) or not candidates:
            raise ValueError(f"Thesis '{name}' in {path} must have a non-empty 'candidates' list")

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

    total_candidates = sum(len(t['candidates']) for t in theses)
    logger.info(f"Loaded {len(theses)} theses with {total_candidates} candidates from {path}")

    return theses
