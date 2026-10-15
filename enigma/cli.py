"""CLI entry point for the Enigma maintenance workflow."""
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

from enigma.capsule import generate_json_capsule, generate_markdown_capsule, validate_capsule_json
from enigma.inspector import inspect_repository
from enigma.models import Capsule, ChangeRecord, Finding, ModelRecommendation, OverallStatus
from enigma.recommender import get_recommendation
from enigma.reviewer import apply_dependency_removal, preview_change
from enigma.verifier import run_baseline_checks, run_check


def main(argv: list[str] | None = None) -> int:
    """Run the Enigma maintenance workflow."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        prog="enigma",
        description="Enigma: Evidence-driven repository maintenance",
    )
    parser.add_argument(
        "target",
        type=Path,
        help="Path to the target repository to inspect",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=Path("."),
        help="Directory for output capsules (default: current directory)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview changes without applying (default: True)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the maintenance change (requires approval)",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Auto-approve changes (use with caution)",
    )
    parser.add_argument(
        "--python-cmd",
        default="python",
        help="Python command to use for checks (default: python)",
    )
    parser.add_argument(
        "--skip-model",
        action="store_true",
        help="Skip model recommendation step",
    )

    args = parser.parse_args(argv)
    target = args.target.resolve()

    print(f"╔══════════════════════════════════════════════╗")
    print(f"║   ENIGMA — Evidence-Driven Maintenance       ║")
    print(f"╚══════════════════════════════════════════════╝")
    print()

    # Initialize capsule
    capsule = Capsule(
        os_info=f"{platform.system()} {platform.release()}",
        python_version=platform.python_version(),
    )

    # ── Stage A: INSPECT ──
    print("[Stage A] Inspecting repository...")
    inspection = inspect_repository(target)

    if "error" in inspection and inspection["error"]:
        print(f"  ERROR: {inspection['error']}")
        capsule.overall_status = OverallStatus.FAIL.value
        capsule.blockers.append(inspection["error"])
        _write_capsules(capsule, args.output_dir)
        return 1

    capsule.repository_url = inspection.get("repo_path", "")
    git_info = inspection.get("git_info", {})
    capsule.initial_commit = git_info.get("commit", "")
    capsule.branch = git_info.get("branch", "")

    print(f"  Repository: {target}")
    print(f"  Manifests found: {list(inspection.get('manifests', {}).keys())}")
    print(f"  Declared deps: {inspection.get('declared_deps', [])}")
    print(f"  Imports found: {len(inspection.get('imports_found', []))}")
    print(f"  Findings: {len(inspection.get('findings', []))}")
    print()

    # ── Stage B: FINDING ──
    print("[Stage B] Selecting maintenance finding...")
    findings: list[Finding] = inspection.get("findings", [])
    selected_finding: Finding | None = None

    if findings:
        # Select the highest-confidence finding
        findings.sort(key=lambda f: f.confidence, reverse=True)
        selected_finding = findings[0]
        print(f"  Selected: {selected_finding.title}")
        print(f"  Confidence: {selected_finding.confidence}")
        print(f"  Evidence: {len(selected_finding.evidence)} reference(s)")
        capsule.finding = selected_finding.to_dict()
    else:
        print("  No maintenance findings identified.")
        capsule.limitations.append("No actionable maintenance finding identified.")
    print()

    # ── Stage C: MODEL RECOMMENDATION ──
    print("[Stage C] Model recommendation...")
    recommendation: ModelRecommendation | None = None

    if selected_finding and not args.skip_model:
        recommendation = get_recommendation(selected_finding, inspection)
        print(f"  Model: {recommendation.model_name}")
        print(f"  Runtime: {recommendation.model_runtime}")
        print(f"  Inference occurred: {recommendation.inference_occurred}")
        print(f"  Validation: {recommendation.validation_result}")
        if recommendation.error:
            print(f"  Blocker: {recommendation.error}")
            capsule.blockers.append(f"Model: {recommendation.error}")
        capsule.model_recommendation = recommendation.to_dict()
    elif args.skip_model:
        print("  Skipped (--skip-model flag).")
        capsule.model_recommendation = {
            "model_name": "gemma",
            "inference_occurred": False,
            "validation_result": "SKIPPED",
            "error": "Skipped by user flag",
        }
    else:
        print("  Skipped (no finding selected).")
    print()

    # ── Stage D: REVIEW ──
    print("[Stage D] Review and maintenance action...")
    change_record: ChangeRecord | None = None

    if selected_finding:
        preview = preview_change(selected_finding, recommendation, target)
        print(f"  Justified: {preview['justified']}")
        print(f"  Reason: {preview['justification_reason']}")

        if preview["justified"]:
            should_apply = args.apply and not args.dry_run
            approved = should_apply and args.auto_approve

            change_record = apply_dependency_removal(
                repo_path=target,
                finding=selected_finding,
                dry_run=not should_apply,
                approved=approved,
            )
            print(f"  Applied: {change_record.applied}")
            print(f"  Recovery: {change_record.recovery}")
            capsule.changes.append(change_record.to_dict())
            capsule.human_approval = "auto-approved" if approved else "dry-run"
        else:
            print("  Change not justified. No modification made.")
    else:
        print("  No finding to act on.")
    print()

    # ── Stage E: VERIFY ──
    print("[Stage E] Running verification checks...")

    # Baseline checks
    baseline_results = run_baseline_checks(target, python_cmd=args.python_cmd)
    capsule.baseline_checks = [r.to_dict() for r in baseline_results]
    passed = sum(1 for r in baseline_results if r.status == "PASSED")
    failed = sum(1 for r in baseline_results if r.status == "FAILED")
    print(f"  Baseline: {passed} passed, {failed} failed, {len(baseline_results)} total")

    # Post-change checks (same checks; change may or may not have been applied)
    if change_record and change_record.applied:
        post_results = run_baseline_checks(target, python_cmd=args.python_cmd)
        capsule.post_change_checks = [r.to_dict() for r in post_results]
        passed = sum(1 for r in post_results if r.status == "PASSED")
        failed = sum(1 for r in post_results if r.status == "FAILED")
        print(f"  Post-change: {passed} passed, {failed} failed, {len(post_results)} total")
    else:
        print("  Post-change checks skipped (no change applied).")
    print()

    # ── Stage F: CAPSULE ──
    print("[Stage F] Generating capsules...")
    capsule.overall_status = capsule.compute_overall_status()
    capsule.final_commit = git_info.get("commit", "")
    capsule.git_state = "clean" if not (change_record and change_record.applied) else "modified"

    # Limitations
    capsule.limitations.extend([
        "Python 3.13 not available for testing on this system.",
        "Hermes Agent integration not verified.",
    ])
    capsule.next_steps = [
        "Verify with Python 3.13 when available.",
        "Test Hermes skill discovery and invocation.",
        "Run with --apply --auto-approve on a disposable repository to test real changes.",
    ]

    valid, errors = _write_capsules(capsule, args.output_dir)

    print(f"  JSON capsule: dependency_exit_capsule.json")
    print(f"  Markdown capsule: dependency_exit_capsule.md")
    print(f"  JSON valid: {valid}")
    if errors:
        print(f"  Validation errors: {errors}")
    print()

    print(f"Overall status: {capsule.overall_status}")
    print("Done.")
    return 0


def _write_capsules(capsule: Capsule, output_dir: Path) -> tuple[bool, list[str]]:
    """Write both capsule files from the same canonical object."""
    output_dir = output_dir.resolve()
    json_path = output_dir / "dependency_exit_capsule.json"
    md_path = output_dir / "dependency_exit_capsule.md"

    valid, errors = generate_json_capsule(capsule, json_path)
    generate_markdown_capsule(capsule, md_path)
    return valid, errors


if __name__ == "__main__":
    sys.exit(main())
