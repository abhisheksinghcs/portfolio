# Engineering Change Readiness Agent — Stage 1A

Companion implementation for the **"Inside the Agentic Harness"** article series on
[abhisingh.org](https://abhisingh.org). Stage 1A builds an agentic harness loop
**explicitly** — model invocation, tool proposals, validation, authorization,
bounded execution, and content-minimizing evidence — before Stage 1B maps the
same behavioral and security contract onto Microsoft Agent Framework.

> The harness coordinates the model and tool loop; deterministic application
> logic retains authorization. The model proposes; code validates and authorizes.

This is a teaching reference with synthetic data only. It is **not**
production-ready.

## What it does

EngBot answers whether a synthetic deployment is ready for a change request. The
model may propose one read-only tool, `get_deployment_status`; the harness
validates the proposal's shape, authorizes it, runs it against bundled synthetic
data within a timeout, and returns a grounded answer — emitting evidence at each
decision point.

## Layout

| Path | Responsibility |
|---|---|
| `src/change_agent/models.py` | Domain data shapes (`Environment`, `DeploymentStatus`, `ToolResult`, `Decision`, `ExecutionContext`) |
| `src/change_agent/errors.py` | Stable reason codes and harness exceptions |
| `src/change_agent/tools/deployment_status.py` | The read-only tool + its Pydantic argument schema |
| `src/change_agent/tool_registry.py` | Explicit tool allowlist + advertised JSON schemas |
| `src/change_agent/policy.py` | Deterministic authorization (independent production denial) |
| `src/change_agent/evidence.py` | Content-minimizing evidence emitter |
| `src/change_agent/model_client.py` | Foundry v1 (OpenAI-compatible) client, Entra auth |
| `src/change_agent/instructions.py` | System prompt (behavioral, not authorization) |
| `src/change_agent/harness.py` | The bounded model/tool loop |
| `src/change_agent/cli.py` | Command-line entry point |
| `synthetic-data/deployments.json` | Bundled synthetic records |
| `docs/` | Article evidence, code walkthrough, Python concept notes |

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run the tests (no network needed)

```bash
pytest -q
```

## Run against a live model

Authentication uses Microsoft Entra (no API key). Your identity needs the
`Cognitive Services OpenAI User` role on the resource.

```bash
az login
cp .env.example .env        # then edit values
set -a; source .env; set +a
change-agent "Check deployment DEP-1003 for payments-api in test. Ready for a change request?"
```

The grounded answer prints to stdout; the evidence trace prints to stderr.
