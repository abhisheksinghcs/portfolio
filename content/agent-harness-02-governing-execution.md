# Inside the Agentic Harness, Part 2: Governing Execution, Evidence, and the Conversation Protocol

Part 2 of [Inside the Agentic Harness](/content/agent-harness.md). [Part 1](/content/agent-harness-01-explicit-loop.md) covered how a single tool proposal is resolved, validated, and authorized. This part covers the loop around it: keeping the conversation a correct execution protocol, bounding execution and normalizing its failures, capturing evidence without creating a new liability, and owning the model target with keyless authentication.

> **Rendering note.** Diagrams are provided in both a Mermaid block and an ASCII block. Where they disagree, the ASCII form is authoritative.

> Conversation state is an execution protocol. Tool output is untrusted data. Evidence records decisions, not content.

All excerpts are from [`engineering-change-agent/`](/engineering-change-agent/README.md), and every result shown is captured from its passing tests.

## Pattern: conversation state is an execution protocol

In Chat Completions, an assistant's tool proposal and the tool's result are correlated by a `tool_call_id`. That identifier is not cosmetic — it is what binds a result to the proposal that asked for it. Missing, duplicate, reused, invented, or orphaned identifiers, or more than one proposal in a single turn, break the protocol and could cause the wrong thing to run or a result to attach to the wrong call.

Stage 1A is strictly sequential and fails closed on any correlation defect, before any execution:

```python
def _check_correlation(self, proposal, seen_ids, emitter):
    proposal_id = getattr(proposal, "id", None)
    if not proposal_id:
        emitter.emit(stage=EvidenceStage.TOOL_AUTHORIZATION,
                     decision="denied", reason=ReasonCode.MISSING_TOOL_CALL_ID,
                     outcome=EvidenceOutcome.NOT_EXECUTED)
        raise InvalidModelResponse("Tool call is missing a tool_call_id", emitter.events)
    if proposal_id in seen_ids:
        emitter.emit(stage=EvidenceStage.TOOL_AUTHORIZATION,
                     decision="denied", reason=ReasonCode.REUSED_TOOL_CALL_ID,
                     outcome=EvidenceOutcome.NOT_EXECUTED, proposal_id=proposal_id)
        raise InvalidModelResponse("Reused tool_call_id", emitter.events)
    seen_ids.add(proposal_id)
```

The harness also refuses more than one proposal per turn (`parallel_tool_calls=False` is set on the request, and a returned batch of more than one fails closed as `unexpected_multiple_tool_calls`). Every executed proposal receives exactly one correlated tool-result message:

```python
@staticmethod
def _tool_message(proposal, result):
    # Correlated to the proposal through tool_call_id.
    return {
        "role": "tool",
        "tool_call_id": proposal.id,
        "name": proposal.function.name,
        "content": json.dumps(result.to_dict()),
    }
```

Protocol correctness is part of the harness's job, not an assumption it inherits from the model. Captured fail-closed cases:

```text
multiple proposals in one turn -> reason "unexpected_multiple_tool_calls"
missing tool_call_id           -> reason "missing_tool_call_id"
reused tool_call_id            -> reason "reused_tool_call_id"
```

Because the harness constructs the tool-result messages itself, invented and orphaned identifiers are structurally prevented in this single-client design; a multi-client or parallel design would need explicit orphan detection, which is deferred with the rest of parallel execution.

## Pattern: agent loops require budgets

A model loop with no budget can run forever, or call a tool endlessly, or hang on one slow call. The harness makes termination guaranteed with three explicit limits:

```python
@dataclass(frozen=True)
class HarnessLimits:
    max_steps: int = 8
    max_tool_calls: int = 4
    tool_timeout: float = 5.0
```

When a budget is exhausted the run stops with evidence rather than spinning:

```text
final_response -> decision "denied", reason "max_steps_exceeded", outcome "not_executed"
```

The tool-call budget is checked before each execution, and the step budget bounds the outer loop. Neither depends on the model choosing to stop.

## Pattern: tool output is untrusted data — failures are normalized

A tool runs under a wall-clock timeout, in a worker thread, so a slow handler cannot block the loop:

```python
def execute_with_timeout(handler, arguments, timeout):
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(handler, arguments)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeout as exc:
        raise ToolTimeout() from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
```

Every failure mode is normalized into a stable reason code before it can re-enter the model's context. A timeout becomes `tool_timeout`; any other exception becomes `tool_execution_failed` — and, critically, the exception's message never reaches the model:

```python
try:
    result = execute_with_timeout(tool.handler, arguments, self._limits.tool_timeout)
except ToolTimeout:
    return self._emit_execution_failure(..., ReasonCode.TOOL_TIMEOUT, ...)
except Exception:
    return self._emit_execution_failure(..., ReasonCode.TOOL_EXECUTION_FAILED, ...)
```

The broad `except Exception` is deliberate: its entire job is to guarantee that a raw stack trace or a sensitive exception string — a connection string, an internal path — cannot leak back into the conversation. A test proves it: a handler that raises `"secret internal detail: connection string=..."` produces only `tool_execution_failed` in the tool message, with the sensitive text absent.

(One honest limitation: on timeout the abandoned worker thread keeps running in the background. True cancellation, along with parallel execution and concurrency-safe evidence, is deferred to a later stage.)

## Pattern: evidence must not become a content store

Security logging often becomes its own liability — teams capture raw prompts, completions, tokens, or full tool results "just in case," and create a new exfiltration target. The evidence emitter is designed so that leaking content is *structurally* hard: `emit(...)` has no parameter for raw content, and an allowlist of keys is asserted in the tests.

```python
ALLOWED_EVENT_KEYS = frozenset({
    "timestamp", "run_id", "stage", "tool", "decision", "reason",
    "target_environment", "outcome", "latency_ms", "policy_version", "proposal_id",
})
```

An event can only ever contain those keys, so a prompt, completion, token, credential, or full result has nowhere to live. A captured denial event:

```json
{"timestamp":"2026-09-26T17:05:00+00:00","run_id":"run-2f9c",
 "stage":"tool_authorization","tool":"get_deployment_status","decision":"denied",
 "reason":"production_environment_prohibited","target_environment":"production",
 "outcome":"not_executed","policy_version":"stage1-v1","proposal_id":"call_abc123"}
```

Useful for audit and drift detection, and carrying nothing sensitive. A control you can forget — "remember not to log secrets" — is not a control; here the safe behavior is the only behavior the API allows.

## Pattern: the model target is application-owned, and authentication is keyless

The endpoint, deployment, and token scope are fixed in application configuration — the model can propose actions, but it cannot change *where* the request goes or *how* it authenticates. Authentication uses Microsoft Entra, with no API key:

```python
from openai import OpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

token_provider = get_bearer_token_provider(
    DefaultAzureCredential(), "https://ai.azure.com/.default")
client = OpenAI(base_url=".../openai/v1/", api_key=token_provider)
```

This shape was verified against Microsoft Learn's Foundry v1 API guidance before it was written: the plain `OpenAI` client with a `base_url` ending in `/openai/v1/`, and a bearer-token provider passed as `api_key` so the client fetches and refreshes short-lived Entra tokens automatically. There is no stored secret to leak into logs, evidence, or source. The harness depends on a narrow `ChatModel` interface rather than the SDK, which is also what keeps the tests hermetic — and what will let Stage 1B substitute a framework client without touching the loop.

## The whole thing, end to end

Two captured traces show the governed loop in full. A successful read:

```json
{"run_id":"run-2f9c","stage":"tool_execution","tool":"get_deployment_status",
 "decision":"allowed","target_environment":"test","outcome":"success",
 "latency_ms":0.33,"policy_version":"stage1-v1","proposal_id":"call_1"}
{"run_id":"run-2f9c","stage":"final_response","outcome":"success",
 "policy_version":"stage1-v1"}
ANSWER: DEP-1003 in test is ready: tests passed, 0 open blockers.
```

A production denial, where the tool never runs:

```json
{"run_id":"run-7a1b","stage":"tool_authorization","tool":"get_deployment_status",
 "decision":"denied","reason":"production_environment_prohibited",
 "target_environment":"production","outcome":"not_executed",
 "policy_version":"stage1-v1","proposal_id":"call_1"}
ANSWER: I cannot assess production deployments.
```

## What Stage 1B will map

Stage 1A owns the loop explicitly. Stage 1B will reimplement the same behavioral and security contract on Microsoft Agent Framework and document, responsibility by responsibility, what moves into the framework — model invocation, conversation state, tool dispatch, the loop itself — and what stays application-owned: the approved target, argument validation, authorization, execution budgets, target-side controls, and evidence. A framework can automate orchestration; it does not remove the application's responsibility for those. That mapping is the next step, and it will be added to this series when complete.

## Where to go next

- [Part 1 — The Loop and the Proposal](/content/agent-harness-01-explicit-loop.md)
- [Part 3 — The Harness and the AI Gateway: Layered Enforcement](/content/agent-harness-03-gateway-and-harness.md)
- [Inside the Agentic Harness](/content/agent-harness.md) — series landing page.
- [GenAI Observability Model](/content/observability.md) — the normalized event schema and identity correlation the evidence here feeds.
- [The Secure Agent Lifecycle, Part 3: Build](/content/agent-lifecycle-03-build.md) — where the harness fits in the lifecycle.
