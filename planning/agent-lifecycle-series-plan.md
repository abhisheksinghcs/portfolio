# Planning: The Secure Agent Lifecycle — Articles 2–6

Internal planning document. Not part of the published site: not linked from `index.html`, `llms.txt`, `README.md`, or the series landing page (`content/agent-lifecycle.md`). This repo has no draft/staging mechanism (no static-site-generator config, no `_drafts` folder — content is hand-authored `.md`/`.html` pairs indexed manually via `llms.txt`), so future-article outlines live here instead of as published placeholder pages.

Series landing page: `content/agent-lifecycle.md`. Article 1 (Define) is fully drafted at `content/agent-lifecycle-01-define.md` / `.html`.

When drafting an article below: create `content/agent-lifecycle-0N-<slug>.md` + `.html` (same zero-md wrapper template as the existing articles), fully write it, then add it to `content/agent-lifecycle.md`'s "Available now" list, `llms.txt`'s Core Work or a new lifecycle section, and remove its outline from this file (or mark it drafted).

**Structural convention (established in Article 1):** each concept-bearing section should have a `### The concept` subsection (the general principle, no EngBot specifics) followed by a `### Applied to EngBot` subsection (naming the specific Azure service, identity, or policy this stage adds). Don't blend the two into one paragraph.

---

## Article 2 — Identify: The Agent Identity Model — **drafted**, see `content/agent-lifecycle-02-identify.md`.

## Article 3 — Build: Choosing and Building the Harness

**Running-scenario coverage:** Stages 1–2, infrastructure decision before Stage 2 ships.
**Maps to:** the `agent-runtime-and-enforcement.md` explainer (harness vs application enforcement tier), not a new RFC boundary.

Outline:
- The build decision Article 1 deferred: does this agent need Microsoft Agent Framework / a Foundry hosted agent, or does a direct model call still suffice once retrieval is added at Stage 2?
- Walk the three deployment shapes from `agent-runtime-and-enforcement.md` (custom RAG app, Foundry hosted agent, simple gateway-managed app) applied specifically to this agent's Stage 2 requirements.
- Where enforcement code actually lives once a harness exists: middleware, filters, hooks, tool wrappers, retrieval wrappers — concrete to this scenario, not generic.
- Explicit non-goal: don't add a harness merely because "agents have harnesses" — justify it against what Stage 2 (retrieval coordination, session state) actually requires that a direct call doesn't provide.
- Failure mode: harness owns retries/memory but the team assumes it also owns authorization — restate "a harness that contains some enforcement code is not automatically fully enforced everywhere."

## Article 4 — Connect: Retrieval and Read-Only Tools

**Running-scenario coverage:** Stage 2 (retrieval) and Stage 3 (read-only tool calls).
**Maps to:** RFC-014 §6 (retrieval authorization, the three isolation-tier comparison) and RFC-015 §5 (tool proposal, scoped to read-only tools specifically).

Outline:
- Stage 2 walkthrough using the eight-question framework: new capability (Azure AI Search retrieval), new authority (read access to an authorized document set), identity acting (still the Stage 1 agent identity, now with a retrieval grant), data exposed (internal engineering docs, scoped), PEP needed (boundary 2), evidence (retrieval_provenance field per RFC-016), what can fail (retrieval filter misapplied, retrieved content treated as instructions instead of data), residual risk (embedding-inversion / cross-tenant leak if isolation tier chosen poorly).
- Which retrieval isolation tier fits this scenario (shared index with filters is likely sufficient for an internal engineering-docs use case; note the decision is risk-tier-owned, not universal, per RFC-014 §6).
- Stage 3 walkthrough, same eight questions, for read-only tools (e.g., "check deployment status," "look up a ticket") — emphasize read-only tools still need boundary 4 (tool proposal / grant check) even though they can't cause a side effect; the risk here is information disclosure, not action.
- Explicit contrast with Article 5: read-only tools don't need boundary 6 (human approval); that's what changes at Stage 4.

## Article 5 — Authorize: Proposing and Approving Changes

**Running-scenario coverage:** Stage 4 (proposes changes) and Stage 5 (performs approved changes).
**Maps to:** RFC-015 §6–7 (resource-side authorization, side effect / human approval), plus RFC-015 §9 (pre-deployment red-teaming informing this stage's impact tier).

Outline:
- Stage 4 walkthrough: the agent can now propose a ticket update, a config change, or a deployment trigger — but proposing is not executing. Reinforce "the model proposes, the enforcement layer validates and coordinates, the resource system authorizes and executes" from the runtime/enforcement explainer.
- Impact classification for this specific agent's tool set: which of its actions are low-impact (e.g., adding a comment to a ticket) vs high-impact (e.g., triggering a deployment) — illustrative, not universal, per RFC-015 §7.
- Stage 5 walkthrough: the approval gate itself (Power Automate / Logic Apps pattern from RFC-015 §7), resource-side RBAC assigned to the agent identity specifically (not the hosting workload's managed identity), and what evidence a completed, approved action produces.
- Microsoft Agent 365 as a pre-approval check, not just a post-hoc dashboard: before a high-impact proposal is approved, the approval workflow reads EngBot's current Agent 365 registry status (active, sponsored, not flagged or blocked). An agent flagged or blocked in Agent 365 doesn't get a proposed action approved regardless of what its tool grant says — this is RFC-014 §5's “agent lifecycle and risk state” bullet, applied concretely at the moment of approval rather than only at admission.
- Failure modes specific to this scenario: approval workflow unavailable during an on-call window: does the change wait, or does someone override it manually, and what does that override itself have to produce as evidence.
- Residual risk to state plainly: an approver who rubber-stamps proposals reintroduces the excessive-agency risk this stage exists to prevent (same caution as RFC-015 §12).

## Article 6 — Observe and Operate: Running It, Detecting Drift, Retiring It

**Running-scenario coverage:** ongoing, all five stages, plus what changes when the agent is decommissioned.
**Maps to:** RFC-016 in full (event schema, native telemetry mapping, drift detection).

Outline:
- What's different about *operating* this agent versus building it: the same eight-question framework now applies continuously, not just at each stage's launch.
- Concrete dashboards/queries for this scenario specifically: review-rate drift on the Stage 1 classifier, retrieval-provenance anomalies at Stage 2–3, approval-latency and override-rate at Stage 4–5 — grounded in RFC-016 §7's illustrative KQL pattern, not new queries invented here.
- **Microsoft Agent 365**: the registry and posture surface for EngBot specifically — whether its registry entry (owner, sponsor, configured tools, instructions) is still accurate months after Stage 5 shipped. This is the same registry Article 5's approval gate reads from at authorization time; here it's the operator's own view of the same data, per RFC-014 §3 and §5.
- **Microsoft Defender**: two distinct angles, not one. Defender XDR's `AIAgentsInfo`/`AgentsInfo` advanced hunting table for posture queries scoped to EngBot (missing instructions, an MCP tool configured that its owner forgot about, no authentication on an exposed endpoint) — a snapshot, not a decision event, per RFC-016 §4.2. Separately, Defender for Cloud AI Threat Protection alerts (`DetectionSource == "Microsoft Defender for AI Services"`) correlated against EngBot's own decision-evidence stream by `correlation_id` or principal, per RFC-016 §7's illustrative join.
- **Microsoft Purview**: DLP, Insider Risk Management, and Communication Compliance applied to EngBot's Stage 4–5 outputs — the proposed or executed ticket and configuration changes — catching sensitive content in a drafted change even when identity-based authorization at Stage 5 already passed, the same content-based backstop described in RFC-015 §6.
- Decommissioning: what "retire this agent" actually means for an Entra Agent ID identity (disable, don't just stop calling it), what evidence a retirement should produce, and the honest gap this leaves (RFC-015 §13 defers detailed lifecycle remediation to itself, not this series).
- Close the series: point back to the landing page's boundary-mapping table and to the RFCs for anyone who arrived here first and now wants the reference architecture.
