# The AI Control-Plane Pattern

This is the reference pattern that the [Control-Plane RFC](/content/control-plane.md), the [Agent Security RFC](/content/agent-security.md), and the [Observability RFC](/content/observability.md) all implement. Start here if you want the shape before the implementation details.

## The problem this pattern solves

Every application team building GenAI features ends up making the same six decisions independently:

- Which user, workload, or agent identity they trust.
- Which model, tool, and data source is allowed to be reached.
- How tenant and user boundaries are preserved through retrieval and tool use.
- What gets classified, redacted, or blocked on the way in.
- What gets classified, redacted, or blocked on the way out.
- What gets logged, at what fidelity, and for how long.

Left to individual teams, each decision gets made differently. The predictable consequences:

- The security team can't tell which application is calling which model, on whose behalf, with what data.
- Rotating a provider key is an org-wide change-management event instead of a same-day operation.
- A tenant leak in one application doesn't get caught by controls in another.
- Every prompt-injection incident is investigated from scratch because the trace shapes don't match.
- Agents — which act, not just answer — inherit these gaps and turn them into side effects on real business systems.

For chat-style applications the cost is fragmentation. For agentic systems the cost is a compromised principal quietly writing to production. That is why the same pattern that used to be optional for enterprise AI is now a baseline for agentic AI.

## The pattern in two lines

Separate the plane that decides what is allowed from the plane that executes the work.

- **Control plane** — owns policy intent and governance state. Registry of agents, models, tools, and MCP servers. Policy definitions and versions. Identity blueprints. Risk classifications. The policy decision point (PDP) that evaluates them.
- **Execution plane** — carries the actual traffic. Agent runtimes, retrieval services, model providers, MCP servers, and the business systems those tools touch. Every consequential boundary in this plane runs a policy enforcement point (PEP) that asks the PDP for a decision, in-path, on every request.

The two planes are connected by two things going in opposite directions: signed policy bundles going out, and evidence coming back in.

## Where the components live

Not everything belongs in one place. The control plane holds authority; the execution plane holds the traffic.

| Function | Plane | Concrete choice in this reference |
|---|---|---|
| Agent / model / tool / MCP registry | Control | Single source of truth for what exists, who owns it, and its trust class. |
| Policy definitions and versions | Control | Signed OPA bundles, canary + rollback, per-tenant thresholds. |
| Identity blueprints and lifecycle | Control | Entra Agent ID (or equivalent) with delegation chain and sponsor. |
| Risk classification and exceptions | Control | Governance-owned. App teams do not self-classify. |
| Policy decision point (PDP) | Logically central, physically replicated | OPA sidecar over UDS in each pod. Off-box PDPs blow the 20 ms budget. |
| Edge / API gateway | Execution, distributed by region | Envoy at PoP or Azure APIM. Handles TLS, OIDC verify, cheap classifier gates. |
| Origin control plane | Execution, per environment | Applies obligations (redact/route/log), mints ephemeral credentials, runs output DLP. |
| Tenant-isolated retrieval | Execution, at the vector store | Namespace per tenant. Tenant resolved from the token, not the request body. |
| Tool authorization | Execution, at gateway AND at tool | The gateway check does not replace the tool's own OAuth resource-server check. |
| Business systems | Execution, unchanged | The CRM, ERP, or database still runs its own row-level authorization. |
| Telemetry collection | Execution, correlated centrally | Local OpenTelemetry collectors, tamper-evident audit sink. |

The subtle bit: a PEP straddles both planes. Its policy comes from the control plane, but it runs directly in the execution path. That is why "centralize governance" does not mean "put every AI request behind one central service."

## Where enforcement has to sit

If you skip any of these six boundaries, the pattern does not hold. Each one needs a PEP wired to the same PDP.

| # | Boundary | What the PEP decides | What breaks if it is missing |
|---|---|---|---|
| 1 | Agent admission | Is this principal + purpose allowed to invoke this agent at all? | Unauthenticated or purpose-less traffic reaches the model. |
| 2 | Retrieval | Does this token authorize access to this namespace, with these filters? | Cross-tenant vector leaks; embedding-inversion attacks recover PII. |
| 3 | Model invocation | Is this model + version approved for this data class and region? | Silent model swaps; regulated data goes to a consumer-grade endpoint. |
| 4 | Tool proposal | Is the agent allowed to call this tool with these arguments right now? | Model output containing a `delete` or `transfer` is treated as authority to act. |
| 5 | Resource-side authorization | Does the target system independently authorize this specific action? | Confused deputy — the CRM trusts the gateway's word for who the user is. |
| 6 | Side effect | Was human approval obtained for the high-impact operations that require it? | Autonomous agents commit financial or destructive actions with no human in the loop. |

Boundaries 1–3 are what the [Control-Plane RFC](/content/control-plane.md) covers. Boundaries 4–6 are what the [Agent Security RFC](/content/agent-security.md) covers. Every boundary produces evidence that the [Observability RFC](/content/observability.md) correlates.

## What this pattern is not

Three things this pattern is deliberately not, because misunderstanding any of them turns a security control into security theater.

- **Not a single pane of glass.** A registry that lists your agents is inventory, not enforcement. If an agent runs in an SDK path that never hits your gateway, listing it in a portal does not govern it. Inventory without interception is visibility.
- **Not a replacement for resource-side authorization.** A gateway PEP can say "this agent is allowed to call the CRM's `update` API." The CRM still has to independently authorize the specific record change. Skipping this is how confused-deputy incidents happen.
- **Not a monolith.** The PDP is logically central but physically replicated as a sidecar. Off-box PDP calls on the hot path burn 30–80 ms per hop; they do not survive the 20 ms budget. Central policy authority, distributed enforcement — not central service, distributed clients.

## Rule of thumb

If a change alters what your agents may do at all, it is a control-plane change. If a change alters what the current request does, it is an execution-plane change. A PEP is where the first decides the second.

## Where to go next

- [Control-Plane RFC](/content/control-plane.md) — edge gateway, OIDC-to-ephemeral-credential exchange, RAG namespace isolation, ZDR mandate. Boundaries 1–3.
- [Agent Security RFC](/content/agent-security.md) — tool authorization, argument schemas, delegation chains, human-in-the-loop. Boundaries 4–6.
- [Observability RFC](/content/observability.md) — trace schema, decision evidence, drift detection, audit integrity.
