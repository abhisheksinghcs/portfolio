# Python concepts — Q&A notes

Plain-language answers to questions raised while walking through the code, so you
can refer back and re-explain them. Each entry names the file and symbol it
relates to.

---

## `@lru_cache` — `tools/deployment_status.py`, `_load_deployments()`

`lru_cache` (from `functools`) makes a function **remember its return value** so
the body runs only once.

```python
@lru_cache(maxsize=1)
def _load_deployments() -> tuple[dict, ...]:
    with _SYNTHETIC_DATA.open(encoding="utf-8") as handle:
        return tuple(json.load(handle))
```

- **Why:** read `deployments.json` from disk once, then reuse the parsed data on
  every later tool call instead of re-reading and re-parsing.
- **`maxsize=1`:** the function takes no arguments, so there is only ever one
  possible result to cache — one slot is enough.
- **Pairs with `tuple(...)`:** the cached value is shared by all callers, so we
  return an *immutable* tuple; no caller can mutate the shared data.
- **Trade-off:** because the file is read once and frozen, tests can't rely on
  editing the JSON mid-run. That's why `get_deployment_status(..., deployments=)`
  accepts injected records — tests bypass the cache and stay pure.
- **Not a security control** — just a performance/safety convenience.

---

## `@dataclass` — `models.py` (`ToolResult`, `ExecutionContext`, `Decision`)

A **dataclass** is a class whose job is to hold data. The decorator generates the
constructor, `__repr__`, and `__eq__` from the field declarations, so you don't
hand-write boilerplate.

```python
@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str | None = None
```

- **`frozen=True` = immutable.** Once created, fields can't be reassigned. A
  `Decision` of "denied" can't later be flipped to "allowed"; a `ToolResult`
  can't be tampered with. This is a security-relevant property.
- **Value equality for free.** Two dataclasses with equal fields compare equal —
  clean, honest tests.

### dataclass vs Pydantic (both live in `models.py`)
- **Pydantic `BaseModel`** (e.g. `DeploymentStatus`, tool arguments) = **validate
  untrusted input** coming from outside (records, model output).
- **`@dataclass`** (`Decision`, `ExecutionContext`, `ToolResult`) = **internal,
  already-trusted values our own code creates**. They need structure and
  immutability, not validation. Using the lighter tool signals "trusted internal
  data."

---

## `Iterable[Environment]` + `frozenset` — `policy.py`, `Policy.__init__`

```python
def __init__(self, allowed_environments: Iterable[Environment] | None = None):
    self._allowed_environments = (
        frozenset(allowed_environments)
        if allowed_environments is not None
        else self.DEFAULT_ALLOWED_ENVIRONMENTS
    )
```

- **`Iterable[Environment]`** is a *type hint on the input*: "anything you can
  loop over" — set, list, tuple, generator. It's the most permissive input type,
  so callers pass whatever container is convenient.
- **`frozenset(...)`** is what we *store*: an **immutable set**. Two benefits:
  1. Immutable — the allowlist can't be mutated after the policy is built.
  2. Fast O(1) membership for the hot `environment not in ...` check.
- **The idiom:** *accept the broadest type in (`Iterable`), normalize to the
  safest type inside (`frozenset`)* — flexible at the boundary, strict
  internally.

---

## How `models.py` and `policy.py` work together

`models.py` is the **shared vocabulary**; `policy.py` is a **consumer**.

```
models.py defines:   Environment, ExecutionContext, Decision   (the types)
                                   |  imported by
                                   v
policy.py uses them:  authorize(arguments[Environment],
                                context[ExecutionContext]) -> Decision
```

- `policy.py` imports `Decision`, `Environment`, `ExecutionContext` from
  `models.py`. It **reads** `Environment`, **receives** an `ExecutionContext`,
  and **returns** a `Decision`.
- `models.py` does **not** import `policy.py` — the dependency points one way:
  shared data types at the bottom, enforcement logic on top.
- The harness loop (later) will reuse the *same* types, so every layer speaks one
  consistent vocabulary.

---

## `Protocol` + lazy import — `model_client.py`

### `Protocol` (structural interface)
```python
class ChatModel(Protocol):
    def complete(self, *, messages, tools): ...
```
A `Protocol` (from `typing`) describes a *shape* — "anything with a `complete`
method like this counts as a `ChatModel`." Unlike a base class, a type doesn't
have to inherit from it; it just has to have the right method. This is
"duck typing, checked by the type checker." We use it so the harness depends on
the *interface*, not the OpenAI SDK — a fake client in tests satisfies the
protocol without any network or credentials, and Stage 1B can substitute a
different implementation.

### Lazy import
```python
@staticmethod
def _build_client(config):
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from openai import OpenAI
    ...
```
The SDK imports live *inside* the method, not at the top of the file. So
importing `model_client.py` (e.g. in tests that inject a fake) never requires the
SDK or credentials to be present — only the real credential path pays that cost.
This keeps tests hermetic and the module cheap to import.

### `dataclasses.field` note
`ModelConfig` is a frozen dataclass built from environment variables via
`from_env(env=None)`, which accepts an injected mapping so tests don't touch the
process environment.

---

## Deep dive: `Protocol` vs. a base class (ABC)

Both express "this thing has a `complete` method," but differently.

**Base class (nominal typing)** — relationship by inheritance:
```python
from abc import ABC, abstractmethod
class ChatModel(ABC):
    @abstractmethod
    def complete(self, *, messages, tools): ...
class FoundryChatModel(ChatModel):        # must inherit
    def complete(self, *, messages, tools): ...
```
`FoundryChatModel` is a `ChatModel` only because it *inherits*. A test fake would
also have to import and subclass it.

**Protocol (structural typing)** — relationship by shape:
```python
from typing import Protocol
class ChatModel(Protocol):
    def complete(self, *, messages, tools): ...
class FoundryChatModel:                    # no inheritance
    def complete(self, *, messages, tools): ...
```
Anything with a matching `complete` method *counts as* a `ChatModel` — no
inheritance, no import of the protocol. "Duck typing, checked by the type
checker."

**Why Protocol here:** the harness depends on the *shape*, not our SDK wrapper;
test fakes need no imports/subclassing (hermetic tests); Stage 1B can swap in a
different implementation with the same method shape and the loop never changes.

**When a base class is better:** when you want to *share implementation* (concrete
inherited helpers) or enforce the relationship at runtime. ABCs = shared lineage
and code; Protocols = interface shape only. Note Protocols are primarily a
*static* check (Pyright/mypy) unless you add `@runtime_checkable` + `isinstance`.

---

## Deep dive: how `get_bearer_token_provider` gets a token

```python
token_provider = get_bearer_token_provider(DefaultAzureCredential(), scope)
```

- **`DefaultAzureCredential()`** is a *credential chain*. Asked for a token it
  tries, in order: env vars / workload identity, managed identity (in Azure),
  Azure CLI (`az login` — local dev), Azure Developer CLI, VS Code, etc., and
  uses the first that works. Same code authenticates as your CLI identity locally
  and as a managed identity in production — no code change.
- **The scope** (`https://ai.azure.com/.default`) is the OAuth *audience*: "a
  token valid for the Foundry/AI resource." `.default` = all static permissions
  the identity already has there (granted via the `Cognitive Services OpenAI
  User` RBAC role).
- **`get_bearer_token_provider(...)` returns a callable** (zero-arg function). It
  does *not* fetch a token immediately. Each call: `credential.get_token(scope)`
  -> `AccessToken(token, expires_on)`, caches it, returns the raw JWT string, and
  refreshes automatically near expiry.
- **The OpenAI v1 client** accepts that provider as `api_key`, calls it before
  each request, and sends `Authorization: Bearer <JWT>`. Foundry validates the
  JWT (signature, audience, expiry) and checks RBAC before serving.

**Why it matters:** no stored secret; short-lived tokens fetched on demand and
auto-refreshed. Nothing to leak into logs, evidence, or source. This is why the
brief mandates Entra auth over API keys.

---

## Deep dive: why lazy imports matter

```python
@staticmethod
def _build_client(config):
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider
    from openai import OpenAI
    ...
```

Imports live *inside* the method, not at file top. Effects:
- **Deferred cost:** `openai` + `azure.identity` pull large dependency trees; if
  you only ever inject a fake client (tests), that cost is never paid.
- **Imports without the SDK/credentials present:** `import
  change_agent.model_client` works in any environment; only the real-client path
  needs the packages installed and an identity available -> hermetic tests.
- **Failures where they're meaningful:** a missing credential/SDK surfaces when
  you build the real client, not at import time or in unrelated tests.

**Trade-off:** top-level imports are clearer and lint/type-check more easily;
lazy imports slightly hide a dependency and re-run import machinery per call
(cheap after the first — Python caches in `sys.modules`). Rule of thumb: import
at the top by default; go lazy when the dependency is heavy, optional, or
environment-specific (all three true for the Azure SDK).

---

## Factory function vs. singleton — `tool_registry.py`, `default_registry()`

`default_registry()` is a **factory**: each call builds and returns a *new*
`ToolRegistry`. The alternative is a **singleton**: one shared instance everyone
reuses.

```python
# Factory (what we use)
def default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(RegisteredTool(name="get_deployment_status", ...))
    return registry

# Singleton (alternative)
REGISTRY = ToolRegistry()          # built once at import
REGISTRY.register(RegisteredTool(name="get_deployment_status", ...))
```

**Why a factory here:**
1. **Test isolation** — each test gets a fresh registry; one test's `register(...)`
   can't leak state into another (no order-dependent failures).
2. **No shared mutable global** — `ToolRegistry` is mutable (`register` changes
   it); a shared mutable module-level object invites action-at-a-distance.
3. **Explicit configuration** — a factory can take args later
   (`default_registry(include_write_tools=False)`); a singleton bakes in one
   config.
4. **Import-time safety** — a module-level singleton runs setup on import, whether
   or not it's used; a factory defers work to call time.

**When a singleton is better:** the object is immutable/stateless (safe to share)
or a genuinely unique, expensive resource you want exactly one of — DB connection
pool, loaded config, cache, logger, or a network client. (This is why the model
client is built once and reused, and why `_load_deployments()` uses an
`lru_cache` — immutable data, safe to share.)

**Deciding question:** is the object cheap+mutable (favor a factory) or
expensive/unique+safe-to-share (favor a singleton)?

**In-between:** put `functools.lru_cache` on a factory to get a *lazy singleton* —
first call builds, later calls reuse. We deliberately don't do that for the
registry (we want fresh instances) but do for `_load_deployments()`.

---

## Sink (write-only destination) — `evidence.py` + `cli.py`

A **sink** is a destination that consumes data you hand it, without you needing to
know what it does with it. It's the opposite of a *source*. In code it's usually
just **a callable you call with each item**; the callable decides where the item
ends up (print, file, logging service, list, or discard).

```python
# Producer (evidence.py): knows nothing about the destination.
def emit(self, ...):
    event = EvidenceEvent(...)
    self._events.append(event)
    if self._sink is not None:
        self._sink(event.to_dict())     # hand it off; don't care where it goes
    return event
```

`sink` is "a callable that takes one dict." Different callers plug in different
destinations **without changing the producer**:
- **Tests:** `sink=captured.append` — events land in a list to assert on.
- **CLI:** `evidence_sink=lambda e: print(json.dumps(e), file=sys.stderr)`.
- **Production:** a sink that writes to Azure Monitor / a SIEM.

**Payoff:** one producer, many destinations, zero coupling. Redirect output by
swapping the sink. (Same idea as a Unix stream redirect, or the observer/callback
pattern — a sink is the write-only end of a pipe.)

**CLI stream discipline:** the CLI sends the *answer* to **stdout** and the
*evidence sink* to **stderr**, so they can be piped independently
(`change-agent "..." 2> evidence.log`).

---

## Domain concept: a "proposal" and its `tool_call_id`

**Proposal.** When the harness calls the model with `tools=...`, the model may
answer with either final text or a *tool call* — a request to run a tool. We call
that a **proposal** because it carries no authority: it is a suggestion our
deterministic code may accept or reject (resolve -> validate -> authorize ->
execute). A jailbroken or mistaken model can propose anything; that is fine,
because a proposal is a request, not a command.

**Where `tool_call_id` comes from.** The model/service generates it. A tool-call
response looks like:

```json
{
  "role": "assistant",
  "content": null,
  "tool_calls": [
    { "id": "call_abc123", "type": "function",
      "function": { "name": "get_deployment_status",
                    "arguments": "{\"application\":\"payments-api\", ...}" } }
  ]
}
```

- `id` (`call_abc123`) — minted by the model/service, not by us.
- `function.name` — untrusted; checked against the registry.
- `function.arguments` — an untrusted JSON *string*; `json.loads` + Pydantic
  validated.

**How the id relates to the proposal.** The `tool_call_id` *is* the identity of
that proposal — the correlation key that binds a *result* back to the *request*.
After running the tool, we send a `role:"tool"` message reusing the same id:

```
assistant -> tool_calls: [ { id: "call_abc123", name: ..., arguments: ... } ]  # proposal
tool      -> { tool_call_id: "call_abc123", content: {"outcome":"success",...} } # its result
```

The model reads `tool_call_id` to know which result answers which call. A broken
id breaks the binding, so `Harness._check_correlation` fails closed on missing or
reused ids, and Stage 1A allows only one proposal per turn.

**Analogy:** a purchase requisition. The model files a requisition (proposal)
stamped with a tracking number (`tool_call_id`); procurement (the harness)
approves/denies, fulfills if allowed, and files the outcome under the same
tracking number. The requisition authorizes nothing — approval does.

---

## Where different guardrails belong (not everything goes in policy)

Policy is the home for **authorization** guardrails, but each layer owns a
different kind of check. Put a guardrail at the layer that owns its concern:

| Guardrail kind | Home | Examples |
|---|---|---|
| **Shape / structure** of arguments | Pydantic argument model (`tools/…`) | required fields, types, enum values, string patterns, numeric ranges, `extra="forbid"` |
| **Which tools exist at all** | Tool registry allowlist | only registered tools resolve; unknown -> fail closed |
| **Whether a valid proposal is permitted** | `policy.py` | caller/agent/tenant/purpose, environment, approval required, resource ownership, quotas |
| **The tool's own contract** | Tool implementation | read-only, its own production denial, known-target limits, target-side authZ |
| **Budgets & protocol** | Harness / `HarnessLimits` | max steps, max tool calls, timeout, `tool_call_id` correlation, output normalization |
| **Behavioral steering** | Instructions (system prompt) | *not a control* — guidance only |

Guidance:
- A guardrail about **"is this allowed?"** -> policy. Expand `ExecutionContext`
  (add caller roles, tenant, approval state, resource owner) and add rules to
  `Policy.authorize`.
- A guardrail about **"is this well-formed?"** -> the argument schema, not policy.
- A guardrail the **target must enforce regardless of caller** -> the tool itself
  (defense in depth; e.g. production is denied by *both* policy and the tool).
- A guardrail about **"how much / how long"** -> harness budgets.

So "further guardrails go in policy" is correct *for authorization rules*; for
other kinds, prefer the layer that owns the concern, and use two layers when the
control is important enough to deserve defense in depth.
