---
name: enigma-maintainer
version: 1.0.0
description: >
  Evidence-driven Python repository maintenance agent skill.
  Performs the INSPECT→FINDING→MODEL→REVIEW→APPLY→VERIFY→CAPSULE workflow
  on any target Python repository.
author: Push-Pull-Pray
license: MIT
requires_python: ">=3.12"
tools:
  - name: inspect
    description: Run deterministic inspection on a Python repository
    command: "python -m enigma.cli inspect --target {repo_path}"
  - name: run_dry
    description: Preview maintenance changes without applying them
    command: "python -m enigma.cli run --target {repo_path} --dry-run"
  - name: run_apply
    description: Apply the maintenance change (requires approval flag)
    command: "python -m enigma.cli run --target {repo_path} --auto-approve"
  - name: validate
    description: Validate a generated capsule JSON file
    command: "python -m enigma.cli validate --capsule {capsule_path}"
inputs:
  repo_path:
    description: Absolute or relative path to the target repository root
    required: true
  capsule_path:
    description: Path to capsule JSON (for validate tool)
    default: "reports/dependency_exit_capsule.json"
outputs:
  - path: "reports/dependency_exit_capsule.json"
    description: "Structured JSON capsule with all findings, evidence, and results"
  - path: "reports/dependency_exit_capsule.md"
    description: "Human-readable Markdown capsule"
hermes_integration:
  status: NOT_VERIFIED
  notes: >
    Hermes Agent was not installed in the development environment.
    This skill follows the Agent Skills Open Standard (https://agentskills.io/home).
    Install Hermes Agent and register this skill to enable discovery and invocation.
---

# enigma-maintainer

**Enigma** is a reusable AI-powered maintenance capability for Python repositories.
It was built for **Hacktoberfest 2026 Track 2: Maintenance Agent Skill** at
Hacktoberfest Hack Day Mumbai × ISTE KJSSE.

---

## What This Skill Does

Enigma runs a structured, evidence-driven maintenance workflow on any Python repository:

```
INSPECT → FINDING → MODEL RECOMMENDATION → REVIEW → APPLY → VERIFY → CAPSULE
```

1. **INSPECT** — Reads `pyproject.toml`, `requirements.txt`, source files. Extracts
   dependency versions, classifiers, API usage patterns, and Git state.

2. **FINDING** — Identifies one evidence-backed maintenance issue (e.g. a Pydantic
   v1/v2 conflict). Attaches file paths, line numbers, and evidence excerpts.

3. **MODEL RECOMMENDATION** — Queries a local Gemma model via Ollama for a structured
   JSON recommendation. Validates the response. Falls back gracefully if unavailable.

4. **REVIEW** — Displays the finding and model recommendation. Requires explicit
   approval before modifying any file. Supports `--dry-run` and `--auto-approve`.

5. **APPLY** — Applies the smallest justified change (e.g. pydantic API migration).
   Creates `.bak` backups. Records recovery instructions.

6. **VERIFY** — Runs baseline checks (import, pytest, syntax) before and after the
   change. Captures exact commands, exit codes, and output.

7. **CAPSULE** — Generates `reports/dependency_exit_capsule.json` and
   `reports/dependency_exit_capsule.md` from the same in-memory object. Validates
   against a JSON Schema.

---

## Target Repository

- **LinkWatch** — `https://github.com/rishrek/LinkWatch`
- **Finding**: Pydantic v1/v2 version conflict
  - `pyproject.toml`: `pydantic>=2` (v2 required)
  - `requirements.txt`: `pydantic==1.10.13` (v1 pinned — contradicts pyproject.toml)
  - `linkwatch/config.py`: uses `@validator`, `class Config`, `anystr_strip_whitespace`
    (Pydantic v1 API removed in v2)

---

## Installation

```bash
# Clone the project
git clone https://github.com/OP141230/H26_Push-Pull-Pray_Enigma.git
cd H26_Push-Pull-Pray_Enigma

# Install Enigma with Python 3.12
py -3.12 -m pip install -e ".[dev]"

# (Optional) Install Gemma model for AI recommendations
ollama pull gemma:2b
```

---

## Usage

```bash
# Inspect only
py -3.12 -m enigma.cli inspect --target ./linkwatch

# Dry-run (preview changes, no files modified)
py -3.12 -m enigma.cli run --target ./linkwatch --dry-run

# Apply the change
py -3.12 -m enigma.cli run --target ./linkwatch --auto-approve

# Validate the generated capsule
py -3.12 -m enigma.cli validate --capsule reports/dependency_exit_capsule.json

# Run tests
py -3.12 -m pytest tests/ -v
```

---

## AI Model Details

| Field | Value |
|-------|-------|
| Model name | Gemma |
| Model version | gemma:2b (or any gemma model available in Ollama) |
| Model source | Google DeepMind — open-weight |
| Access method | Local inference via Ollama (localhost:11434) |
| License | Gemma Terms of Use (Apache-compatible for research/non-commercial) |
| Role | Provides structured maintenance recommendations grounded in evidence |

> AI-generated recommendations are labelled `AI_RECOMMENDATION` and are always
> separated from deterministically observed facts (`OBSERVED`, `VERIFIED_BY_EXECUTION`).

---

## Status Labels

| Label | Meaning |
|-------|---------|
| `OBSERVED` | Directly supported by repository files or command output |
| `AI_RECOMMENDATION` | Produced by a real model invocation |
| `VERIFIED_BY_EXECUTION` | Confirmed by a recorded command result |
| `NOT_VERIFIED` | Not yet demonstrated |
| `BLOCKED` | Could not proceed due to a concrete blocker |

---

## Hermes Agent Integration

**Status**: `NOT_VERIFIED`

Hermes Agent (Nous Research) was not installed in the development environment.
This skill is structured to follow the Agent Skills Open Standard specification
at https://agentskills.io/home.

To integrate with Hermes Agent:
1. Install Hermes Agent per its documentation.
2. Register this skill directory with Hermes.
3. Invoke: `hermes run enigma-maintainer --repo_path ./linkwatch`

---

## Original Contribution

This is an original implementation. It is not a prompt change, UI modification,
or simple deployment of an existing agent. Enigma adds:

- A **new deterministic inspector** for Python dependency metadata
- A **structured Finding model** with traceable evidence references  
- A **Gemma-backed model adapter** with response validation and graceful fallback
- A **safe reviewer** with dry-run, approval gate, and backup recovery
- A **bounded verifier** running real pytest suites with before/after comparison
- A **dual-format capsule generator** (JSON + Markdown) from a single source object
- A **JSON Schema validator** for capsule integrity checking
- A complete **pytest test suite** covering all stages

---

## Known Limitations

- Python 3.13 coverage: `NOT_VERIFIED` (not installed in development environment)
- Hermes Agent integration: `NOT_VERIFIED` (not installed)
- Gemma model: `BLOCKED` until `ollama pull gemma:2b` is run
- Cloud services and paid APIs: not used (per hackathon rules)
