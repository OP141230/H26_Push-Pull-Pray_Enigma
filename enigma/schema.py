"""JSON Schema definition and validation for capsule reports."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from enigma.capsule import CAPSULE_SCHEMA, validate_capsule_json


def validate_capsule_file(filepath: Path) -> tuple[bool, list[str]]:
    """Validate a capsule JSON file against the schema."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON: {e}"]
    except FileNotFoundError:
        return False, [f"File not found: {filepath}"]

    return validate_capsule_json(data)


def get_schema() -> dict[str, Any]:
    """Return the capsule JSON schema."""
    return CAPSULE_SCHEMA
