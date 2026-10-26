---
name: phase-done
description: Close a build phase. Runs the full tests and lint, asks the reviewer agent to review the diff, and commits on the current phase branch if there are no HIGH findings. Never pushes.
disable-model-invocation: true
argument-hint: "[phase number and name, for example 05-graph]"
---
Close phase $ARGUMENTS.

1. Check the file `PHASE` contains this phase's number (the human sets it). If not, stop and tell the human. Then run `pytest -q` (it runs the tests of phases 1 up to PHASE) and `ruff check src tests`. If either fails, stop and report the failure. Do not commit.
2. Run `git status` and `git diff --stat`. If any file under `tests/`, `data/`, `evals/`, `docs/SPEC.md`, `.github/` or `.claude/` changed (`PHASE` is expected to have changed), stop and tell the human.
3. Ask the `reviewer` agent to review the uncommitted changes. Show its findings in full.
4. If the reviewer reports HIGH findings, stop. Do not commit. List the findings and wait.
5. Otherwise stage only the files under `src/`, `dashboard_app/` and `infra/`, plus `PHASE`, and commit with a message of the form `feat: <what this phase added> (phase $ARGUMENTS)`.
6. Do not push. Print the three commands the human should run next: `git push`, `gh pr create --fill`, and the review checklist from the guide.
