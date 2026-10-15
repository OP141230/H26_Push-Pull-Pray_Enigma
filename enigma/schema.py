"""JSON Schema validator for the Dependency Exit Capsule.

Uses jsonschema if available, otherwise performs manual required-field checks.
Always returns a ValidationResult — never raises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Schema definition ─────────────────────────────────────────────────────────

CAPSULE_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "EnigmaDependencyExitCapsule",
    "type": "object",
    "required": [
        "schema_version", "run_id", "timestamp_utc", "overall_status",
        "project", "environment", "finding", "model", "review",
        "verification", "hermes", "blockers", "limitations",
        "recovery_instructions", "next_steps",
    ],
    "properties": {
        "schema_version": {"type": "string"},
        "run_id": {"type": "string"},
        "timestamp_utc": {"type": "string"},
        "overall_status": {"type": "string", "enum": ["PASS", "PARTIAL", "FAIL", "BLOCKED"]},
        "project": {
            "type": "object",
            "required": ["name", "repo_url"],
            "properties": {
                "name": {"type": "string"},
                "repo_url": {"type": "string"},
                "version": {"type": ["string", "null"]},
                "initial_commit": {"type": ["string", "null"]},
                "final_commit": {"type": ["string", "null"]},
                "branch": {"type": ["string", "null"]},
            },
        },
        "environment": {
            "type": "object",
            "required": ["os_info", "python_version"],
            "properties": {
                "os_info": {"type": "string"},
                "python_version": {"type": "string"},
                "python_312_tested": {"type": "boolean"},
                "python_313_tested": {"type": "boolean"},
            },
        },
        "finding": {
            "oneOf": [
                {"type": "null"},
                {
                    "type": "object",
                    "required": ["finding_id", "title", "classification", "severity", "status"],
                },
            ]
        },
        "model": {
            "oneOf": [
                {"type": "null"},
                {"type": "object", "required": ["status", "inference_performed"]},
            ]
        },
        "review": {
            "oneOf": [
                {"type": "null"},
                {"type": "object", "required": ["approved", "dry_run"]},
            ]
        },
        "verification": {
            "type": "object",
            "required": ["baseline_checks", "post_change_checks"],
        },
        "hermes": {
            "type": "object",
            "required": ["status"],
        },
        "blockers": {"type": "array"},
        "limitations": {"type": "array"},
        "recovery_instructions": {"type": "array"},
        "next_steps": {"type": "array"},
    },
}


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    validator_used: str = "unknown"

    def __str__(self) -> str:
        if self.valid:
            return f"✅ VALID (using {self.validator_used})"
        return (
            f"❌ INVALID (using {self.validator_used}) — "
            + "; ".join(self.errors[:5])
        )


# ── Validators ────────────────────────────────────────────────────────────────

def _manual_validate(data: dict) -> ValidationResult:
    """Fallback validator: checks required top-level keys and types."""
    errors = []
    required = CAPSULE_SCHEMA["required"]
    for key in required:
        if key not in data:
            errors.append(f"Missing required field: '{key}'")

    status = data.get("overall_status")
    valid_statuses = {"PASS", "PARTIAL", "FAIL", "BLOCKED"}
    if status and status not in valid_statuses:
        errors.append(f"overall_status must be one of {valid_statuses}, got {status!r}")

    project = data.get("project", {})
    if isinstance(project, dict):
        for req in ["name", "repo_url"]:
            if not project.get(req):
                errors.append(f"project.{req} is required")

    env = data.get("environment", {})
    if isinstance(env, dict):
        for req in ["os_info", "python_version"]:
            if not env.get(req):
                errors.append(f"environment.{req} is required")

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        validator_used="manual",
    )


def validate_capsule(data: dict) -> ValidationResult:
    """
    Validate a capsule dict against the JSON Schema.

    Tries jsonschema first; falls back to manual validation.
    Never raises.
    """
    try:
        import jsonschema  # type: ignore[import]
        validator = jsonschema.Draft7Validator(CAPSULE_SCHEMA)
        errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
        if errors:
            return ValidationResult(
                valid=False,
                errors=[f"{list(e.absolute_path)}: {e.message}" for e in errors[:10]],
                validator_used="jsonschema/Draft7",
            )
        return ValidationResult(valid=True, validator_used="jsonschema/Draft7")
    except ImportError:
        return _manual_validate(data)
    except Exception as exc:
        return ValidationResult(
            valid=False,
            errors=[f"Validator error: {exc}"],
            validator_used="jsonschema/error",
        )
