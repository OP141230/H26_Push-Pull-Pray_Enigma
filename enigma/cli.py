"""Enigma CLI — entry point for the maintenance workflow.

Usage:
    python -m enigma.cli run --target ./linkwatch
    python -m enigma.cli run --target ./linkwatch --dry-run
    python -m enigma.cli run --target ./linkwatch --auto-approve
    python -m enigma.cli inspect --target ./linkwatch
    python -m enigma.cli validate --capsule reports/dependency_exit_capsule.json
"""

from __future__ import annotations

import json
import os
import sys

try:
    import click
except ImportError:
    print("ERROR: 'click' is not installed. Run: py -3.12 -m pip install click")
    sys.exit(1)

from .workflow import run_workflow
from .inspector import inspect_repository
from .schema import validate_capsule


@click.group()
@click.version_option("0.1.0", prog_name="enigma")
def cli():
    """Enigma — Evidence-Driven Repository Maintenance Agent Skill."""


@cli.command()
@click.option("--target", required=True, help="Path to the target repository.")
@click.option("--dry-run/--no-dry-run", default=True, show_default=True,
              help="Preview changes without writing files.")
@click.option("--auto-approve", is_flag=True, default=False,
              help="Apply change without interactive prompt (sets --no-dry-run).")
@click.option("--output-dir", default="reports", show_default=True,
              help="Directory for capsule output files.")
def run(target: str, dry_run: bool, auto_approve: bool, output_dir: str):
    """Run the full INSPECT→FINDING→MODEL→REVIEW→VERIFY→CAPSULE workflow."""
    if auto_approve:
        dry_run = False
    abs_target = os.path.abspath(target)
    if not os.path.isdir(abs_target):
        click.echo(f"ERROR: Target path does not exist or is not a directory: {abs_target}", err=True)
        sys.exit(1)

    _capsule, json_path, md_path = run_workflow(
        target_repo=abs_target,
        dry_run=dry_run,
        auto_approve=auto_approve,
        output_dir=output_dir,
    )
    click.echo(f"\nDone. Capsule: {json_path}")


@cli.command()
@click.option("--target", required=True, help="Path to the target repository.")
def inspect(target: str):
    """Run deterministic inspection only and print results."""
    abs_target = os.path.abspath(target)
    result = inspect_repository(abs_target)
    click.echo(f"\n=== Inspection: {result.repo_path} ===")
    click.echo(f"Commit : {result.repo_commit or 'unknown'}")
    click.echo(f"Branch : {result.repo_branch or 'unknown'}")
    click.echo(f"Python requires: {result.python_requires or 'not declared'}")
    click.echo(f"\nDeps in pyproject.toml ({len(result.pyproject_deps)}):")
    for name, ver in result.pyproject_deps.items():
        click.echo(f"  {name}{ver}")
    click.echo(f"\nDeps in requirements.txt ({len(result.requirements_deps)}):")
    for name, ver in result.requirements_deps.items():
        click.echo(f"  {name}{ver}")
    click.echo(f"\nEvidence items ({len(result.evidence)}):")
    for e in result.evidence[:20]:
        click.echo(f"  [{e.status}] {os.path.basename(e.file_path)}:{e.line_number} — {e.excerpt[:80]}")
    if result.errors:
        click.echo(f"\nErrors:")
        for err in result.errors:
            click.echo(f"  ⚠ {err}")


@cli.command()
@click.option("--capsule", default="reports/dependency_exit_capsule.json",
              show_default=True, help="Path to capsule JSON file.")
def validate(capsule: str):
    """Validate a capsule JSON file against the schema."""
    if not os.path.exists(capsule):
        click.echo(f"ERROR: File not found: {capsule}", err=True)
        sys.exit(1)
    with open(capsule, encoding="utf-8") as f:
        data = json.load(f)
    result = validate_capsule(data)
    click.echo(str(result))
    sys.exit(0 if result.valid else 1)


if __name__ == "__main__":
    cli()
