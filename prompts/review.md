# Review prompts: use after a phase is green, before /phase-done

## Explain the diff
Explain this diff as if I must defend it in an interview. For each file say what it does, what could go wrong, and which test covers it. List anything you assumed that I have not confirmed.

## Security review
Act as a skeptical security reviewer who has not seen the plan. Review the diff for injection, secrets in logs or code, missing validation, excess permissions, unbounded loops or cost, and anything that bypasses the tool gate. Give findings ordered by severity, each with file and line. Do not fix anything yet.

## Find test gaps
List behaviours in docs/SPEC.md for this phase that no test covers, and boundary cases that are missing. Describe the tests you would add and what they would assert. Do not edit tests or the implementation.

## Check against the spec
Compare the implementation with the numbered sections of docs/SPEC.md for this phase. List every difference, including extra behaviour the spec did not ask for.

## Independent second opinion
Use the reviewer agent (or a fresh session with no plan context) to review the uncommitted changes and report only problems. Use this for guard.py, tools.py, hitl.py and infra/template.yaml.
