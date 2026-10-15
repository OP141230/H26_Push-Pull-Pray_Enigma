---
name: enigma-maintainer
description: Inspect Python dependency declarations and imports, review an evidenced maintenance finding, and generate verified JSON and Markdown capsules. Use for Enigma or LinkWatch maintenance; not vulnerability scanning or automatic dependency upgrades.
license: MIT
---

# Enigma maintainer

Requires Python 3.12 or 3.13 and Git. Repository tests require pytest and project
dependencies. Local Ollama Gemma and Hermes Agent are optional integrations.

Use the implemented Enigma CLI from the delivered project directory, or install that
directory locally with `python -m pip install -e /path/to/enigma`. Do not install or
download a model as an implicit part of this skill. The CLI has no runtime dependencies.

1. Inspect the target Git status, branch and diff. Preserve existing changes. Locate
   the event handbook if event compliance is requested; absence means NOT_VERIFIED.
2. Run `python -m enigma run /path/to/repo --output /separate/path/reports`.
   For a trusted checkout, add `--check-python /path/to/python` to execute its pytest
   suite before any modification. Repository test code has the user's permissions;
   this command is not an execution sandbox. Output must be outside the target repo.
3. Read both capsules and `proposed.patch`. The implemented rule detects the exact
   conflict between `pydantic>=2` in pyproject.toml and a Pydantic 1.x.y pin in
   requirements.txt. It aligns the first declaration with the existing pin. This is
   a manifest-consistency fix, not a compatibility proof or a dependency-exit claim.
   If no rule matches, report no actionable finding; do not invent unused dependencies.
4. If a local Gemma model is already installed, add `--model gemma3:1b` (substitute the
   actual installed tag). Only the local Ollama interface is supported. The runtime
   must be reachable. No cloud tags, hosted fallback, weight download, arbitrary
   model commands, or model-generated paths are allowed. Valid structure and evidence
   IDs do not prove the model's interpretation. Label actual inference AI_RECOMMENDATION;
   preserve BLOCKED or NOT_VERIFIED when no inference occurred.
5. Show the exact patch, cited evidence, expected outcome, uncertainty, baseline and
   `change.review_sha256`. Obtain explicit human approval of that patch before editing.
   General permission to build or continue is insufficient. If approved and baseline
   passes, rerun the same command with `--apply --approve ENIGMA-PYDANTIC-001
   --expected-sha256 REVIEWED_HASH`. Supply `--check-python` again. Never supply an
   approval flag yourself without the user's explicit approval. A stale hash or changed
   evidence requires a new review. A failed baseline blocks this MVP's automatic apply.
6. Check post-change results. Backups are recorded in the capsule. If recovery is
   needed, compare the backup and restore only the approved line while preserving
   later changes; never reset the repository. Do not commit, push, or switch branches.
7. Run `python -m enigma validate /path/reports/dependency_exit_capsule.json
   --markdown /path/reports/dependency_exit_capsule.md`. Both views share one canonical
   report. Report exact check outcomes, interpreter versions, and unresolved blockers.

Labels: OBSERVED for local evidence; AI_RECOMMENDATION only for real inference;
VERIFIED_BY_EXECUTION for executed commands; NOT_VERIFIED for missing proof;
BLOCKED for concrete obstacles. Overall FAIL includes baseline failures, BLOCKED
means a necessary operation was unavailable, PARTIAL includes skipped checks and
unavailable integrations, and PASS requires all declared checks and integrations.

## Discovery and installation

This is the single canonical `enigma-maintainer` skill supplied by this project.
The older LinkWatch `linkwatch-dependency-maintenance` skill is preserved in its
original checkout and has not been renamed or installed by Enigma.
On a Hermes installation, copy this folder to `~/.hermes/skills/enigma-maintainer/`
without overwriting an existing skill. Start a fresh session, run
`hermes skills list`, then invoke `/enigma-maintainer` with the repository and
absolute Enigma project path. Actual discovery and invocation must be recorded;
a correctly formatted skill alone does not establish Hermes integration.

Reference specifications: https://agentskills.io/specification and
https://hermes-agent.nousresearch.com/docs/guides/work-with-skills
