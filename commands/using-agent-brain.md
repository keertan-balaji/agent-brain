---
description: "Load the agent-brain usage discipline (recall before work, capture at breakpoints, pre-exit checklist)"
---

# /using-agent-brain

Invoke the `agent-brain:using-agent-brain` skill via the Skill tool. Read it end-to-end. Then:

1. Confirm a resume bundle was injected (look for "Agent Brain resume bundle" in your initial context). If yes, summarize it briefly.
2. If no bundle, run `brain status` via Bash and summarize the active projects + recent captures.
3. Wait for the user's first non-trivial request — then begin using the brain per the skill's flowchart.

Do not output the skill content verbatim. Do not produce a long pre-amble. Brief acknowledgement (≤3 sentences) + ready signal.
