# Enterprise GenAI Security & Control-Plane Portfolio

> Personal technical knowledge base and architecture portfolio for **Abhi Singh**, specializing in enterprise Generative AI security, control-plane defense, and autonomous agentic governance.

## Architecture Modules

* **[Microsoft-Native Control-Plane Enforcement](./content/control-plane.md)** — Boundaries 1-3 of the control-plane pattern on Microsoft-native services: Entra ID and API Management for admission, Azure AI Search for retrieval, Azure OpenAI with managed identity for model invocation.
* **[Agent Runtime, Agentic Harness, and Application Enforcement](./content/agent-runtime-and-enforcement.md)** — Standalone explainer: where the AI gateway, agent runtime, agentic harness, and application enforcement tier each run, and how the identity model works.
* **[Microsoft-Native Enforcement for Agent Tool Use and Side Effects](./content/agent-security.md)** — Boundaries 4-6 of the control-plane pattern: per-agent tool access grants, resource-side RBAC, human-approved side effects, and pre-deployment red teaming.
* **[GenAI Observability Model](./content/observability.md)** — Telemetry pipelines, token tracking, and behavioral threat detection integrated with SIEM.
* **[The Secure Agent Lifecycle: From Prototype to Production](./content/agent-lifecycle.md)** — Practical, build-order companion series to the RFCs above: define, identify, build, connect, authorize, observe and operate an agent. Part 1 published; parts 2-6 outlined.
* **[Publications & Thought Leadership](./content/publications.md)** — Whitepapers on securing generative AI, threat vectors, and defense strategies.
* **[Customer Impact Stories](./content/impact-stories.md)** — Enterprise case studies across financial services, telco, and regulated public sector accounts ($50M+ pipeline scope).

## AI Agent Ingestion (`llms.txt`)
This repository is structured for automated AI consumption. An `llms.txt` file is included at the root directory to provide structured context to LLM crawlers and automated recruiting agents.

## License
Published under the MIT License. Feel free to review the architecture patterns and documentation.