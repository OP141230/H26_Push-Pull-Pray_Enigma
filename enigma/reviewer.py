"""Stage D: Review and controlled maintenance action."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from enigma.models import ChangeRecord, Finding, ModelRecommendation


def preview_change(
    finding: Finding,
    recommendation: ModelRecommendation | None,
    repo_path: Path,
) -> dict[str, Any]:
    """Generate a preview of the proposed change without modifying files."""
    preview: dict[str, Any] = {
        "finding_title": finding.title,
        "finding_description": finding.description,
        "evidence_count": len(finding.evidence),
        "evidence_refs": [e.to_dict() for e in finding.evidence],
        "recommendation_available": recommendation is not None and recommendation.inference_occurred,
        "recommendation_text": recommendation.recommendation if recommendation else "",
        "proposed_changes": [],
        "justified": False,
        "justification_reason": "",
    }

    # Determine if the change is justified by deterministic evidence
    if finding.evidence and finding.confidence >= 0.5:
        preview["justified"] = True
        preview["justification_reason"] = (
            f"Finding has {len(finding.evidence)} evidence reference(s) "
            f"with confidence {finding.confidence}"
        )
    else:
        preview["justification_reason"] = (
            f"Insufficient evidence (confidence={finding.confidence}, "
            f"evidence_count={len(finding.evidence)})"
        )

    return preview


def apply_dependency_removal(
    repo_path: Path,
    finding: Finding,
    dry_run: bool = True,
    approved: bool = False,
) -> ChangeRecord:
    """Apply a dependency removal change to the target repository."""
    record = ChangeRecord(
        description=finding.proposed_action,
        approved=approved,
    )

    if not finding.evidence:
        record.applied = False
        record.recovery = "No change made - no evidence references."
        return record

    # Extract the dependency name from the finding title
    dep_match = re.search(r"dependency:\s*(\S+)", finding.title, re.IGNORECASE)
    if not dep_match:
        dep_match = re.search(r"unused dependency:\s*(\S+)", finding.title, re.IGNORECASE)
    if not dep_match:
        record.applied = False
        record.recovery = "Could not extract dependency name from finding."
        return record

    dep_name = dep_match.group(1)

    for ev in finding.evidence:
        target_file = Path(ev.file_path)
        if not target_file.is_file():
            continue

        content = target_file.read_text(encoding="utf-8")
        original_content = content

        record.file_path = str(target_file)
        record.change_type = "modified"

        # Handle requirements.txt format
        if target_file.name.endswith(".txt"):
            lines = content.splitlines(keepends=True)
            new_lines = []
            removed = False
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    line_dep = re.split(r"[><=!~;@\[]", stripped)[0].strip()
                    if line_dep.lower() == dep_name.lower():
                        removed = True
                        record.diff_summary = f"Removed line: {stripped}"
                        continue
                new_lines.append(line)

            if removed:
                if dry_run:
                    record.applied = False
                    record.recovery = f"DRY RUN: Would remove '{dep_name}' from {target_file.name}"
                elif approved:
                    # Backup
                    backup_path = target_file.with_suffix(target_file.suffix + ".bak")
                    shutil.copy2(target_file, backup_path)
                    target_file.write_text("".join(new_lines), encoding="utf-8")
                    record.applied = True
                    record.recovery = f"Restore from backup: {backup_path}"
                else:
                    record.applied = False
                    record.recovery = "Change not approved."
        else:
            record.applied = False
            record.recovery = f"Unsupported file format for automated editing: {target_file.name}"

    return record
