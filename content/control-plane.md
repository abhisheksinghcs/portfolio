# Sanitized AI Control-Plane Architecture

> A reference architecture for a policy-enforcing control plane that mediates every interaction between applications, foundation models, tools, and enterprise data. Designed to make security, governance, and observability *structural* rather than bolted on.

**Author:** Abhi Singh, Principal AI Security Architect
**Status:** Living document — sanitized from production deployments
**Audience:** Security architects, platform engineers, AI infrastructure leads

---

## 1. Problem statement

Enterprises are wiring foundation models directly into applications, copilots, and agents faster than their security and governance functions can catch up. The result is a sprawl of:

- Direct SDK calls from application code to model providers, with credentials and prompts scattered across services.
- Ad-hoc retrieval pipelines that bypass data-loss prevention (DLP) and access controls.
- Agents invoking tools with over-broad privileges and no auditable decision trail.
- No consistent place to enforce policy, redact sensitive data, rate-limit, or evaluate output quality.

An **AI control plane** consolidates these concerns into a single, policy-driven layer that every AI interaction flows through.

## 2. Design goals

1. **Single ingress for AI traffic.** All model, tool, and retrieval calls traverse the control plane.
2. **Identity-aware.** Every request carries a verifiable caller identity (user, service, or agent) and a purpose.
3. **Policy as code.** Access, redaction, routing, and safety policies are declarative, versioned, and testable.
4. **Provider-agnostic.** Applications target a stable internal contract; model and tool providers are swappable.
5. **Fully auditable.** Every decision — allow, deny, redact, reroute — is logged with sufficient context to reconstruct.
6. **Fail safe, not open.** Policy-engine outages degrade to deny or to a constrained default model, never to unmediated egress.

## 3. Logical architecture

```
                     ┌────────────────────────────────────────────┐
                     │              Client surfaces                │
                     │  apps · copilots · agents · notebooks · CI  │
                     └───────────────────┬────────────────────────┘
                                         │  (authenticated, purpose-tagged)
                                         ▼
                     ┌────────────────────────────────────────────┐
                     │              AI Control Plane               │
                     │                                            │
                     │  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
                     │  │  Ingress │→ │  Policy  │→ │  Router  │  │
                     │  │  + AuthN │  │  Engine  │  │  + Cache │  │
                     │  └──────────┘  └──────────┘  └────┬─────┘  │
                     │        │            │             │        │
                     │        ▼            ▼             ▼        │
                     │  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
                     │  │ Redaction│  │  Safety  │  │  Audit   │  │
                     │  │  / DLP   │  │  Filters │  │  Sink    │  │
                     │  └──────────┘  └──────────┘  └──────────┘  │
                     └───────┬──────────────┬────────────┬────────┘
                             ▼              ▼            ▼
                     ┌─────────────┐ ┌────────────┐ ┌────────────┐
                     │ Model pools │ │ Tool broker│ │ Retrieval  │
                     │ (multi-vend)│ │ (MCP, APIs)│ │ (RAG, KGs) │
                     └─────────────┘ └────────────┘ └────────────┘
```

## 4. Core components

### 4.1 Ingress & authentication
- Terminates TLS and authenticates the caller against the enterprise identity provider.
- Resolves the caller into a **principal** (user, workload, or agent identity) plus a **purpose tag** (e.g. `support-copilot:draft-reply`).
- Rejects anonymous or purpose-less traffic at the edge.

### 4.2 Policy engine
- Evaluates declarative policies (OPA/Rego, Cedar, or an internal DSL) against the request envelope.
- Produces a **decision object**: allow / deny / transform, plus obligations (e.g. "redact PII", "log to regulated sink", "route to on-prem model").
- Policy bundles are versioned, signed, and rolled out with canary + rollback.

### 4.3 Redaction & DLP
- Applies obligations from the policy engine before egress: PII / secret redaction, entity replacement, prompt hygiene.
- Symmetric on the response path: re-hydration where authorized, or permanent removal where not.

### 4.4 Safety filters
- Model-agnostic pre- and post-filters for prompt injection, jailbreaks, self-harm, and category-specific harms.
- Runs alongside — not instead of — provider-native safety systems.

### 4.5 Router & cache
- Selects a model or model pool based on policy, cost, latency, and capability requirements.
- Deterministic cache for eligible requests keyed on redacted inputs to reduce cost and leakage surface.

### 4.6 Tool broker
- Central authority for tool invocation (MCP servers, internal APIs, code execution).
- Enforces per-tool authorization, argument schemas, and rate limits.
- Emits structured tool-call events for the audit sink.

### 4.7 Audit sink
- Append-only, tamper-evident log of every decision and every model/tool interaction.
- Split streams: operational (short retention, high volume) and compliance (long retention, redacted).

## 5. Request lifecycle

1. Client sends a request with an identity token and purpose tag.
2. Ingress authenticates and normalizes into an internal envelope.
3. Policy engine evaluates and returns a decision + obligations.
4. Redaction/DLP applies input obligations.
5. Router selects a model or tool; cache is consulted.
6. Provider is invoked with a scoped, short-lived credential minted by the control plane.
7. Safety filters and output obligations run on the response.
8. Audit sink records the full decision trail with a correlation ID returned to the client.

## 6. Threat model (summary)

| Threat | Control plane mitigation |
|---|---|
| Credential sprawl to model providers | Providers only accept credentials minted by the control plane; app code never holds them. |
| Prompt injection via retrieved content | Retrieval passes through content-provenance tagging and injection classifiers before reaching the model. |
| Over-privileged tool use by agents | Tool broker enforces per-purpose allowlists and argument schemas; sensitive tools require human-in-the-loop. |
| Data exfiltration via model output | Output DLP + egress allowlist; regulated data classes cannot leave without explicit policy. |
| Silent model swaps | Router decisions are logged; model+version is part of the audit record and surfaced to callers. |
| Policy engine outage | Fail-closed default with a constrained "safe mode" model pool for approved critical paths. |

## 7. What this document deliberately omits

- Vendor names, product SKUs, and internal service names from the deployments this is derived from.
- Customer-specific policies, data classes, and org structures.
- Exact latency and cost numbers — see the [impact stories](/content/impact-stories.md) for sanitized outcomes.

## 8. Related work on this site

- [Agent Security & Governance Framework](/content/agent-security.md) — how agents plug into this control plane.
- [GenAI Observability Model](/content/observability.md) — the telemetry contract the audit sink emits against.
- [Publications & Whitepapers](/content/publications.md) — longer-form background.

---

*Feedback and corrections welcome. This document is intentionally sanitized; if you are evaluating this architecture for a specific environment, reach out via the channels listed on the [home page](/index.html).*
