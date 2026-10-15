"""Stage F: Dependency Exit Capsule generation.

Generates both reports/dependency_exit_capsule.json and
reports/dependency_exit_capsule.md from a single canonical EnigmaCapsule object.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


SCHEMA_VERSION = "1.0.0"


@dataclass
class EnigmaCapsule:
    """Canonical in-memory report — single source of truth for both outputs."""
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: str = SCHEMA_VERSION
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    overall_status: str = "PARTIAL"   # PASS | PARTIAL | FAIL | BLOCKED

    # Project identity
    project_name: str = "linkwatch"
    project_version: Optional[str] = None
    repo_url: str = "https://github.com/rishrek/LinkWatch"
    repo_path: str = ""
    initial_commit: Optional[str] = None
    final_commit: Optional[str] = None
    branch: Optional[str] = None

    # Environment
    os_info: str = field(default_factory=lambda: platform.platform())
    python_version: str = field(default_factory=lambda: sys.version.split()[0])
    python_312_tested: bool = False
    python_313_tested: bool = False

    # Finding
    finding: Optional[dict] = None

    # Model
    model_result: Optional[dict] = None

    # Review
    review_result: Optional[dict] = None

    # Verification
    baseline_checks: list[dict] = field(default_factory=list)
    post_change_checks: list[dict] = field(default_factory=list)

    # Hermes
    hermes_status: str = "NOT_VERIFIED"
    hermes_notes: str = "Hermes Agent not installed in this environment."

    # Blockers
    blockers: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    # Recovery
    recovery_instructions: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)

    def compute_overall_status(self) -> str:
        """Aggregate status from all checks."""
        if self.finding is None:
            return "BLOCKED"

        all_checks = self.baseline_checks + self.post_change_checks
        statuses = [c.get("status", "SKIPPED") for c in all_checks]

        has_fail = any(s == "FAIL" for s in statuses)
        has_pass = any(s == "PASS" for s in statuses)
        has_blocked = bool(self.blockers)

        if has_fail:
            return "FAIL"
        if has_blocked and not has_pass:
            return "BLOCKED"
        if has_blocked or not self.python_312_tested or not self.python_313_tested:
            return "PARTIAL"
        if has_pass:
            return "PASS"
        return "PARTIAL"

    def to_dict(self) -> dict:
        self.overall_status = self.compute_overall_status()
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "timestamp_utc": self.timestamp_utc,
            "overall_status": self.overall_status,
            "project": {
                "name": self.project_name,
                "version": self.project_version,
                "repo_url": self.repo_url,
                "repo_path": self.repo_path,
                "initial_commit": self.initial_commit,
                "final_commit": self.final_commit,
                "branch": self.branch,
            },
            "environment": {
                "os_info": self.os_info,
                "python_version": self.python_version,
                "python_312_tested": self.python_312_tested,
                "python_313_tested": self.python_313_tested,
            },
            "finding": self.finding,
            "model": self.model_result,
            "review": self.review_result,
            "verification": {
                "baseline_checks": self.baseline_checks,
                "post_change_checks": self.post_change_checks,
            },
            "hermes": {
                "status": self.hermes_status,
                "notes": self.hermes_notes,
            },
            "blockers": self.blockers,
            "limitations": self.limitations,
            "recovery_instructions": self.recovery_instructions,
            "next_steps": self.next_steps,
        }


def _check_status_icon(status: str) -> str:
    icons = {"PASS": "✅", "FAIL": "❌", "TIMEOUT": "⏱️",
             "MISSING_EXECUTABLE": "🔍", "SKIPPED": "⏭️", "ERROR": "⚠️",
             "BLOCKED": "🚫", "PARTIAL": "🟡", "SUCCESS": "✅"}
    return icons.get(status, "❓")


def _render_checks_table(checks: list[dict]) -> str:
    if not checks:
        return "_No checks recorded._\n"
    lines = ["| Label | Command | Status | Exit | Elapsed |",
             "|-------|---------|--------|------|---------|"]
    for c in checks:
        cmd = " ".join(c.get("command", []))[:60]
        status = c.get("status", "?")
        icon = _check_status_icon(status)
        lines.append(
            f"| {c.get('label','?')} | `{cmd}` | {icon} {status} "
            f"| {c.get('exit_code','—')} | {c.get('elapsed_seconds','—')}s |"
        )
    return "\n".join(lines) + "\n"


def generate_capsule_files(capsule: EnigmaCapsule, output_dir: str = "reports") -> tuple[str, str]:
    """
    Write dependency_exit_capsule.json and dependency_exit_capsule.md.

    Both are generated from the same capsule object.
    Returns (json_path, md_path).
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    data = capsule.to_dict()

    json_path = os.path.join(output_dir, "dependency_exit_capsule.json")
    md_path = os.path.join(output_dir, "dependency_exit_capsule.md")

    # JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Markdown — rendered from the same `data` dict
    md = _render_markdown(data)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

    return json_path, md_path


def _render_markdown(data: dict) -> str:
    status = data.get("overall_status", "?")
    icon = _check_status_icon(status)
    finding = data.get("finding") or {}
    model = data.get("model") or {}
    review = data.get("review") or {}
    verif = data.get("verification") or {}
    proj = data.get("project") or {}
    env = data.get("environment") or {}
    hermes = data.get("hermes") or {}

    evidence_rows = ""
    for e in finding.get("evidence", []):
        evidence_rows += (
            f"| `{Path(e.get('file_path','?')).name}` "
            f"| {e.get('line_number','—')} "
            f"| `{e.get('excerpt','')[:80]}` "
            f"| {e.get('status','?')} |\n"
        )

    baseline_table = _render_checks_table(verif.get("baseline_checks", []))
    post_table = _render_checks_table(verif.get("post_change_checks", []))

    model_section = ""
    model_label = model.get("label", "NOT_VERIFIED")
    if model.get("inference_performed"):
        rec = model.get("validated_recommendation") or {}
        model_section = f"""
**Model**: `{model.get('model_id', '?')}` via {model.get('runtime','?')}
**Label**: `{model_label}`
**Rationale**: {rec.get('rationale', '—')[:400]}
**Proposed change**: {rec.get('proposed_change', '—')[:400]}
**Confidence**: {rec.get('confidence', '—')}
"""
    else:
        model_section = f"""
**Status**: `{model.get('status', 'BLOCKED')}`  [label: `{model_label}`]
**Blocker**: {model.get('blocker_reason', 'N/A')}

> ⚠️ No real model inference was performed. Deterministic finding stands independently.
"""

    changes_section = ""
    for ch in review.get("changes_applied", []):
        changes_section += f"\n**File**: `{ch.get('file_path','?')}`\n"
        changes_section += f"**Description**: {ch.get('description','?')}\n"
        diff = ch.get("diff_preview", "")
        if diff:
            changes_section += f"\n```diff\n{diff}\n```\n"
        changes_section += f"\n**Recovery**: `{ch.get('recovery_instructions','?')}`\n"

    blockers = data.get("blockers", [])
    blockers_md = "\n".join(f"- {b}" for b in blockers) if blockers else "_None_"
    limitations = data.get("limitations", [])
    limitations_md = "\n".join(f"- {l}" for l in limitations) if limitations else "_None_"
    next_steps = data.get("next_steps", [])
    next_steps_md = "\n".join(f"1. {s}" for s in next_steps) if next_steps else "_None_"
    recovery = data.get("recovery_instructions", [])
    recovery_md = "\n".join(f"- `{r}`" for r in recovery) if recovery else "_None_"

    return f"""# Enigma — Dependency Exit Capsule

> **Status**: {icon} `{status}`  
> **Run ID**: `{data.get('run_id','?')}`  
> **Timestamp**: {data.get('timestamp_utc','?')}  
> **Schema**: v{data.get('schema_version','?')}

---

## Project

| Field | Value |
|-------|-------|
| Name | `{proj.get('name','?')}` |
| Version | `{proj.get('version','?')}` |
| Repo URL | {proj.get('repo_url','?')} |
| Commit (initial) | `{proj.get('initial_commit','?')}` |
| Commit (final) | `{proj.get('final_commit','?')}` |
| Branch | `{proj.get('branch','?')}` |

## Environment

| Field | Value |
|-------|-------|
| OS | {env.get('os_info','?')} |
| Python | {env.get('python_version','?')} |
| Python 3.12 tested | {'✅' if env.get('python_312_tested') else '❌'} |
| Python 3.13 tested | {'✅' if env.get('python_313_tested') else '❌'} |

---

## Finding  `[OBSERVED]`

**ID**: `{finding.get('finding_id','?')}`  
**Title**: {finding.get('title','?')}  
**Classification**: `{finding.get('classification','?')}`  
**Severity**: `{finding.get('severity','?')}`  
**Confidence**: {finding.get('confidence', 0):.0%}  

### Description
{finding.get('description','?')}

### Affected Files
{chr(10).join(f'- `{f}`' for f in finding.get('affected_files', []))}

### Evidence  `[OBSERVED]`

| File | Line | Excerpt | Status |
|------|------|---------|--------|
{evidence_rows if evidence_rows else '| — | — | — | — |'}

### Expected Outcome
{finding.get('expected_outcome','?')}

### Proposed Action
{finding.get('proposed_action','?')}

### Uncertainty
{finding.get('uncertainty','?')}

---

## Model Recommendation  `[{model_label}]`

{model_section}

---

## Review & Changes  `[{review.get('approval_source','?')}]`

| Field | Value |
|-------|-------|
| Approved | {'✅ Yes' if review.get('approved') else '❌ No'} |
| Dry-run | {'Yes' if review.get('dry_run') else 'No'} |
| Approval source | `{review.get('approval_source','?')}` |
| Skipped reason | {review.get('skipped_reason') or '—'} |

{changes_section if changes_section else '_No changes applied._'}

---

## Verification

### Baseline (before change)  `[VERIFIED_BY_EXECUTION]`

{baseline_table}

### Post-Change (after change)  `[VERIFIED_BY_EXECUTION]`

{post_table}

---

## Hermes Agent

| Field | Value |
|-------|-------|
| Status | `{hermes.get('status','?')}` |
| Notes | {hermes.get('notes','?')} |

---

## Blockers

{blockers_md}

## Limitations

{limitations_md}

## Recovery Instructions

{recovery_md}

## Next Steps

{next_steps_md}

---

*Generated by Enigma v0.1.0 — Hacktoberfest 2026 Track 2 Maintenance Agent Skill*
"""
