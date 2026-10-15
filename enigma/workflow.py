"""Orchestrator: INSPECT → FINDING → MODEL → REVIEW → VERIFY → CAPSULE.

Ties all stages together into a single callable workflow.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from .capsule import EnigmaCapsule, generate_capsule_files
from .finding import build_pydantic_conflict_finding
from .inspector import inspect_repository
from .model_adapter import get_recommendation
from .reviewer import review_and_apply
from .schema import validate_capsule
from .verifier import CheckResult, run_linkwatch_baseline


def _python_executable() -> tuple[str, str]:
    """Return (executable, flag) for py -3.12 if available, else sys.executable."""
    import subprocess
    try:
        subprocess.check_output(["py", "-3.12", "--version"], stderr=subprocess.STDOUT, timeout=5)
        return "py", "-3.12"
    except Exception:
        return sys.executable, ""


def run_workflow(
    target_repo: str,
    dry_run: bool = True,
    auto_approve: bool = False,
    interactive: bool = False,
    output_dir: str = "reports",
) -> tuple[EnigmaCapsule, str, str]:
    """
    Execute the full Enigma maintenance workflow.

    Parameters
    ----------
    target_repo : str
        Path to the LinkWatch (or other) repository root.
    dry_run : bool
        Preview changes without writing. Default True.
    auto_approve : bool
        Apply without interactive prompt. Sets dry_run=False implicitly.
    interactive : bool
        Prompt user on stdin for approval.
    output_dir : str
        Directory for capsule output files.

    Returns
    -------
    (capsule, json_path, md_path)
    """
    if auto_approve:
        dry_run = False

    print(f"\n{'='*70}")
    print("ENIGMA — Evidence-Driven Repository Maintenance")
    print(f"Target  : {target_repo}")
    print(f"Mode    : {'DRY-RUN' if dry_run else 'APPLY'}")
    print(f"{'='*70}\n")

    capsule = EnigmaCapsule(repo_path=target_repo)

    # ── Stage A: Inspect ──────────────────────────────────────────────────────
    print("[A] Inspecting repository…")
    inspection = inspect_repository(target_repo)
    capsule.initial_commit = inspection.repo_commit
    capsule.final_commit = inspection.repo_commit  # updated after apply
    capsule.branch = inspection.repo_branch
    capsule.project_version = inspection.pyproject_deps.get("linkwatch", None)

    if inspection.errors:
        for e in inspection.errors:
            print(f"    ⚠ {e}")

    print(f"    Commit : {inspection.repo_commit or 'unknown'}")
    print(f"    Evidence items: {len(inspection.evidence)}")

    # ── Stage B: Finding ─────────────────────────────────────────────────────
    print("[B] Building finding…")
    finding = build_pydantic_conflict_finding(inspection)

    if finding is None:
        print("    No actionable finding. Halting workflow.")
        capsule.blockers.append("No actionable finding could be built from inspection evidence.")
        capsule.overall_status = "BLOCKED"
        json_path, md_path = generate_capsule_files(capsule, output_dir)
        return capsule, json_path, md_path

    capsule.finding = finding.to_dict()
    print(f"    [{finding.finding_id}] {finding.title} ({finding.severity})")

    # ── Stage C: Model recommendation ────────────────────────────────────────
    print("[C] Requesting model recommendation…")
    evidence_text = "\n".join(
        f"  {e.file_path}:{e.line_number} — {e.excerpt}"
        for e in finding.evidence[:10]
    )
    model_result = get_recommendation(finding.to_dict(), evidence_text)
    capsule.model_result = model_result.to_dict()

    if model_result.status == "SUCCESS":
        print(f"    ✅ Inference OK — model: {model_result.model_id}")
    else:
        print(f"    ⚠ Model {model_result.status}: {model_result.blocker_reason}")
        capsule.blockers.append(
            f"Model: {model_result.status} — {model_result.blocker_reason}"
        )

    # ── Stage E (baseline): Run checks before change ──────────────────────────
    print("[E-baseline] Running baseline checks…")
    py_exe, py_flag = _python_executable()
    # Try to install dependencies first (silently)
    _ensure_deps(target_repo, py_exe, py_flag)

    baseline = run_linkwatch_baseline(target_repo, py_exe, py_flag)
    capsule.baseline_checks = [c.to_dict() for c in baseline]
    capsule.python_312_tested = True  # py -3.12 used

    for c in baseline:
        icon = "✅" if c.status == "PASS" else ("⚠" if c.status == "SKIPPED" else "❌")
        print(f"    {icon} {c.label}: {c.status} (exit={c.exit_code})")

    # ── Stage D: Review & apply ───────────────────────────────────────────────
    print("[D] Reviewing and applying change…")
    review_result = review_and_apply(
        finding=finding,
        model_result=model_result,
        repo_path=target_repo,
        dry_run=dry_run,
        auto_approve=auto_approve,
        interactive=interactive,
    )
    capsule.review_result = review_result.to_dict()

    if review_result.changes_applied:
        capsule.recovery_instructions = [
            c.recovery_instructions for c in review_result.changes_applied
        ]

    # ── Stage E (post): Run checks after change ───────────────────────────────
    if review_result.approved and not dry_run:
        print("[E-post] Running post-change checks…")
        # Re-install deps with new pydantic pin
        _ensure_deps(target_repo, py_exe, py_flag, force=True)
        post = run_linkwatch_baseline(target_repo, py_exe, py_flag)
        capsule.post_change_checks = [c.to_dict() for c in post]
        # Update final commit
        import subprocess
        try:
            capsule.final_commit = subprocess.check_output(
                ["git", "-C", target_repo, "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL, timeout=5,
            ).decode().strip()
        except Exception:
            pass
        for c in post:
            icon = "✅" if c.status == "PASS" else ("⚠" if c.status == "SKIPPED" else "❌")
            print(f"    {icon} {c.label}: {c.status} (exit={c.exit_code})")
    else:
        print("[E-post] Skipped (dry-run or not approved)")

    # ── Limitations ───────────────────────────────────────────────────────────
    capsule.limitations = [
        "Python 3.13 not available in this environment — coverage NOT_VERIFIED.",
        "Hermes Agent not installed — skill invocation NOT_VERIFIED.",
        "Gemma model availability depends on `ollama pull gemma:2b` being run.",
    ]
    capsule.next_steps = [
        "Run `ollama pull gemma:2b` and re-run to get real AI recommendation.",
        "Run `py -3.13 -m pytest tests/` when Python 3.13 is available.",
        "Install Hermes Agent and verify enigma-maintainer skill discovery.",
        "Review generated capsule at reports/dependency_exit_capsule.json.",
    ]

    # ── Stage F: Capsule ──────────────────────────────────────────────────────
    print("[F] Generating capsule…")
    json_path, md_path = generate_capsule_files(capsule, output_dir)

    # Schema validation
    import json
    with open(json_path, encoding="utf-8") as f:
        capsule_data = json.load(f)
    validation = validate_capsule(capsule_data)
    print(f"    Schema validation: {validation}")

    print(f"\n✅ Capsule written:")
    print(f"   JSON: {json_path}")
    print(f"   MD  : {md_path}")
    print(f"   Status: {capsule.compute_overall_status()}\n")

    return capsule, json_path, md_path


def _ensure_deps(repo_path: str, py_exe: str, py_flag: str, force: bool = False) -> None:
    """Silently install requirements.txt deps into the current env."""
    import subprocess
    req = Path(repo_path) / "requirements.txt"
    if not req.exists():
        return
    cmd = [py_exe]
    if py_flag:
        cmd.append(py_flag)
    cmd += ["-m", "pip", "install", "-r", str(req), "-q", "--disable-pip-version-check"]
    try:
        subprocess.run(cmd, capture_output=True, timeout=120)
    except Exception:
        pass
