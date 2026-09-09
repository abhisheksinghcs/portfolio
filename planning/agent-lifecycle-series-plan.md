# Planning: The Secure Agent Lifecycle — Articles 2–6

Internal planning document. Not part of the published site: not linked from `index.html`, `llms.txt`, `README.md`, or the series landing page (`content/agent-lifecycle.md`). This repo has no draft/staging mechanism (no static-site-generator config, no `_drafts` folder — content is hand-authored `.md`/`.html` pairs indexed manually via `llms.txt`), so future-article outlines live here instead of as published placeholder pages.

Series landing page: `content/agent-lifecycle.md`. Article 1 (Define) is fully drafted at `content/agent-lifecycle-01-define.md` / `.html`.

When drafting an article below: create `content/agent-lifecycle-0N-<slug>.md` + `.html` (same zero-md wrapper template as the existing articles), fully write it, then add it to `content/agent-lifecycle.md`'s "Available now" list, `llms.txt`'s Core Work or a new lifecycle section, and remove its outline from this file (or mark it drafted).

**Structural convention (established in Article 1):** each concept-bearing section should have a `### The concept` subsection (the general principle, no EngBot specifics) followed by a `### Applied to EngBot` subsection (naming the specific Azure service, identity, or policy this stage adds). Don't blend the two into one paragraph.

---

## Article 2 — Identify: The Agent Identity Model — **drafted**, see `content/agent-lifecycle-02-identify.md`.

## Article 3 — Build: Choosing and Building the Harness — **drafted**, see `content/agent-lifecycle-03-build.md`.

## Article 4 — Connect: Retrieval and Read-Only Tools — **drafted**, see `content/agent-lifecycle-04-connect.md`.

## Article 5 — Authorize: Proposing and Approving Changes — **drafted**, see `content/agent-lifecycle-05-authorize.md`.

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
