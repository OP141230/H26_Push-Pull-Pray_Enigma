"""Stage A: Deterministic repository inspection."""
from __future__ import annotations

import configparser
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from enigma.models import EvidenceRef, Finding, Severity, Status

# Directories to always skip
SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "env",
    "node_modules", ".tox", ".mypy_cache", ".pytest_cache",
    "dist", "build", "*.egg-info", ".eggs",
}

MAX_FILE_SIZE = 512 * 1024  # 512 KB


def should_skip_dir(dirname: str) -> bool:
    """Check if a directory should be skipped."""
    return dirname in SKIP_DIRS or dirname.endswith(".egg-info")


def read_file_safe(path: Path, max_size: int = MAX_FILE_SIZE) -> str | None:
    """Read a file safely, respecting size limits."""
    try:
        if not path.is_file():
            return None
        if path.stat().st_size > max_size:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, PermissionError):
        return None


def find_manifest_files(repo_path: Path) -> dict[str, Path]:
    """Find Python project manifest files."""
    manifests: dict[str, Path] = {}
    candidates = {
        "pyproject.toml": "pyproject.toml",
        "setup.py": "setup.py",
        "setup.cfg": "setup.cfg",
        "requirements.txt": "requirements.txt",
        "requirements-dev.txt": "requirements-dev.txt",
        "Pipfile": "Pipfile",
    }
    for label, filename in candidates.items():
        fpath = repo_path / filename
        if fpath.is_file():
            manifests[label] = fpath
    return manifests


def parse_requirements_txt(content: str) -> list[str]:
    """Parse a requirements.txt file."""
    deps = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Strip version specifiers for name extraction
        name = re.split(r"[><=!~;@\[]", line)[0].strip()
        if name:
            deps.append(name)
    return deps


def parse_setup_cfg_deps(content: str) -> list[str]:
    """Parse install_requires from setup.cfg."""
    config = configparser.ConfigParser()
    try:
        config.read_string(content)
    except configparser.Error:
        return []
    deps = []
    if config.has_option("options", "install_requires"):
        raw = config.get("options", "install_requires")
        for line in raw.splitlines():
            line = line.strip()
            if line:
                name = re.split(r"[><=!~;@\[]", line)[0].strip()
                if name:
                    deps.append(name)
    return deps


def parse_pyproject_deps(content: str) -> list[str]:
    """Parse dependencies from pyproject.toml (basic TOML parsing)."""
    deps = []
    in_deps = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped == 'dependencies = [':
            in_deps = True
            continue
        if in_deps:
            if stripped == ']':
                break
            # Extract package name from quoted string
            match = re.match(r'["\']([a-zA-Z0-9_-]+)', stripped)
            if match:
                deps.append(match.group(1))
    return deps


def find_python_imports(repo_path: Path) -> set[str]:
    """Find all Python import statements in the repository."""
    imports: set[str] = set()
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not should_skip_dir(d)]
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = Path(root) / fname
            content = read_file_safe(fpath)
            if content is None:
                continue
            for line in content.splitlines():
                line = line.strip()
                # import X or import X.Y
                m = re.match(r"^import\s+([a-zA-Z_][a-zA-Z0-9_]*)", line)
                if m:
                    imports.add(m.group(1))
                # from X import ...
                m = re.match(r"^from\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+import", line)
                if m:
                    imports.add(m.group(1))
    return imports


def get_python_version_requirement(content: str) -> str | None:
    """Extract requires-python from pyproject.toml."""
    m = re.search(r'requires-python\s*=\s*["\']([^"\']+)["\']', content)
    return m.group(1) if m else None


def get_git_info(repo_path: Path) -> dict[str, str]:
    """Get Git repository information."""
    info: dict[str, str] = {"commit": "", "branch": "", "remotes": ""}
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path), capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            info["commit"] = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_path), capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            info["branch"] = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return info


# Well-known mapping from PyPI package name to import name
PACKAGE_IMPORT_MAP: dict[str, list[str]] = {
    "pillow": ["PIL"],
    "pyyaml": ["yaml"],
    "scikit-learn": ["sklearn"],
    "python-dateutil": ["dateutil"],
    "beautifulsoup4": ["bs4"],
    "opencv-python": ["cv2"],
    "opencv-python-headless": ["cv2"],
    "python-dotenv": ["dotenv"],
    "attrs": ["attr"],
    "pymongo": ["pymongo", "bson", "gridfs"],
    "protobuf": ["google.protobuf"],
    "google-auth": ["google.auth"],
    "setuptools": ["setuptools", "pkg_resources"],
}


def get_import_names(package_name: str) -> list[str]:
    """Get possible import names for a PyPI package."""
    lower = package_name.lower().replace("-", "_")
    if lower in PACKAGE_IMPORT_MAP:
        return PACKAGE_IMPORT_MAP[lower]
    if package_name.lower() in PACKAGE_IMPORT_MAP:
        return PACKAGE_IMPORT_MAP[package_name.lower()]
    return [lower]


def inspect_repository(repo_path: Path) -> dict[str, Any]:
    """Perform full deterministic inspection of a repository.
    
    Returns a dict with manifests, dependencies, imports, git info, and findings.
    """
    repo_path = Path(repo_path)
    if not repo_path.is_dir():
        return {"error": f"Repository path does not exist: {repo_path}", "findings": []}

    result: dict[str, Any] = {
        "repo_path": str(repo_path),
        "manifests": {},
        "declared_deps": [],
        "imports_found": [],
        "git_info": {},
        "python_requires": None,
        "findings": [],
        "errors": [],
    }

    # Find manifests
    manifests = find_manifest_files(repo_path)
    result["manifests"] = {k: str(v) for k, v in manifests.items()}

    # Parse dependencies from manifests
    all_declared_deps: list[str] = []
    dep_sources: dict[str, str] = {}  # dep -> source file

    for label, fpath in manifests.items():
        content = read_file_safe(fpath)
        if content is None:
            result["errors"].append(f"Could not read {label}")
            continue

        deps: list[str] = []
        if label == "requirements.txt" or label == "requirements-dev.txt":
            deps = parse_requirements_txt(content)
        elif label == "setup.cfg":
            deps = parse_setup_cfg_deps(content)
        elif label == "pyproject.toml":
            deps = parse_pyproject_deps(content)
            result["python_requires"] = get_python_version_requirement(content)

        for d in deps:
            all_declared_deps.append(d)
            dep_sources[d] = label

    result["declared_deps"] = list(set(all_declared_deps))

    # Find imports
    imports = find_python_imports(repo_path)
    result["imports_found"] = sorted(imports)

    # Git info
    result["git_info"] = get_git_info(repo_path)

    # Analyze: find potentially unused declared dependencies
    for dep in all_declared_deps:
        import_names = get_import_names(dep)
        used = any(iname in imports for iname in import_names)
        if not used:
            source_file = dep_sources.get(dep, "unknown")
            source_path = manifests.get(source_file)
            evidence_refs = []
            if source_path:
                content = read_file_safe(source_path)
                if content:
                    for i, line in enumerate(content.splitlines(), 1):
                        if dep.lower() in line.lower():
                            evidence_refs.append(EvidenceRef(
                                file_path=str(source_path),
                                line_start=i,
                                line_end=i,
                                snippet=line.strip(),
                                description=f"Dependency '{dep}' declared in {source_file}",
                            ))
                            break

            finding = Finding(
                title=f"Potentially unused dependency: {dep}",
                description=(
                    f"The dependency '{dep}' is declared in {source_file} "
                    f"but no matching import ({', '.join(import_names)}) "
                    f"was found in .py files. This may be unused, or it may "
                    f"be used via dynamic import, plugin, CLI tool, or "
                    f"alternate import name not covered by the scanner."
                ),
                classification="dependency-maintenance",
                severity=Severity.LOW,
                evidence=evidence_refs,
                affected_files=[str(source_path)] if source_path else [],
                expected_outcome=f"Confirm whether '{dep}' is needed; remove if unused.",
                confidence=0.6,
                uncertainty=(
                    f"The package '{dep}' might be imported under a different "
                    f"name, used as a CLI tool, plugin, or optional runtime "
                    f"dependency not detectable by static import scanning."
                ),
                proposed_action=f"Remove '{dep}' from {source_file} if confirmed unused.",
                status=Status.OBSERVED,
                reason="Static import scan did not find matching import.",
            )
            result["findings"].append(finding)

    # Check for stale python version requirements
    if result.get("python_requires"):
        py_req = result["python_requires"]
        if "3.14" in py_req or "3.15" in py_req:
            result["findings"].append(Finding(
                title="Python version requirement includes unreleased version",
                description=f"requires-python = '{py_req}' references unreleased Python versions.",
                classification="metadata-maintenance",
                severity=Severity.MEDIUM,
                confidence=0.9,
                status=Status.OBSERVED,
            ))

    return result
