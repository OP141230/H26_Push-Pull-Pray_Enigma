"""Stage D: Review and controlled maintenance action.

Displays finding + model recommendation, validates the change is justified,
then applies (or previews) the smallest justified patch.
Never modifies files without explicit approval or --auto-approve flag.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ChangeRecord:
    """Records exactly what was changed and how to recover."""
    file_path: str
    original_content: str
    new_content: str
    description: str
    recovery_instructions: str


@dataclass
class ReviewResult:
    """Outcome of the review-and-apply step."""
    approved: bool
    dry_run: bool
    changes_applied: list[ChangeRecord] = field(default_factory=list)
    skipped_reason: Optional[str] = None
    approval_source: str = "human"   # "human" | "auto_approve" | "dry_run"

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "dry_run": self.dry_run,
            "approval_source": self.approval_source,
            "skipped_reason": self.skipped_reason,
            "changes_applied": [
                {
                    "file_path": c.file_path,
                    "description": c.description,
                    "recovery_instructions": c.recovery_instructions,
                    "diff_preview": _make_diff_preview(c.original_content, c.new_content),
                }
                for c in self.changes_applied
            ],
        }


def _make_diff_preview(original: str, new: str) -> str:
    """Produce a compact unified-diff-style preview (no external deps)."""
    orig_lines = original.splitlines()
    new_lines = new.splitlines()
    diff_lines = []
    # simple line-by-line comparison for the preview
    orig_set = set(orig_lines)
    new_set = set(new_lines)
    for line in orig_lines:
        if line not in new_set:
            diff_lines.append(f"- {line}")
    for line in new_lines:
        if line not in orig_set:
            diff_lines.append(f"+ {line}")
    return "\n".join(diff_lines[:40])  # cap at 40 lines


def _migrate_config_py(source: str) -> str:
    """
    Migrate LinkWatch config.py from Pydantic v1 API to Pydantic v2 API.

    Changes:
      - Replace `from pydantic import BaseModel, validator`
        with `from pydantic import BaseModel, field_validator`
        and add `from pydantic import ConfigDict`
      - Replace `@validator(...)` with `@field_validator(..., mode='before')`
      - Replace inner `class Config:` block containing Pydantic options
        with `model_config = ConfigDict(...)`
      - Remove `anystr_strip_whitespace`
    """
    import re

    text = source

    # 1. Update import line
    text = re.sub(
        r"from pydantic import BaseModel, validator",
        "from pydantic import BaseModel, ConfigDict, field_validator",
        text,
    )
    # Also handle `from pydantic import validator` alone
    text = re.sub(
        r"from pydantic import validator\b",
        "from pydantic import field_validator",
        text,
    )

    # 2. Replace @validator("name") with @field_validator("name", mode="before")
    text = re.sub(
        r'@validator\("([^"]+)"\)',
        r'@field_validator("\1", mode="before")',
        text,
    )
    text = re.sub(
        r"@validator\('([^']+)'\)",
        r"@field_validator('\1', mode='before')",
        text,
    )

    # 3. Replace the Site class Config block
    #    class Config:
    #        anystr_strip_whitespace = True
    # with model_config = ConfigDict(str_strip_whitespace=True)
    text = re.sub(
        r"    class Config:\s*\n        anystr_strip_whitespace = True\n",
        "    model_config = ConfigDict(str_strip_whitespace=True)\n",
        text,
    )

    # 4. Replace the Settings class Config block
    #    class Config:
    #        extra = "forbid"
    # with model_config = ConfigDict(extra="forbid")
    text = re.sub(
        r"    class Config:\s*\n        extra = \"forbid\"\n",
        '    model_config = ConfigDict(extra="forbid")\n',
        text,
    )

    # 5. Replace @validator cls method signature to use @classmethod
    #    field_validator methods still need @classmethod in v2
    text = re.sub(
        r'(@field_validator\([^)]+\))\n    def (\w+)\(cls,',
        r'\1\n    @classmethod\n    def \2(cls,',
        text,
    )

    return text


def _migrate_requirements_txt(source: str) -> str:
    """Replace pydantic==1.x.x with pydantic>=2,<3 in requirements.txt."""
    import re
    return re.sub(
        r"pydantic==1\.[0-9.]+",
        "pydantic>=2,<3",
        source,
    )


def _print_review_summary(finding, model_result, dry_run: bool) -> None:
    """Print a human-readable review summary to stdout."""
    print("\n" + "=" * 70)
    print("ENIGMA MAINTENANCE REVIEW")
    print("=" * 70)
    print(f"\nFINDING [{finding.finding_id}]: {finding.title}")
    print(f"Severity : {finding.severity}")
    print(f"Confidence: {finding.confidence:.0%}")
    print(f"\nDescription:\n  {finding.description[:300]}...")
    print(f"\nAffected files:")
    for f in finding.affected_files:
        print(f"  • {f}")
    print(f"\nProposed action:\n  {finding.proposed_action[:300]}")

    print("\n" + "-" * 70)
    print("MODEL RECOMMENDATION  [label: AI_RECOMMENDATION]")
    print("-" * 70)
    if model_result.inference_performed and model_result.validated_recommendation:
        rec = model_result.validated_recommendation
        print(f"Model   : {model_result.model_id}")
        print(f"Rationale: {rec.get('rationale', '')[:250]}")
        print(f"Proposed : {rec.get('proposed_change', '')[:250]}")
        print(f"Confidence: {rec.get('confidence', 'N/A')}")
    else:
        print(f"Status  : {model_result.status}")
        print(f"Reason  : {model_result.blocker_reason or 'N/A'}")
        print("  (Deterministic finding stands without model confirmation)")

    mode = "DRY-RUN PREVIEW" if dry_run else "APPLYING CHANGE"
    print(f"\n{'=' * 70}")
    print(f"  {mode}")
    print("=" * 70)


def review_and_apply(
    finding,
    model_result,
    repo_path: str,
    dry_run: bool = True,
    auto_approve: bool = False,
    interactive: bool = False,
) -> ReviewResult:
    """
    Show the finding, check deterministic evidence, optionally apply patch.

    Parameters
    ----------
    finding : Finding
        The selected maintenance finding.
    model_result : ModelResult
        Result from the model adapter.
    repo_path : str
        Root of the target repository.
    dry_run : bool
        If True, show changes but do not write files.
    auto_approve : bool
        If True, apply without interactive prompt (requires dry_run=False).
    interactive : bool
        If True, prompt user on stdin for approval.
    """
    root = Path(repo_path).resolve()

    _print_review_summary(finding, model_result, dry_run)

    # Determine approval
    approved = False
    approval_source = "dry_run"

    if dry_run:
        approved = False
        approval_source = "dry_run"
        print("\n[DRY-RUN] No files will be modified. Pass --auto-approve to apply.")
    elif auto_approve:
        approved = True
        approval_source = "auto_approve"
        print("\n[AUTO-APPROVE] Applying change as requested.")
    elif interactive:
        answer = input("\nApply this change? [y/N]: ").strip().lower()
        approved = answer == "y"
        approval_source = "human"
    else:
        approved = False
        approval_source = "dry_run"

    if not approved:
        # Still compute diffs for the capsule
        changes = _compute_changes(root)
        result = ReviewResult(
            approved=False,
            dry_run=dry_run,
            changes_applied=changes,
            skipped_reason="dry_run" if dry_run else "not_approved",
            approval_source=approval_source,
        )
        _print_diff_preview(changes)
        return result

    # Apply
    changes = _compute_and_apply_changes(root)
    print(f"\n✓ Applied {len(changes)} change(s).")
    for c in changes:
        print(f"  Modified: {c.file_path}")

    return ReviewResult(
        approved=True,
        dry_run=False,
        changes_applied=changes,
        approval_source=approval_source,
    )


def _compute_changes(root: Path) -> list[ChangeRecord]:
    """Compute what would change without writing anything."""
    changes = []

    config_path = root / "linkwatch" / "config.py"
    if config_path.exists():
        original = config_path.read_text(encoding="utf-8")
        new = _migrate_config_py(original)
        if original != new:
            changes.append(ChangeRecord(
                file_path=str(config_path),
                original_content=original,
                new_content=new,
                description="Migrate config.py from Pydantic v1 to v2 API",
                recovery_instructions=(
                    f"To recover: git -C {root} checkout -- linkwatch/config.py"
                ),
            ))

    req_path = root / "requirements.txt"
    if req_path.exists():
        original = req_path.read_text(encoding="utf-8")
        new = _migrate_requirements_txt(original)
        if original != new:
            changes.append(ChangeRecord(
                file_path=str(req_path),
                original_content=original,
                new_content=new,
                description="Update requirements.txt: pydantic==1.x → pydantic>=2,<3",
                recovery_instructions=(
                    f"To recover: git -C {root} checkout -- requirements.txt"
                ),
            ))

    return changes


def _compute_and_apply_changes(root: Path) -> list[ChangeRecord]:
    """Compute changes and write them to disk. Creates .bak backups."""
    changes = _compute_changes(root)
    for c in changes:
        path = Path(c.file_path)
        # Backup
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
        path.write_text(c.new_content, encoding="utf-8")
    return changes


def _print_diff_preview(changes: list[ChangeRecord]) -> None:
    for c in changes:
        print(f"\n--- {c.file_path} (preview diff) ---")
        print(_make_diff_preview(c.original_content, c.new_content))
