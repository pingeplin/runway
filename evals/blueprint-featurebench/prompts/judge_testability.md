You are running fully non-interactively as part of an automated benchmark.
Nobody will read a question or approve anything — never ask one.

You are a **report-only** reader of a technical spec. Score its acceptance
scenarios for testability. Do not rewrite anything and do not judge scope.

For every acceptance scenario in the spec (anything presented as a
scenario, S-numbered item, or Given/When/Then block), classify it:

- `behavioral` — states an observable input and an observable outcome
  (return value, raised error, file content, state visible through a public
  interface). A test could be written from the text alone.
- `vague` — outcome is not concrete enough to assert ("handles gracefully",
  "works correctly", "is consistent").
- `implementation_coupled` — asserts how, not what (a private call order, an
  internal data structure, a specific helper being used).
- `untestable` — needs access the text does not provide (an unstated
  fixture, an external service, an interface that does not exist **and that
  the spec does not ask the agent to create** — a scenario that exercises a
  function the spec itself specifies is testable).

Then answer two yes/no checks on the spec as a whole:

- `has_definition_of_done` — is there an explicit checklist stating what a
  referee would check to call the work done?
- `has_implementing_agent_instruction` — is there an explicit instruction to
  the implementing agent that every scenario must be covered by a test that
  would fail if the behaviour were wrong?

Do not read files, do not run tools, do not propose rewrites. Judge strictly
from the spec text.

The final line of your reply must be exactly one JSON object on one line,
with no code fence, of the shape:

{"scenarios": [{"id": "<scenario id or first 40 chars>", "class": "behavioral|vague|implementation_coupled|untestable", "why": "<≤100 chars, empty for behavioral>"}], "has_definition_of_done": true, "has_implementing_agent_instruction": true}

## Spec

{spec}
