"""Stage F: Capsule generation - JSON and Markdown reports."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from enigma.models import Capsule

# JSON Schema for capsule validation
CAPSULE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "schema_version", "run_id", "timestamp_utc",
        "overall_status", "project_name",
    ],
    "properties": {
        "schema_version": {"type": "string"},
        "run_id": {"type": "string"},
        "timestamp_utc": {"type": "string"},
        "overall_status": {"type": "string", "enum": ["PASS", "PARTIAL", "FAIL", "BLOCKED"]},
        "project_name": {"type": "string"},
        "repository_url": {"type": ["string", "null"]},
        "initial_commit": {"type": ["string", "null"]},
        "final_commit": {"type": ["string", "null"]},
        "branch": {"type": ["string", "null"]},
        "git_state": {"type": ["string", "null"]},
        "os_info": {"type": "string"},
        "python_version": {"type": "string"},
        "python_312_tested": {"type": "boolean"},
        "python_313_tested": {"type": "boolean"},
        "finding": {"type": ["object", "null"]},
        "model_recommendation": {"type": ["object", "null"]},
        "changes": {"type": "array"},
        "human_approval": {"type": "string"},
        "baseline_checks": {"type": "array"},
        "post_change_checks": {"type": "array"},
        "hermes_status": {"type": "string"},
        "blockers": {"type": "array"},
        "limitations": {"type": "array"},
        "recovery_instructions": {"type": "string"},
        "next_steps": {"type": "array"},
    },
    "additionalProperties": False,
}


def validate_capsule_json(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate capsule data against the JSON schema."""
    errors: list[str] = []
    try:
        import jsonschema
        jsonschema.validate(instance=data, schema=CAPSULE_SCHEMA)
        return True, []
    except ImportError:
        # Fallback: manual validation of required fields
        for field in CAPSULE_SCHEMA["required"]:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        if "overall_status" in data:
            allowed = CAPSULE_SCHEMA["properties"]["overall_status"]["enum"]
            if data["overall_status"] not in allowed:
                errors.append(f"Invalid overall_status: {data['overall_status']}")
        return len(errors) == 0, errors
    except Exception as e:
        errors.append(f"Validation error: {type(e).__name__}: {e}")
        return False, errors


def generate_json_capsule(capsule: Capsule, output_path: Path) -> tuple[bool, list[str]]:
    """Generate the JSON capsule file."""
    data = capsule.to_dict()
    capsule.overall_status = capsule.compute_overall_status()
    data["overall_status"] = capsule.overall_status

    valid, errors = validate_capsule_json(data)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return valid, errors


def generate_markdown_capsule(capsule: Capsule, output_path: Path) -> None:
    """Generate the Markdown capsule from the same canonical capsule object."""
    data = capsule.to_dict()
    lines: list[str] = []

    lines.append("# Enigma Maintenance Capsule")
    lines.append("")
    lines.append(f"**Run ID:** `{data['run_id']}`  ")
    lines.append(f"**Timestamp (UTC):** `{data['timestamp_utc']}`  ")
    lines.append(f"**Overall Status:** `{data['overall_status']}`  ")
    lines.append(f"**Schema Version:** `{data['schema_version']}`  ")
    lines.append("")

    lines.append("## Environment")
    lines.append(f"- **Project:** {data['project_name']}")
    lines.append(f"- **Repository:** {data.get('repository_url', 'N/A')}")
    lines.append(f"- **Branch:** {data.get('branch', 'N/A')}")
    lines.append(f"- **OS:** {data.get('os_info', 'N/A')}")
    lines.append(f"- **Python:** {data.get('python_version', 'N/A')}")
    lines.append(f"- **Python 3.12 tested:** {data.get('python_312_tested', False)}")
    lines.append(f"- **Python 3.13 tested:** {data.get('python_313_tested', False)}")
    lines.append(f"- **Initial commit:** `{data.get('initial_commit', 'N/A')}`")
    lines.append(f"- **Final commit:** `{data.get('final_commit', 'N/A')}`")
    lines.append("")

    # Finding
    lines.append("## Finding")
    finding = data.get("finding")
    if finding:
        lines.append(f"- **ID:** `{finding.get('finding_id', 'N/A')}`")
        lines.append(f"- **Title:** {finding.get('title', 'N/A')}")
        lines.append(f"- **Description:** {finding.get('description', 'N/A')}")
        lines.append(f"- **Classification:** {finding.get('classification', 'N/A')}")
        lines.append(f"- **Severity:** {finding.get('severity', 'N/A')}")
        lines.append(f"- **Confidence:** {finding.get('confidence', 'N/A')}")
        lines.append(f"- **Status:** {finding.get('status', 'N/A')}")
        lines.append(f"- **Uncertainty:** {finding.get('uncertainty', 'N/A')}")
        lines.append("")
        if finding.get("evidence"):
            lines.append("### Evidence")
            for ev in finding["evidence"]:
                lines.append(f"- `{ev['file_path']}` (line {ev.get('line_start', '?')}): {ev.get('description', '')}")
                if ev.get("snippet"):
                    lines.append(f"  ```")
                    lines.append(f"  {ev['snippet']}")
                    lines.append(f"  ```")
            lines.append("")
    else:
        lines.append("No finding recorded.")
        lines.append("")

    # Model Recommendation
    lines.append("## Model Recommendation")
    rec = data.get("model_recommendation")
    if rec:
        lines.append(f"- **Model:** {rec.get('model_name', 'N/A')}")
        lines.append(f"- **Runtime:** {rec.get('model_runtime', 'N/A')}")
        lines.append(f"- **Inference occurred:** {rec.get('inference_occurred', False)}")
        lines.append(f"- **Validation:** {rec.get('validation_result', 'N/A')}")
        if rec.get("recommendation"):
            lines.append(f"- **Recommendation:** {rec['recommendation']}")
        if rec.get("error"):
            lines.append(f"- **Error/Blocker:** {rec['error']}")
    else:
        lines.append("No model recommendation recorded.")
    lines.append("")

    # Changes
    lines.append("## Changes")
    changes = data.get("changes", [])
    if changes:
        for ch in changes:
            lines.append(f"- **File:** `{ch.get('file_path', 'N/A')}`")
            lines.append(f"  - Type: {ch.get('change_type', 'N/A')}")
            lines.append(f"  - Approved: {ch.get('approved', False)}")
            lines.append(f"  - Applied: {ch.get('applied', False)}")
            lines.append(f"  - Description: {ch.get('description', '')}")
            lines.append(f"  - Recovery: {ch.get('recovery', '')}")
    else:
        lines.append("No changes recorded.")
    lines.append("")

    # Checks
    for section, key in [("Baseline Checks", "baseline_checks"), ("Post-Change Checks", "post_change_checks")]:
        lines.append(f"## {section}")
        checks = data.get(key, [])
        if checks:
            for ck in checks:
                cmd = ck.get("command", "N/A")
                status = ck.get("status", "N/A")
                exit_code = ck.get("exit_code", "N/A")
                lines.append(f"- `{cmd}` → **{status}** (exit code: {exit_code})")
                if ck.get("reason"):
                    lines.append(f"  - Reason: {ck['reason']}")
        else:
            lines.append("No checks recorded.")
        lines.append("")

    # Integration status
    lines.append("## Integration Status")
    lines.append(f"- **Hermes:** {data.get('hermes_status', 'NOT_VERIFIED')}")
    lines.append(f"- **Human approval:** {data.get('human_approval', 'N/A')}")
    lines.append("")

    # Blockers
    lines.append("## Blockers & Limitations")
    for b in data.get("blockers", []):
        lines.append(f"- ⛔ {b}")
    for l in data.get("limitations", []):
        lines.append(f"- ⚠️ {l}")
    if not data.get("blockers") and not data.get("limitations"):
        lines.append("None.")
    lines.append("")

    # Recovery
    lines.append("## Recovery Instructions")
    lines.append(data.get("recovery_instructions", "No recovery needed."))
    lines.append("")

    # Next steps
    lines.append("## Next Steps")
    for ns in data.get("next_steps", []):
        lines.append(f"- {ns}")
    lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
