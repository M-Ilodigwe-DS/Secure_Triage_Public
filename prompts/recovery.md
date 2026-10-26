# Recovery prompts: paste one when a session goes wrong

## It invented an API or syntax
Stop. docs/SPEC.md section 7 and the official documentation are the source of truth. Show me the exact documentation page for what you used. If you cannot, write a live smoke test for it instead of guessing.

## A test fails and it wants to change the test
Do not change the test or loosen an assertion. Explain why the implementation fails the test, then fix the implementation. If you believe the test is wrong, show me why using the spec, and stop.

## It is looping or thrashing
Stop. Summarize what you tried, what you learned and the current hypothesis in five lines. Do not edit anything. I will decide the next step.

## It ignored a rule in CLAUDE.md
You broke this rule: <quote the rule>. Revert the change that broke it, then redo the work following the rule.

## The conversation drifted
Run /clear. Then: Read CLAUDE.md and docs/SPEC.md. We are on phase N. Here is the current state: <paste `git status` and the failing output>. Plan the smallest next step and wait for "go".

## A live step failed with an error
The live step <name> failed with this error: <paste it with secrets removed>. Give two or three likely causes ranked by probability and the fastest check for each. Do not change code until I pick one.

## It wants to run a blocked command
The hook blocked that command on purpose. Do not look for a way around it. Tell me the exact command you wanted to run and why, and I will run it myself.
