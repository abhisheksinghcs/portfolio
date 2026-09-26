# Article notes — Inside the Agentic Harness

Factual implementation evidence, organized by **design pattern** (not by source
file). Every claim here is backed by real code and captured test output in this
repository. Do not add a claim unless a test or captured run proves it.

Source subfolder: `engineering-change-agent/`.

---

## Pattern: Schema validation is not authorization

### Problem

If well-formed model output is treated as permission, a syntactically valid
tool call could read prohibited data (e.g. production) simply because the
arguments "parsed."

### Design decision

Structural validation (Pydantic) and authorization are separate steps.
`production` is a **structurally valid** `Environment` value, so it passes the
argument schema — and is then *denied by the tool itself*.

### Implementation evidence

- Schema: `DeploymentStatusArguments` in
  `engineering-change-agent/src/change_agent/tools/deployment_status.py`
  (`model_config = ConfigDict(extra="forbid")`, required fields, `min_length`).
- Denial: same file, `get_deployment_status` returns
  `ToolResult.denied(ReasonCode.PRODUCTION_ENVIRONMENT_PROHIBITED)`.
- Tests: `test_production_is_denied_by_the_tool`,
  `test_missing_argument_is_rejected`, `test_unknown_environment_value_is_rejected`.

### Allowed example (captured)

```
ALLOWED test -> {"outcome": "success", "data": {"deployment_id": "DEP-1003",
"application": "payments-api", "environment": "test", "status":
"validation_complete", "tests_passed": true, "open_blockers": 0,
"change_window_available": true}}
```

### Denied example (captured)

```
DENIED prod -> {"outcome": "denied", "reason": "production_environment_prohibited"}
```

### Security significance

A correctly shaped proposal can still be prohibited. The enforcement point is
code, not the schema.

### Limitation

At this stage the *tool* denies production. Application policy (a separate
module) will add the second, independent denial ("denied twice") in a later
step.

---

## Pattern: Tools are constrained targets, not open endpoints

### Problem

A model could try to smuggle arbitrary URLs, resource IDs, queries, or
credentials into a tool call.

### Design decision

The argument schema accepts exactly three named fields; `extra="forbid"`
rejects everything else. The tool serves only known applications and known
records, backed solely by bundled synthetic data.

### Implementation evidence

- `extra="forbid"` on `DeploymentStatusArguments`.
- Known-application check and record match in `get_deployment_status`.
- Tests: `test_unexpected_argument_is_rejected`,
  `test_unknown_application_is_denied`.

### Denied example (captured)

```
REJECT url -> REJECTED by schema: extra_forbidden ('url',)
```

### Security significance

The model cannot expand the tool's reach by adding fields; the target surface
is fixed by shape.

### Limitation

Constraint is currently enforced in-process against synthetic data. A real
protected API with its own authN/authZ is deferred scope.

---

## Pattern: Failure and not-found are normalized (no leakage)

### Problem

Raw exceptions, stack traces, or echoed record contents can leak sensitive
detail into model context.

### Design decision

Every outcome returns a uniform `ToolResult` with a stable reason code. A
not-found returns the reason but **no record contents**.

### Implementation evidence

- `ToolResult` in `engineering-change-agent/src/change_agent/models.py`.
- Not-found path in `get_deployment_status`.
- Test: `test_unknown_deployment_is_not_found_without_leakage`.

### Denied example (captured)

```
NOTFOUND id -> {"outcome": "not_found", "reason": "unknown_deployment"}
```

### Security significance

The caller learns nothing about records it did not legitimately match.

### Limitation

Timeout/exception normalization for real handler execution is a later step
(the tool is currently pure and synchronous).

---

## Pattern: Authorization is separate from validation (and denied twice)

### Problem

If the tool is the only thing refusing production, a bug or future change in the
tool could silently expose production data. And if authorization were folded
into the Pydantic schema, "well-formed" would drift into meaning "allowed."

### Design decision

A standalone `Policy.authorize(...)` decides permission on deterministic,
application-derived context (`ExecutionContext`) and configurable allowed
environments. Production is refused by policy *and*, independently, by the tool
— the same stable reason code from two layers, so neither is load-bearing alone.

### Implementation evidence

- `engineering-change-agent/src/change_agent/policy.py` (`Policy.authorize`).
- `Decision` / `ExecutionContext` in
  `engineering-change-agent/src/change_agent/models.py`.
- Tests: `test_denies_production`,
  `test_denies_environment_outside_configured_allowlist`,
  `test_production_denied_by_both_policy_and_tool`.

### Allowed example (captured)

```
ALLOW test -> allowed= True reason= None
```

### Denied example (captured)

```
DENY  production    -> allowed= False reason= production_environment_prohibited
DENY  sandbox(cfg)  -> allowed= False reason= environment_not_permitted
DENIED TWICE        -> policy.reason= production_environment_prohibited
                       | tool.reason= production_environment_prohibited
```

### Security significance

Correctly shaped input can still be refused. Production denial survives the
failure of either single layer. Authorization is configuration + code, not the
model's instructions.

### Guardrail placement (frequently asked, often missed)

Guardrails belong at the layer that owns the concern: **shape** -> Pydantic args;
**which tools exist** -> registry allowlist; **is it permitted?** -> policy;
**the tool's own contract** -> tool implementation; **budgets/protocol** ->
harness; **behavioral steering** -> system prompt (not a control). A human-approval
guardrail is an authorization concern, so it lives in policy: `Policy(
tools_requiring_approval=...)` denies `approval_required` unless the caller holds
the approval in `ExecutionContext.approved_tools` (application-derived, never
model-asserted). Captured: `NO APPROVAL -> allowed=False reason=approval_required`;
`WITH APPROVAL -> allowed=True`.

### Limitation

Stage 1A authorizes on environment and human approval. Caller/tenant/resource-
owner rules are later steps. Approval is granted out of band and reflected in
`ExecutionContext`; no approval-workflow UI is built here.

---

## Pattern: Evidence must not become a content store

### Problem

Security logging often becomes a liability: teams capture raw prompts, model
completions, tokens, credentials, or full tool results "just in case," creating
a new exfiltration target.

### Design decision

The evidence emitter records only short, decision-oriented fields. Leakage is
made *structurally* hard: `emit(...)` has **no parameter** for raw content, and
an `ALLOWED_EVENT_KEYS` allowlist is asserted in tests — an event can never
contain a key outside it.

### Implementation evidence

- `engineering-change-agent/src/change_agent/evidence.py`
  (`EvidenceEmitter.emit`, `EvidenceEvent.to_dict`, `ALLOWED_EVENT_KEYS`).
- `POLICY_VERSION` single source in
  `engineering-change-agent/src/change_agent/policy.py`.
- Tests: `test_emitted_keys_are_a_subset_of_the_allowlist`,
  `test_none_fields_are_omitted`, `test_enum_values_serialize_as_plain_strings`.

### Allowed example (captured)

```
SUCCESS event: {"timestamp":"2026-09-26T17:05:00+00:00","run_id":"run-2f9c",
"stage":"tool_execution","tool":"get_deployment_status","decision":"allowed",
"target_environment":"test","outcome":"success","latency_ms":0.42,
"policy_version":"stage1-v1","proposal_id":"call_def456"}
```

### Denied example (captured)

```
DENIED event: {"timestamp":"2026-09-26T17:05:00+00:00","run_id":"run-2f9c",
"stage":"tool_authorization","tool":"get_deployment_status","decision":"denied",
"reason":"production_environment_prohibited","target_environment":"production",
"outcome":"not_executed","policy_version":"stage1-v1","proposal_id":"call_abc123"}
```

### Security significance

The evidence stream is useful for audit and drift detection while carrying no
sensitive content. There is no field for a prompt, completion, token,
credential, or full tool result, so none can be recorded even by mistake.

### Limitation

Wiring the emitter into the live loop (stamping real proposal IDs and measured
latency) happens when the harness is built. Concurrency-safe emission is
deferred with the rest of parallel execution.

---

## Pattern: The model target is application-owned (and auth is keyless)

### Problem

If the endpoint, deployment, or credentials could be influenced by the model or
request, the agent could be redirected to an unapproved model or leak a key.

### Design decision

`ModelConfig` fixes the approved endpoint, deployment, and token scope in
application configuration. Authentication uses Microsoft Entra via
`get_bearer_token_provider(DefaultAzureCredential(), scope)` passed as the v1
client's `api_key` — no API key, automatic refresh. The harness depends on a
narrow `ChatModel` protocol, not the SDK, so the target can't be swapped by
model output. Stage 1A also pins `parallel_tool_calls=False`.

### Implementation evidence

- `engineering-change-agent/src/change_agent/model_client.py`
  (`ModelConfig`, `FoundryChatModel`, `ChatModel`).
- `.env.example` documents the (non-secret) endpoint/deployment/scope.
- Tests: `test_complete_uses_deployment_and_disables_parallel_tool_calls`,
  `test_from_env_requires_base_url`, `test_from_env_normalizes_bare_endpoint`.

### Verified interface (Microsoft Learn, Foundry v1 API, Python)

```python
from openai import OpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
token_provider = get_bearer_token_provider(
    DefaultAzureCredential(), "https://ai.azure.com/.default")
client = OpenAI(base_url=".../openai/v1/", api_key=token_provider)
client.chat.completions.create(model="gpt-5.5", messages=[...], tools=[...],
                               parallel_tool_calls=False)
```

### Security significance

The model can propose actions but cannot change *where* the request goes or *how*
it authenticates. No API key exists to leak.

### Limitation

Stage 1A stops at request construction; the real network call, ret/timeout
handling, and wiring into the loop come with the harness step.

---

## Pattern: Tool registries are allowlists; instructions are not authorization

### Problem

If tools were resolved by importing whatever name the model emits, a hallucinated
or malicious name could execute arbitrary code. And if the system prompt were
treated as a control, "telling" the model to avoid production would be mistaken
for enforcing it.

### Design decision

`ToolRegistry.resolve(name)` returns a tool only if it was explicitly registered,
else `None` (harness fails closed) — never a dynamic import. The system prompt is
behavioral guidance only; enforcement stays in code. The advertised tool schema
is *derived from the same Pydantic argument model* used for validation, so it
cannot drift — and developer docstrings are stripped so only structure (not
internal enforcement commentary) reaches the model.

### Implementation evidence

- `engineering-change-agent/src/change_agent/tool_registry.py`
  (`ToolRegistry.resolve`/`schemas`, `_strip_metadata`, `default_registry`).
- `engineering-change-agent/src/change_agent/instructions.py`
  (`SYSTEM_INSTRUCTIONS`, `build_initial_context`).
- Tests: `test_resolve_unknown_tool_returns_none`,
  `test_schemas_are_derived_from_the_argument_model`,
  `test_advertised_schema_excludes_developer_docstrings`,
  `test_registered_handler_runs_end_to_end`.

### Captured evidence (cleaned advertised schema)

```json
{"type":"object","additionalProperties":false,
 "properties":{"application":{"minLength":1,"type":"string"},
  "environment":{"$ref":"#/$defs/Environment"},
  "deployment_id":{"minLength":1,"type":"string"}},
 "required":["application","environment","deployment_id"],
 "$defs":{"Environment":{"enum":["development","test","sandbox","production"],
  "type":"string"}}}
```

### Security significance

The model can only ever name a tool that was deliberately allowlisted, and only
with arguments matching the validated shape. Guidance in the prompt is not
mistaken for enforcement, and internal design notes are not exposed to the model.

### Note discovered during implementation

`model_json_schema()` copies class/field docstrings into schema `description`
fields. Advertising those verbatim leaks developer commentary (including how
enforcement works) into the model prompt; `_strip_metadata` removes them.

### Limitation

Production remains a structurally valid `Environment` value in the advertised
enum (the model may name it); denial is enforced by policy and the tool, not by
hiding the value.

---

## Pattern: The loop is where proposals become governed actions

### Problem

A model that can call tools needs a loop, and a naive loop trusts model output:
it might run whatever tool name is returned, execute unvalidated arguments, run
forever, hang on a slow tool, or leak a stack trace back into the model.

### Design decision

`Harness.run` is a bounded loop that treats every model output as an untrusted
proposal. Per turn it: preserves the assistant message, enforces sequential +
correlated tool calls, resolves from the registry (unknown -> fail closed),
validates shape, authorizes, executes under a timeout, normalizes failures, emits
content-minimizing evidence, appends a correlated tool-result message, and
continues. Budgets (`max_steps`, `max_tool_calls`, `tool_timeout`) guarantee
termination.

### Implementation evidence

- `engineering-change-agent/src/change_agent/harness.py` (`Harness.run`,
  `_check_correlation`, `_process_tool_call`, `execute_with_timeout`).
- Tests: `tests/test_harness_read_flow.py` (11), `tests/test_limits.py` (4).

### Allowed example (captured end-to-end trace)

```json
{"run_id":"run-2f9c","stage":"tool_execution","tool":"get_deployment_status",
 "decision":"allowed","target_environment":"test","outcome":"success",
 "latency_ms":0.33,"policy_version":"stage1-v1","proposal_id":"call_1"}
{"run_id":"run-2f9c","stage":"final_response","outcome":"success",
 "policy_version":"stage1-v1"}
ANSWER: DEP-1003 in test is ready: tests passed, 0 open blockers.
```

### Denied example (captured end-to-end trace)

```json
{"run_id":"run-7a1b","stage":"tool_authorization","tool":"get_deployment_status",
 "decision":"denied","reason":"production_environment_prohibited",
 "target_environment":"production","outcome":"not_executed",
 "policy_version":"stage1-v1","proposal_id":"call_1"}
ANSWER: I cannot assess production deployments.
```

### Security significance

The model can propose, but only allowlisted tools with validated, authorized
arguments run; the loop cannot run forever, hang, or leak internals; and every
decision leaves content-minimizing evidence.

### Limitation

`execute_with_timeout` abandons a timed-out thread rather than truly cancelling
it (a Stage 1A limitation). Parallel tool calls, cancellation, and
concurrency-safe evidence remain deferred.

---

## Pattern: Conversation state is an execution protocol

### Problem

Tool results are correlated to proposals by `tool_call_id`. Missing, duplicate,
reused, invented, or orphaned identifiers — or multiple proposals in one turn —
break the protocol and could execute the wrong thing.

### Design decision

Stage 1A is strictly sequential (`parallel_tool_calls=False`; >1 proposal fails
closed as `unexpected_multiple_tool_calls`). Each proposal must carry a fresh
`tool_call_id`; missing or reused ids fail closed before any execution. Every
executed proposal gets exactly one correlated `role:"tool"` message.

### Implementation evidence

- `Harness._check_correlation`, `Harness._tool_message`, and the
  `len(tool_calls) > 1` guard in `harness.py`.
- Tests: `test_multiple_tool_calls_fail_closed`,
  `test_missing_tool_call_id_fails_closed`,
  `test_reused_tool_call_id_fails_closed`,
  `test_no_content_and_no_tool_call_fails_closed`,
  `test_second_model_call_sees_the_correlated_tool_result`.

### Security significance

Protocol correctness is part of the harness: a malformed conversation cannot
cause an uncorrelated or duplicated tool execution.

### Limitation

Invented/orphaned identifiers are structurally prevented because the harness
constructs the tool-result messages itself; a multi-client or parallel design
would need explicit orphan detection.

---

## Test evidence (captured)

`python -m pytest -q` in `engineering-change-agent/`: **55 passed**.
```
