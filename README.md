# Enigma: Evidence-Driven Repository Maintenance

Evidence-driven repository maintenance agent skill for automated, verified maintenance tasks.

## Architecture

The maintenance workflow follows the canonical pipeline:

```
INSPECT ──► FINDING ──► MODEL RECOMMENDATION ──► REVIEW ──► APPLY ──► VERIFY ──► CAPSULE
```

1. **Stage A (Inspect)**: Deterministic inspection of manifest files (`pyproject.toml`, `setup.cfg`, `requirements.txt`), imports in Python code, and git status.
2. **Stage B (Finding)**: Identification of maintenance findings backed by concrete file and line evidence (e.g. unused dependencies).
3. **Stage C (Model Recommendation)**: Query local language models (Gemma / llama-cpp-python) for structured proposed changes and step-by-step reasoning.
4. **Stage D (Review)**: Rule-based preview and controlled modification with backup and recovery support.
5. **Stage E (Verify)**: Execution of baseline and post-change verification checks (syntax checks, pip check, tests).
6. **Stage F (Capsule)**: Generation of dual canonical JSON and Markdown report capsules validated against JSON schema.

## Installation

```bash
pip install -e .
```

For development and testing:
```bash
pip install -e ".[dev]"
```

## CLI Usage

```bash
# Dry run preview (default)
enigma /path/to/target-repo

# Apply changes with approval
enigma /path/to/target-repo --apply --auto-approve

# Custom output directory
enigma /path/to/target-repo -o /path/to/reports
```
