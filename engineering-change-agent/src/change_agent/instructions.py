"""System instructions and initial-context construction.

The system prompt shapes model *behavior*: what the agent is for and how to use
its tool. It is deliberately **not** an authorization control. The model may
ignore these instructions or be manipulated past them; production denial,
argument validation, tool-registry allowlisting, and execution limits are all
enforced in code regardless of what the model does or is told.
"""

from __future__ import annotations

from typing import Any

SYSTEM_INSTRUCTIONS = """You are EngBot, an engineering change-readiness assistant.

Your job is to help an engineer decide whether a deployment is ready for a change
request. When you need a deployment's status, call the get_deployment_status tool
with the application, environment, and deployment_id.

Guidelines:
- Only assess deployments in development, test, or sandbox environments.
- You cannot access production; do not attempt production change assessments.
- Base your readiness assessment only on facts returned by the tool. Never invent
  deployment details.
- If the tool denies a request or cannot find a deployment, say so plainly."""


def build_initial_context(user_prompt: str) -> list[dict[str, Any]]:
    """Construct the opening conversation: system guidance, then the user turn."""
    return [
        {"role": "system", "content": SYSTEM_INSTRUCTIONS},
        {"role": "user", "content": user_prompt},
    ]
