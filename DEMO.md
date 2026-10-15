# Five-minute live demo

Run from the Enigma project directory with Python 3.12. Use the existing LinkWatch
checkout and its virtual environment. These commands display actual local output;
the real capsule is expected to report FAIL until the pre-existing failure is fixed.

1. **Preservation and scope.** Set `$repo` and `$targetPython` as in README. Show
   `git -C $repo status --short` and `git -C $repo diff --stat`. Explain that the
   tomllib changes predate Enigma and remain intact.
2. **Observe.** Run the README's `python -m enigma run ...` command. Show the exact
   conflicting Pydantic declarations and E4/E15 evidence in the JSON capsule.
3. **Separate facts from AI.** Show the BLOCKED model result: the requested model is
   not installed. Do not read a scripted recommendation as if Gemma generated it.
   Show Hermes as unavailable. If these are later installed, rerun and show actual
   inference/discovery evidence, rather than reusing today's report.
4. **Review.** `Get-Content reports/proposed.patch`. Explain the one-line alignment,
   uncertainty, review hash and explicit approval requirement. No real LinkWatch
   change has been authorized, and the baseline failure prevents automatic apply.
5. **Verify honestly.** Show the capsule's baseline output: 14 passed, 1 failed,
   caused by Jinja2 importing missing `markupsafe.soft_unicode`. Then run
   `python -m unittest discover -s tests -v`: all 18 Enigma tests pass, including
   a real approved edit and before/after pytest on a disposable fixture.
6. **Capsule and final diff.** Run `python -m enigma validate
   reports/dependency_exit_capsule.json --markdown reports/dependency_exit_capsule.md`
   on one line. Open both files. Show `git -C $repo diff --stat` again and the
   preserved-state evidence in HANDOFF.md. Conclude with the specific missing
   handbook, Gemma, Hermes and Python 3.13 evidence.

The approval branch is demonstrated by tests on disposable fixtures. Do not apply
the real patch in a live presentation without explicit approval and a passing baseline.
