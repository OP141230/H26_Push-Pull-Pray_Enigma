"""Stage E: Baseline and post-change verification.

Runs bounded subprocesses with arg lists (no shell interpolation).
Captures command, cwd, interpreter, timing, exit code, output.
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

MAX_OUTPUT_BYTES = 4096   # truncate stdout/stderr to 4 KB each
DEFAULT_TIMEOUT = 60       # seconds


@dataclass
class CheckResult:
    """Result of a single verification command."""
    label: str
    command: list[str]
    cwd: str
    interpreter: str
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    status: str = "SKIPPED"   # PASS | FAIL | TIMEOUT | MISSING_EXECUTABLE | SKIPPED | ERROR
    elapsed_seconds: Optional[float] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    skip_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "command": self.command,
            "cwd": self.cwd,
            "interpreter": self.interpreter,
            "exit_code": self.exit_code,
            "stdout_excerpt": self.stdout[:1000],
            "stderr_excerpt": self.stderr[:500],
            "status": self.status,
            "elapsed_seconds": self.elapsed_seconds,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "skip_reason": self.skip_reason,
        }


def _interpreter_version(executable: str) -> str:
    """Return 'Python X.Y.Z' string or 'unknown'."""
    try:
        out = subprocess.check_output(
            [executable, "--version"], stderr=subprocess.STDOUT, timeout=5
        ).decode().strip()
        return out
    except Exception:
        return "unknown"


def run_check(
    label: str,
    command: list[str],
    cwd: str,
    timeout: int = DEFAULT_TIMEOUT,
    python_executable: Optional[str] = None,
) -> CheckResult:
    """
    Run a single verification command safely.

    Parameters
    ----------
    label : str
        Human-readable name for this check.
    command : list[str]
        Command and arguments (never shell-interpolated string).
    cwd : str
        Working directory.
    timeout : int
        Seconds before the process is killed.
    python_executable : str, optional
        Python interpreter path for version reporting.
    """
    from datetime import datetime, timezone

    interp = python_executable or sys.executable
    interp_ver = _interpreter_version(interp)

    result = CheckResult(
        label=label,
        command=command,
        cwd=cwd,
        interpreter=interp_ver,
    )

    if not Path(cwd).exists():
        result.status = "ERROR"
        result.skip_reason = f"Working directory does not exist: {cwd}"
        return result

    t0 = time.monotonic()
    result.started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            timeout=timeout,
        )
        result.elapsed_seconds = round(time.monotonic() - t0, 2)
        result.ended_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        result.exit_code = proc.returncode
        result.stdout = proc.stdout.decode(errors="replace")[:MAX_OUTPUT_BYTES]
        result.stderr = proc.stderr.decode(errors="replace")[:MAX_OUTPUT_BYTES]
        result.status = "PASS" if proc.returncode == 0 else "FAIL"

    except subprocess.TimeoutExpired:
        result.elapsed_seconds = round(time.monotonic() - t0, 2)
        result.status = "TIMEOUT"
        result.skip_reason = f"Command timed out after {timeout}s"

    except FileNotFoundError:
        result.elapsed_seconds = round(time.monotonic() - t0, 2)
        result.status = "MISSING_EXECUTABLE"
        result.skip_reason = f"Executable not found: {command[0]}"

    except Exception as exc:
        result.elapsed_seconds = round(time.monotonic() - t0, 2)
        result.status = "ERROR"
        result.skip_reason = str(exc)

    return result


def run_linkwatch_baseline(
    repo_path: str,
    python_executable: str = "py",
    python_flag: str = "-3.12",
) -> list[CheckResult]:
    """
    Run the standard LinkWatch verification suite.

    Returns a list of CheckResult objects (baseline or post-change).
    """
    executable = [python_executable, python_flag] if python_flag else [python_executable]
    results = []

    # 1. Import check — verifies pydantic compat
    results.append(run_check(
        label="import_check",
        command=executable + ["-c", "import linkwatch; print('import OK')"],
        cwd=repo_path,
        python_executable=python_executable,
    ))

    # 2. pytest
    results.append(run_check(
        label="pytest",
        command=executable + ["-m", "pytest", "tests/", "-q", "--tb=short", "--no-header"],
        cwd=repo_path,
        python_executable=python_executable,
        timeout=90,
    ))

    # 3. Syntax check on config.py
    results.append(run_check(
        label="syntax_check_config",
        command=executable + ["-m", "py_compile", "linkwatch/config.py"],
        cwd=repo_path,
        python_executable=python_executable,
    ))

    return results
