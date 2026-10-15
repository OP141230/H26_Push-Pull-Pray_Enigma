"""Stage A: Deterministic inspection of a target Python repository.

Reads pyproject.toml, requirements*.txt, setup.cfg, .python-version.
Returns structured InspectionResult with file paths, line numbers, evidence.
Never raises — all errors are captured in the result.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# tomllib is stdlib in Python 3.11+; fall back to tomli for 3.10
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-reuse-import]
        except ImportError:
            tomllib = None  # type: ignore[assignment]

# Directories to skip during scanning
SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "env", ".env",
    "node_modules", "dist", "build", ".tox", ".mypy_cache",
    "site-packages", ".eggs",
}

MAX_FILE_BYTES = 256 * 1024  # 256 KB cap per file


@dataclass
class EvidenceRef:
    """A traceable reference to a specific location in a file."""
    file_path: str
    line_number: Optional[int]
    excerpt: str
    status: str = "OBSERVED"


@dataclass
class InspectionResult:
    """All deterministically observed facts about the target repository."""
    repo_path: str
    repo_commit: Optional[str] = None
    repo_branch: Optional[str] = None
    python_requires: Optional[str] = None
    python_version_file: Optional[str] = None
    pyproject_path: Optional[str] = None
    requirements_path: Optional[str] = None
    requirements_dev_path: Optional[str] = None
    classifiers: list[str] = field(default_factory=list)
    pyproject_deps: dict[str, str] = field(default_factory=dict)
    requirements_deps: dict[str, str] = field(default_factory=dict)
    requirements_dev_deps: dict[str, str] = field(default_factory=dict)
    evidence: list[EvidenceRef] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    unsupported_formats: list[str] = field(default_factory=list)


def _git_info(repo_path: Path) -> tuple[Optional[str], Optional[str]]:
    """Return (commit_hash, branch) or (None, None) on failure."""
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL, timeout=10,
        ).decode().strip()
        branch = subprocess.check_output(
            ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL, timeout=10,
        ).decode().strip()
        return commit, branch
    except Exception:
        return None, None


def _read_safe(path: Path) -> Optional[str]:
    """Read a text file up to MAX_FILE_BYTES. Return None on error."""
    try:
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            return None  # too large
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _parse_pyproject(result: InspectionResult, path: Path) -> None:
    """Parse pyproject.toml and populate result fields."""
    if tomllib is None:
        result.unsupported_formats.append(f"{path}: tomllib/tomli not available")
        return
    text = _read_safe(path)
    if text is None:
        result.errors.append(f"Cannot read {path}")
        return
    try:
        data = tomllib.loads(text)
    except Exception as exc:
        result.errors.append(f"Malformed TOML in {path}: {exc}")
        return

    result.pyproject_path = str(path)
    project = data.get("project", {})

    # python_requires
    py_req = project.get("requires-python")
    if py_req:
        result.python_requires = py_req
        # find line number
        for i, line in enumerate(text.splitlines(), 1):
            if "requires-python" in line:
                result.evidence.append(EvidenceRef(
                    file_path=str(path),
                    line_number=i,
                    excerpt=line.strip(),
                    status="OBSERVED",
                ))
                break

    # classifiers
    classifiers = project.get("classifiers", [])
    result.classifiers = classifiers
    for i, line in enumerate(text.splitlines(), 1):
        if "Programming Language :: Python ::" in line:
            result.evidence.append(EvidenceRef(
                file_path=str(path),
                line_number=i,
                excerpt=line.strip(),
                status="OBSERVED",
            ))

    # dependencies
    deps_raw = project.get("dependencies", [])
    for dep in deps_raw:
        name, version = _split_dep(dep)
        result.pyproject_deps[name] = version
    # capture pydantic specifically
    for i, line in enumerate(text.splitlines(), 1):
        if "pydantic" in line.lower():
            result.evidence.append(EvidenceRef(
                file_path=str(path),
                line_number=i,
                excerpt=line.strip(),
                status="OBSERVED",
            ))


def _parse_requirements(path: Path) -> dict[str, str]:
    """Parse a requirements.txt-style file. Returns {name: version_spec}."""
    deps: dict[str, str] = {}
    text = _read_safe(path)
    if text is None:
        return deps
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        name, version = _split_dep(line)
        deps[name] = version
    return deps


def _split_dep(dep: str) -> tuple[str, str]:
    """Split 'requests==2.31.0' into ('requests', '==2.31.0')."""
    import re
    m = re.match(r"^([A-Za-z0-9_.\-]+)\s*([><=!~].*)?$", dep.strip())
    if m:
        return m.group(1).lower(), (m.group(2) or "").strip()
    return dep.lower(), ""


def inspect_repository(repo_path: str) -> InspectionResult:
    """
    Deterministically inspect a Python repository.

    Parameters
    ----------
    repo_path : str
        Absolute or relative path to the repository root.

    Returns
    -------
    InspectionResult
        All observed facts. Never raises.
    """
    root = Path(repo_path).resolve()
    result = InspectionResult(repo_path=str(root))

    if not root.exists():
        result.errors.append(f"Repository path does not exist: {root}")
        return result
    if not root.is_dir():
        result.errors.append(f"Repository path is not a directory: {root}")
        return result

    # Git info
    result.repo_commit, result.repo_branch = _git_info(root)

    # pyproject.toml
    pp = root / "pyproject.toml"
    if pp.exists():
        _parse_pyproject(result, pp)
    else:
        result.errors.append("pyproject.toml not found")

    # requirements.txt
    req = root / "requirements.txt"
    if req.exists():
        result.requirements_path = str(req)
        result.requirements_deps = _parse_requirements(req)
        # look for pydantic in requirements
        text = _read_safe(req)
        if text:
            for i, line in enumerate(text.splitlines(), 1):
                if "pydantic" in line.lower():
                    result.evidence.append(EvidenceRef(
                        file_path=str(req),
                        line_number=i,
                        excerpt=line.strip(),
                        status="OBSERVED",
                    ))

    # requirements-dev.txt
    req_dev = root / "requirements-dev.txt"
    if req_dev.exists():
        result.requirements_dev_path = str(req_dev)
        result.requirements_dev_deps = _parse_requirements(req_dev)

    # .python-version
    pv = root / ".python-version"
    if pv.exists():
        content = _read_safe(pv)
        result.python_version_file = (content or "").strip()

    # Scan source files for pydantic usage patterns (config.py etc.)
    _scan_source_for_pydantic_v1(root, result)

    return result


def _scan_source_for_pydantic_v1(root: Path, result: InspectionResult) -> None:
    """Look for Pydantic v1-style API usage in Python source files."""
    v1_patterns = [
        ("@validator", "Pydantic v1 @validator decorator (removed in v2)"),
        ("class Config:", "Pydantic v1 inner Config class (removed in v2)"),
        ("anystr_strip_whitespace", "Pydantic v1 Config option (removed in v2)"),
        ("from pydantic import validator", "Pydantic v1 import"),
        ("pydantic.validator", "Pydantic v1 validator import"),
    ]

    for py_file in root.rglob("*.py"):
        # skip irrelevant dirs
        if any(part in SKIP_DIRS for part in py_file.parts):
            continue
        text = _read_safe(py_file)
        if not text:
            continue
        for pattern, description in v1_patterns:
            for i, line in enumerate(text.splitlines(), 1):
                if pattern in line:
                    result.evidence.append(EvidenceRef(
                        file_path=str(py_file),
                        line_number=i,
                        excerpt=f"[{description}] {line.strip()}",
                        status="OBSERVED",
                    ))
