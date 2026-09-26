# Code walkthrough — Stage 1A, Step 1 (read-only tool contract)

A guided tour of what exists in `engineering-change-agent/` so far, written so you
can follow along and ask questions. Read it top to bottom; each file builds on
the one before it.

> The model proposes; deterministic application code validates and authorizes.
> This step builds the *innermost* piece — the tool — and proves its own rules
> before any model or loop exists.

---

## 0. Mental model first

Think of the finished harness as a series of rings around a real action:

```
model proposes  ->  [ shape check ]  ->  [ authorization ]  ->  [ the tool ]  ->  data
                     (Pydantic)          (policy.py, later)     (enforces its
                                                                 own contract)
```

We are building **from the inside out**. Step 1 is only the tool itself and the
shape check for its arguments. The authorization ring (`policy.py`) and the
model/loop rings come in later steps. Building inside-out means each ring is
fully tested before anything less trusted is allowed to call it.

---

## 1. `synthetic-data/deployments.json` — the fake world

Three hand-written deployment records. This is the *only* data the tool can ever
return in Stage 1A. No database, no network, no real systems.

```json
{ "deployment_id": "DEP-1003", "application": "payments-api",
  "environment": "test", "status": "validation_complete",
  "tests_passed": true, "open_blockers": 0, "change_window_available": true }
```

Records provided: `DEP-1003` (payments-api / test), `DEP-2001` (payments-api /
sandbox), `DEP-3007` (identity-service / development). Notice there is **no
production record** — production is refused before any lookup happens, so we
never even store production data.

**Question to consider:** why is using synthetic data a *security* choice, not
just convenience? (Answer: the sample can be published and run by anyone, and a
bug can never leak real deployment information.)

---

## 2. `src/change_agent/errors.py` — stable reason codes

A single small enum, `ReasonCode`. Every denial or failure refers to one of
these exact strings (e.g. `"production_environment_prohibited"`).

Why it matters: tests, evidence logs, and the article all quote these codes.
Keeping them in one place means the *internal* wording of a message can change
without breaking the *contract* that the outside world depends on.

```python
class ReasonCode(str, Enum):
    PRODUCTION_ENVIRONMENT_PROHIBITED = "production_environment_prohibited"
    UNKNOWN_APPLICATION = "unknown_application"
    UNKNOWN_DEPLOYMENT = "unknown_deployment"
```

`str, Enum` means each member *is* a string, so it serializes cleanly into JSON
evidence while still being a named constant in code.

---

## 3. `src/change_agent/models.py` — the data shapes

This file defines *shapes of data*, never permissions. Three things live here:

### `Environment` (enum)
The four environment names, **including `production`**. This is deliberate and
is the crux of a key lesson: `production` is a *structurally valid* name, so it
passes shape-checking — and is refused later by the tool as an *authorization*
decision. Structure and permission are different questions.

### `DeploymentStatus` (Pydantic model)
The typed shape of a record the tool returns. `extra="forbid"` means a record
with unexpected fields would be rejected — the tool won't pass through junk.

### `ToolResult` + `Outcome`
One uniform result shape for *every* outcome: success, denied, not_found,
failed. Built with helper constructors:

```python
ToolResult.success(data)     # outcome=success, carries data
ToolResult.denied(reason)    # outcome=denied,  reason only, NEVER data
ToolResult.not_found(reason) # outcome=not_found, reason only, no record contents
ToolResult.failed(reason)    # outcome=failed,  reason only
```

`to_dict()` turns it into the small JSON object that will later be handed back
to the model. **Security significance:** denials and not-founds carry a reason
but no data, so failures can't leak information. Callers never see raw
exceptions.

**Question to consider:** why return a `ToolResult` object instead of raising
exceptions for "denied" or "not found"? (Answer: expected outcomes are data, not
crashes; a uniform shape is easy to normalize, log, and hand to the model
without leaking internals.)

---

## 4. `src/change_agent/tools/deployment_status.py` — the tool itself

This is the heart of Step 1. Two parts:

### 4a. `DeploymentStatusArguments` — the shape check (the outer ring for this step)

```python
class DeploymentStatusArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    application: str = Field(min_length=1)
    environment: Environment
    deployment_id: str = Field(min_length=1)
```

- `extra="forbid"` is the single most important line for the "locked door"
  property: only these three fields are accepted. A smuggled `url`, `token`, or
  `query` field is rejected automatically.
- `min_length=1` rejects empty strings.
- `environment: Environment` rejects any value that isn't one of the four known
  names.

This establishes **shape**. It does *not* say anyone is allowed to do anything.

### 4b. `get_deployment_status(...)` — the tool's own contract

The tool re-checks its own rules even though outer rings will also check —
"defense in depth." Its logic, in order:

```python
if arguments.environment is Environment.PRODUCTION:
    return ToolResult.denied(ReasonCode.PRODUCTION_ENVIRONMENT_PROHIBITED)

known_applications = {r["application"] for r in records}
if arguments.application not in known_applications:
    return ToolResult.denied(ReasonCode.UNKNOWN_APPLICATION)

for record in records:
    if matches(record, arguments):
        return ToolResult.success(DeploymentStatus...model_dump())

return ToolResult.not_found(ReasonCode.UNKNOWN_DEPLOYMENT)
```

1. **Deny production first** — the tool's own refusal, independent of any policy
   layer. (A second, separate refusal lives in `policy.py` in the next step:
   "denied twice.")
2. **Deny unknown applications** — the tool serves a known set only.
3. **Match a known record** -> return its status as `success`.
4. **Otherwise** -> `not_found` with a reason and **no record contents**, so the
   caller learns nothing about records it didn't match.

Supporting detail: `_load_deployments()` reads the JSON once (`lru_cache`) and
returns it as an immutable tuple; the handler accepts an optional `deployments`
argument so tests can inject their own records.

**Question to consider:** the tool trusts that its arguments were already
shape-checked, yet it *still* re-checks production and known-app rules. Why
duplicate? (Answer: each ring must hold on its own; a bug or future change in an
outer ring must not be able to make the tool return prohibited data.)

---

## 5. `tests/test_tool_contract.py` — the proof

Ten tests, grouped into three stories:

- **Allowed:** valid `test` and `sandbox` lookups return a status.
- **Denied / not-found:** production is denied; unknown application is denied;
  unknown deployment is not-found *with no data*.
- **Structural rejection:** missing field, unexpected field (a smuggled URL),
  empty string, wrong type, and an invalid environment name are all rejected by
  the schema.

Run them:

```bash
cd engineering-change-agent
source .venv/bin/activate
python -m pytest -q      # -> 10 passed
```

The `_args(**overrides)` helper builds a valid argument set and lets each test
change just one field, so each test isolates exactly one rule.

---

## 6. How the pieces connect (today)

```
test / caller
   -> DeploymentStatusArguments.model_validate(payload)   # shape check (Pydantic)
        -> Policy.authorize(tool_name, arguments, context) # authorization ring
             -> get_deployment_status(args)                # tool's own contract
                  -> reads synthetic-data/deployments.json
                  -> returns ToolResult (success | denied | not_found)
```

The rings still missing — the model client, the loop, `tool_call_id`
correlation, and evidence — are the next steps, added one at a time. (Note: the
loop that calls policy *before* the tool is built in a later step; right now
policy and tool are both proven independently by tests.)

---

## 6b. `src/change_agent/policy.py` — the authorization ring (Step 2)

Added in Step 2. This is the ring *between* the shape check and the tool.

### What it is
A `Policy` class with one method, `authorize(...)`, returning a `Decision`
(`allowed: bool`, optional `reason`). Permission is decided on **deterministic,
application-derived context** — not on the model's words.

```python
if environment is Environment.PRODUCTION:
    return Decision.deny(ReasonCode.PRODUCTION_ENVIRONMENT_PROHIBITED)
if environment not in self._allowed_environments:
    return Decision.deny(ReasonCode.ENVIRONMENT_NOT_PERMITTED)
return Decision.allow()
```

### The two lessons it teaches
1. **Authorization is separate from validation.** Pydantic already said the
   arguments are well-formed; `production` passed. Policy is a *different*
   question — is it permitted? — and answers no.
2. **Denied twice (defense in depth).** Policy refuses production, and the tool
   *also* refuses production, independently, with the *same* reason code. Remove
   either layer and production is still blocked. Captured proof:
   ```
   DENIED TWICE -> policy.reason= production_environment_prohibited
                   | tool.reason= production_environment_prohibited
   ```

### Supporting types (in `models.py`)
- `ExecutionContext` — caller / agent / purpose. Application-derived, never from
  the model's proposal. Stage 1A carries the minimum; later stages add tenant,
  approval, resource ownership.
- `Decision` — `allow()` / `deny(reason)`. Distinct from `ToolResult`: a
  `Decision` answers "allowed?"; a `ToolResult` reports what happened when (or
  whether) the tool ran.

### Configurability
Allowed environments are a constructor argument, defaulting to
`{development, test, sandbox}`. `Policy(allowed_environments={Environment.TEST})`
then refuses sandbox with `environment_not_permitted` — showing authorization is
*configuration*, not something hard-wired into the tool.

**Question to consider:** policy and the tool both deny production — isn't that
redundant? (Answer: that redundancy *is* the security property. Each layer must
hold alone so a bug or change in one cannot expose production.)

---

## 6c. `src/change_agent/evidence.py` — the evidence side-channel (Step 3)

Added in Step 3. This is a *side-channel*, not a ring: the harness calls it to
record what happened, but it never changes control flow.

### What it is
- `EvidenceEmitter` — created per run with a `run_id` and `policy_version`. Its
  `emit(...)` method builds an immutable `EvidenceEvent`, appends it to an
  internal list, and optionally hands the dict to a `sink` (e.g. to write JSON
  lines).
- `EvidenceEvent` — a frozen dataclass; `to_dict()` omits any `None` field.
- `EvidenceStage` / `EvidenceOutcome` — small enums giving stable vocabulary
  (`tool_authorization`, `tool_execution`, `final_response`; `success`,
  `failure`, `not_executed`).

### The core lesson: evidence must not become a content store
The strongest control here is what the code *cannot* do: `emit(...)` has **no
parameter** for a prompt, completion, token, credential, or full tool result. On
top of that, `ALLOWED_EVENT_KEYS` lists every permitted key, and a test asserts
every event's keys are a subset of it. So raw content has nowhere to live.

Captured denial event (note the absence of any content field):
```
{"timestamp":"2026-09-26T17:05:00+00:00","run_id":"run-2f9c",
 "stage":"tool_authorization","tool":"get_deployment_status","decision":"denied",
 "reason":"production_environment_prohibited","target_environment":"production",
 "outcome":"not_executed","policy_version":"stage1-v1","proposal_id":"call_abc123"}
```

### Small design details worth noting
- `_coerce(...)` turns enums into their plain string value so events serialize
  cleanly to JSON.
- `clock` is injectable, so tests assert deterministic timestamps.
- `POLICY_VERSION = "stage1-v1"` lives in `policy.py` as the single source of
  truth and is stamped onto every event.

**Question to consider:** why make leakage impossible *by construction* instead
of just "remembering not to log secrets"? (Answer: a control you can forget is
not a control. No parameter + an asserted allowlist means the safe behavior is
the only behavior.)

---

## 6d. `src/change_agent/model_client.py` — talking to the model (Step 4)

Added in Step 4. The first piece that touches Azure. It owns exactly one job:
turn messages (+ optional tool schemas) into a model response.

### What it is
- `ModelConfig` — the *approved* endpoint, deployment (`gpt-5.5`), and Entra
  token scope. Read from env via `from_env()`; the base URL is normalized to end
  in `/openai/v1/`.
- `FoundryChatModel` — wraps the OpenAI v1 client; `complete(messages, tools)`
  calls `chat.completions.create(...)` with `parallel_tool_calls=False`.
- `ChatModel` — a `Protocol` (structural interface) the harness depends on, so a
  fake client stands in for tests — no network, no credentials.

### The lessons
1. **The model target is application-owned.** Endpoint, deployment, and scope are
   fixed in config — the model can propose actions but can't redirect where the
   request goes.
2. **Keyless auth.** `get_bearer_token_provider(DefaultAzureCredential(), scope)`
   is passed as `api_key`; the v1 client refreshes the token automatically. There
   is no API key to leak.
3. **Verified, not guessed.** The exact client shape was confirmed against
   Microsoft Learn before writing it (see `article-notes.md`).

### Design details
- The real SDK client is built **lazily** inside `_build_client`, so importing
  this module never needs the SDK or credentials — only the real credential path
  does.
- `client=` is injectable, which is how tests pass a fake.

**Question to consider:** why depend on a `ChatModel` protocol instead of the
OpenAI client directly? (Answer: the harness shouldn't care *which* model client
it has; a narrow interface keeps tests hermetic and lets Stage 1B swap in Agent
Framework without touching the loop.)

---

## 6e. `instructions.py` + `tool_registry.py` — what the harness tells the model (Step 5)

Added in Step 5. Together these build *what the harness sends the model*: the
system prompt and the list of tools it may call.

### `instructions.py`
- `SYSTEM_INSTRUCTIONS` — behavioral guidance (what EngBot is for, use the tool,
  dev/test/sandbox only, ground answers in tool results). It is **not** an
  authorization control: the model can ignore it, and enforcement lives in code.
- `build_initial_context(user_prompt)` — returns `[system, user]` messages. This
  is the "context construction" responsibility.

### `tool_registry.py`
- `ToolRegistry` — an explicit allowlist. `resolve(name)` returns a tool only if
  registered, else `None` (the harness fails closed). **No dynamic import** of a
  model-supplied name.
- `RegisteredTool.json_schema()` — the OpenAI tool schema advertised to the
  model. Parameters are **derived from the Pydantic argument model**, so what the
  model is told cannot drift from what is validated.
- `_strip_metadata(...)` — removes `title`/`description` that Pydantic copies from
  developer docstrings, so only structure (not internal commentary) reaches the
  model.
- `default_registry()` — registers the single read-only deployment tool.

### The lessons
1. **Tool registries are allowlists.** The model can only name a tool that was
   deliberately registered.
2. **Instructions are not authorization.** The prompt steers behavior; code
   enforces.
3. **Advertised schema == validated schema.** One Pydantic model is the source of
   both, so they can't diverge — and dev docstrings don't leak into the prompt.

**Question to consider:** production is still in the advertised environment enum
— why not hide it? (Answer: denial is enforced by policy and the tool; hiding the
value would rely on the model's cooperation, which is not a control.)

---

## 6f. `harness.py` — the bounded loop (Step 6)

Added in Step 6. This is where all the rings come together and where "the model
proposes; code disposes" actually happens.

### The shape of `Harness.run`
A `for _ in range(max_steps)` loop. Each turn:
1. `model.complete(messages, tools=registry.schemas())`.
2. Read `response.choices[0].message`; append the *complete* assistant message
   (content + any tool proposal) to `messages`.
3. If there's a tool call:
   - `>1` -> `unexpected_multiple_tool_calls`, fail closed.
   - `_check_correlation`: missing/reused `tool_call_id` -> fail closed.
   - budget check: `max_tool_calls` -> fail closed.
   - `_process_tool_call` -> append a correlated `role:"tool"` message ->
     continue.
4. Else if there's content -> emit `final_response` success, return.
5. Else (neither) -> `invalid_model_response`, fail closed.
6. Loop end -> `max_steps_exceeded`, fail closed.

### `_process_tool_call` — the enforcement pipeline for one proposal
`resolve` (unknown -> `unknown_tool`) -> `json.loads` + `model_validate`
(bad shape -> `invalid_arguments`) -> `policy.authorize` (denied -> its reason) ->
`execute_with_timeout` (timeout -> `tool_timeout`; any exception ->
`tool_execution_failed`) -> emit evidence -> return a normalized `ToolResult`.
Note the enforcement *order*: resolve, then validate shape, then authorize, then
execute — each stage gates the next.

### `execute_with_timeout`
Runs the handler in a worker thread and waits `tool_timeout` seconds. On timeout
it raises `ToolTimeout` and does not wait for the thread, so a slow tool can't
block the loop. (Abandoning the thread is a known Stage 1A limitation.)

### Failures are normalized
Exceptions never reach the model: they become a `ToolResult.failed(reason)` with
a stable code. A test asserts a handler raising `"secret internal detail..."`
yields only `tool_execution_failed` in the tool message — no leakage.

### Budgets
`HarnessLimits(max_steps, max_tool_calls, tool_timeout)` — a model loop without
budgets can run forever or hammer a tool; these make termination guaranteed.

### What it returns
`HarnessResult(answer, events)` — the final text plus the full evidence trace, so
callers and tests can inspect exactly what the harness decided.

**Question to consider:** why append the assistant message *before* processing
the tool call? (Answer: the Chat Completions protocol requires the assistant's
tool proposal to precede its correlated tool result in the history; preserving it
first keeps the conversation valid and the correlation honest.)

---

## 6g. `cli.py` — the entry point (Step 7)

Added in Step 7. Pure wiring, no new logic: `ModelConfig.from_env()` ->
`FoundryChatModel(config)` -> `default_registry()` + `Policy()` +
`ExecutionContext` -> `Harness.run(prompt)`. The answer prints to stdout; the
evidence trace prints to stderr (via the harness `evidence_sink`). A missing
`AZURE_OPENAI_BASE_URL` returns exit code 2 with a helpful message; a protocol
or budget failure returns 1. The `model` parameter is injectable so the happy
path is tested offline with a scripted fake. Installed as the `change-agent`
console script.

---

## 7. Captured evidence (real runs)


```
ALLOWED test -> {"outcome":"success","data":{"deployment_id":"DEP-1003",
                 "environment":"test","tests_passed":true, ...}}
DENIED prod  -> {"outcome":"denied","reason":"production_environment_prohibited"}
NOTFOUND id  -> {"outcome":"not_found","reason":"unknown_deployment"}
REJECT url   -> REJECTED by schema: extra_forbidden ('url',)

ALLOW test        -> allowed= True  reason= None
DENY  production  -> allowed= False reason= production_environment_prohibited
DENY  sandbox(cfg)-> allowed= False reason= environment_not_permitted
DENIED TWICE      -> policy.reason= production_environment_prohibited
                     | tool.reason= production_environment_prohibited
```

See `docs/article-notes.md` for the same evidence organized by design pattern.

---

## Suggested reading order when you revisit

1. `synthetic-data/deployments.json` (the world)
2. `errors.py` (the vocabulary of refusals)
3. `models.py` (the data shapes: Environment, DeploymentStatus, ToolResult, ExecutionContext, Decision)
4. `tools/deployment_status.py` (shape check + the tool's contract)
5. `policy.py` (the authorization ring — separate from validation, denies production a second time)
6. `tests/test_tool_contract.py` and `tests/test_policy.py` (proof of every rule)
