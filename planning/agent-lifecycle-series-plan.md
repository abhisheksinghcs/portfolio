# Planning: The Secure Agent Lifecycle — Articles 2–6

Internal planning document. Not part of the published site: not linked from `index.html`, `llms.txt`, `README.md`, or the series landing page (`content/agent-lifecycle.md`). This repo has no draft/staging mechanism (no static-site-generator config, no `_drafts` folder — content is hand-authored `.md`/`.html` pairs indexed manually via `llms.txt`), so future-article outlines live here instead of as published placeholder pages.

Series landing page: `content/agent-lifecycle.md`. Article 1 (Define) is fully drafted at `content/agent-lifecycle-01-define.md` / `.html`.

When drafting an article below: create `content/agent-lifecycle-0N-<slug>.md` + `.html` (same zero-md wrapper template as the existing articles), fully write it, then add it to `content/agent-lifecycle.md`'s "Available now" list, `llms.txt`'s Core Work or a new lifecycle section, and remove its outline from this file (or mark it drafted).

**Structural convention (established in Article 1):** each concept-bearing section should have a `### The concept` subsection (the general principle, no EngBot specifics) followed by a `### Applied to EngBot` subsection (naming the specific Azure service, identity, or policy this stage adds). Don't blend the two into one paragraph.

---

## Article 2 — Identify: The Agent Identity Model

**Running-scenario coverage:** Stage 1 identity groundwork, ahead of Stage 2's retrieval access.
**Maps to:** RFC-014 §5 (Entra Agent ID: blueprint, blueprint principal, individual agent identity, sponsor, application-only vs delegated access).

Outline:
- Recap: Article 1 created an agent identity with no permissions. This article covers what that identity actually is and how it's governed.
- The three-identity distinction in depth: user identity, Entra Agent ID agent identity, managed/workload identity (federation vs client secret) — link to RFC-014 §5's concept table rather than re-deriving it; add narrative framing (why a security review asks "which identity did this?" three different ways).
- Sponsor and lifecycle: who owns the agent's purpose, what "sponsor leaves the org" actually triggers, how an agent identity gets blocked/retired later (forward reference to Article 6 / RFC-015 out-of-scope items on Agent 365 registry actions).
- Autonomous vs delegated interaction mode for *this* agent specifically: at Stage 1–2 EngBot is autonomous (no per-user delegation yet); note where delegated mode would change the identity story if a future stage added "on behalf of the requesting engineer."
- Failure mode to cover: identity created but never granted a sponsor, or granted a sponsor who leaves before Stage 2 — what breaks, what Entra ID does automatically (sponsorship transfer to manager, per RFC-014 §5).
- Close by handing off to Article 3: the identity exists; now decide what runs it.

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
- Failure modes specific to this scenario: approval workflow unavailable during an on-call window: does the change wait, or does someone override it manually, and what does that override itself have to produce as evidence.
- Residual risk to state plainly: an approver who rubber-stamps proposals reintroduces the excessive-agency risk this stage exists to prevent (same caution as RFC-015 §12).

## Article 6 — Observe and Operate: Running It, Detecting Drift, Retiring It

**Running-scenario coverage:** ongoing, all five stages, plus what changes when the agent is decommissioned.
**Maps to:** RFC-016 in full (event schema, native telemetry mapping, drift detection).

Outline:
- What's different about *operating* this agent versus building it: the same eight-question framework now applies continuously, not just at each stage's launch.
- Concrete dashboards/queries for this scenario specifically: review-rate drift on the Stage 1 classifier, retrieval-provenance anomalies at Stage 2–3, approval-latency and override-rate at Stage 4–5 — grounded in RFC-016 §7's illustrative KQL pattern, not new queries invented here.
- Native telemetry surfaces this scenario would actually touch: Defender XDR's `AIAgentsInfo`/`AgentsInfo` posture table (is this agent's registry entry still accurate months after Stage 5 shipped), Microsoft Agent 365 observability spans if the harness chosen in Article 3 emits them.
- Decommissioning: what "retire this agent" actually means for an Entra Agent ID identity (disable, don't just stop calling it), what evidence a retirement should produce, and the honest gap this leaves (RFC-015 §13 defers detailed lifecycle remediation to itself, not this series).
- Close the series: point back to the landing page's boundary-mapping table and to the RFCs for anyone who arrived here first and now wants the reference architecture.
