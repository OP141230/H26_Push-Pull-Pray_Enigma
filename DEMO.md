# Five-minute live demo

Open `reports/dependency_exit_capsule.html` in a browser for the judge-facing view.
Its status cards distinguish Enigma review completion from the target repository's
baseline failure. The original automation result and failing logs remain visible.
Use `python -m enigma show reports/dependency_exit_capsule.json --output reports`
to present the saved run without repeating inference or tests. Current test count:
26 passing tests. Older counts below describe earlier verification stages.

Run from the Enigma project directory with Python 3.12. Use the existing LinkWatch
checkout and its virtual environment. These commands display actual local output;
the real capsule is expected to report FAIL until the pre-existing failure is fixed.

1. **Preservation and scope.** Set `$repo` and `$targetPython` as in README. Show
   `git -C $repo status --short` and `git -C $repo diff --stat`. Explain that the
   tomllib changes predate Enigma and remain intact.
2. **Observe.** Run the README's `python -m enigma run ...` command. Show the exact
   conflicting Pydantic declarations and E4/E15 evidence in the JSON capsule.
3. **Show the actual AI contribution.** Run with `--model gemma4:latest --model-timeout 300`.
   Open the Markdown capsule's **Gemma recommendation** section. Show the model's
   specific action, rationale, risks, proposed verification and repository citations.
   These are actual model text; the section headings and JSON fields are predefined.
   Distinguish proposed checks from the recorded checks in Execution. Model PASS means
   inference returned validated structure/references, not that the proposed fix is correct.
   Hermes discovery succeeds, but the Python CLI does not invoke Hermes as an agent.
4. **Review.** `Get-Content reports/proposed.patch`. Explain the one-line alignment,
   uncertainty, review hash and explicit approval requirement. No real LinkWatch
   change has been authorized, and the baseline failure prevents automatic apply.
5. **Verify honestly.** Show the capsule's baseline output: 14 passed, 1 failed,
   caused by Jinja2 importing missing `markupsafe.soft_unicode`. Then run
   `python -m unittest discover -s tests -v`: all 21 Enigma tests pass, including
   a real approved edit and before/after pytest on a disposable fixture.
6. **Capsule and final diff.** Run `python -m enigma validate
   reports/dependency_exit_capsule.json --markdown reports/dependency_exit_capsule.md`
   on one line. Open both files. Show `git -C $repo diff --stat` again and the
   preserved-state evidence in HANDOFF.md. Conclude with the specific missing
   handbook, Hermes skill-invocation and Python 3.13 evidence.

The approval branch is demonstrated by tests on disposable fixtures. Do not apply
the real patch in a live presentation without explicit approval and a passing baseline.

## Demonstrating Hermes's role (still to be verified)

Start `hermes chat` from the Enigma project directory. Invoke `/enigma-maintainer`
with the project path, LinkWatch path, Python 3.12 interpreter, target virtualenv
interpreter and `gemma4:latest`. Ask Hermes to run the inspection, read the generated
capsule, explain the model recommendation and baseline failure, and present the patch
for review without applying it. Capture the actual skill load and tool calls in the
live session. Do not claim Hermes discovered the issue: the deterministic Enigma rule
does that. Do not claim it generated the patch: Enigma's whitelisted edit does that.
Hermes's intended role is operating and reviewing the workflow through the skill.
Only a successful agent session demonstrates that role; the current capsule's
discovery check alone does not, and the CLI cannot attest an external chat session.
