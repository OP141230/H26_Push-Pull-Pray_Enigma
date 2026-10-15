"""Stage E: Verification - run baseline and post-change checks."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from enigma.models import CommandResult

DEFAULT_TIMEOUT = 120  # seconds


def run_check(
    command: list[str],
    working_dir: str | Path,
    label: str = "",
    timeout: int = DEFAULT_TIMEOUT,
) -> CommandResult:
    """Run a verification command and capture the result."""
    result = CommandResult(
        command=command,
        working_dir=str(working_dir),
    )

    # Detect interpreter
    if command and command[0] in ("python", "python3", "py"):
        result.interpreter = command[0]
        try:
            ver = subprocess.run(
                [command[0], "--version"],
                capture_output=True, text=True, timeout=10,
            )
            result.interpreter_version = ver.stdout.strip() + ver.stderr.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            result.interpreter_version = "unknown"

    result.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    try:
        proc = subprocess.run(
            command,
            cwd=str(working_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        result.exit_code = proc.returncode
        result.stdout_summary = proc.stdout[:2000] if proc.stdout else ""
        result.stderr_summary = proc.stderr[:2000] if proc.stderr else ""
        result.status = "PASSED" if proc.returncode == 0 else "FAILED"
    except subprocess.TimeoutExpired:
        result.exit_code = -1
        result.status = "TIMEOUT"
        result.reason = f"Command timed out after {timeout}s"
    except FileNotFoundError:
        result.exit_code = -1
        result.status = "MISSING_EXECUTABLE"
        result.reason = f"Executable not found: {command[0]}"
    except Exception as e:
        result.exit_code = -1
        result.status = "ERROR"
        result.reason = f"{type(e).__name__}: {e}"

    result.ended_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        t0 = time.mktime(time.strptime(result.started_at, "%Y-%m-%dT%H:%M:%SZ"))
        t1 = time.mktime(time.strptime(result.ended_at, "%Y-%m-%dT%H:%M:%SZ"))
        result.duration_seconds = round(t1 - t0, 2)
    except ValueError:
        pass

    return result


def run_baseline_checks(
    repo_path: Path,
    python_cmd: str = "python",
) -> list[CommandResult]:
    """Run baseline verification checks against the target repository."""
    checks: list[CommandResult] = []

    # Check 1: Python syntax check on all .py files
    py_files = []
    for f in repo_path.rglob("*.py"):
        rel = f.relative_to(repo_path)
        parts = rel.parts
        skip = False
        for p in parts:
            if p in (".venv", "venv", "env", "__pycache__", ".git", ".tox"):
                skip = True
                break
        if not skip:
            py_files.append(str(f))

    if py_files:
        # Check syntax of each file
        for pf in py_files[:20]:  # Limit to 20 files
            check = run_check(
                [python_cmd, "-c", f"import py_compile; py_compile.compile(r'{pf}', doraise=True)"],
                working_dir=str(repo_path),
                label=f"syntax-check-{Path(pf).name}",
            )
            checks.append(check)

    # Check 2: pip check (if requirements.txt exists)
    req_file = repo_path / "requirements.txt"
    if req_file.is_file():
        check = run_check(
            [python_cmd, "-m", "pip", "check"],
            working_dir=str(repo_path),
            label="pip-check",
        )
        checks.append(check)

    return checks
