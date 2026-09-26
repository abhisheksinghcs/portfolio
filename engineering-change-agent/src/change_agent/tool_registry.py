"""Explicit tool registry: the allowlist of tools the harness may run.

Tools are resolved by name *only* from this registry. The harness never imports
or executes a model-supplied function name, so a hallucinated or malicious tool
name fails closed. The registry is also the single source of the JSON schemas
advertised to the model, derived from each tool's Pydantic argument model so the
advertised shape cannot drift from what is actually validated.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from change_agent.models import ToolResult
from change_agent.tools.deployment_status import (
    DeploymentStatusArguments,
    get_deployment_status,
)


def _strip_metadata(node: Any) -> Any:
    """Remove ``title``/``description`` from a JSON schema tree.

    Pydantic copies class and field docstrings into schema descriptions. Those
    are written for developers and can hint at internal enforcement; we advertise
    structure to the model, not our commentary. The curated, model-facing
    description lives at the function level instead.
    """
    if isinstance(node, dict):
        return {
            key: _strip_metadata(value)
            for key, value in node.items()
            if key not in ("title", "description")
        }
    if isinstance(node, list):
        return [_strip_metadata(item) for item in node]
    return node


@dataclass(frozen=True)
class RegisteredTool:
    """One tool the harness is allowed to run, with its validated argument model
    and handler."""

    name: str
    description: str
    arguments_model: type[BaseModel]
    handler: Callable[[Any], ToolResult]

    def json_schema(self) -> dict[str, Any]:
        """The OpenAI tool schema advertised to the model.

        Parameters are generated from the Pydantic argument model, so what the
        model is told matches what the harness validates. Developer docstrings
        are stripped so only structure and the curated description are sent.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": _strip_metadata(
                    self.arguments_model.model_json_schema()
                ),
            },
        }


class ToolRegistry:
    """An explicit, in-memory allowlist. Registration is deliberate; resolution
    of an unknown name returns ``None`` so the harness can fail closed."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, tool: RegisteredTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def resolve(self, name: str) -> RegisteredTool | None:
        # Unknown names return None. No dynamic import of a model-supplied name.
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.json_schema() for tool in self._tools.values()]

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)


DEPLOYMENT_STATUS_DESCRIPTION = (
    "Return the read-only readiness status of a single deployment. "
    "Supports development, test, and sandbox only; production is not accessible. "
    "Only known applications and deployment records are available."
)


def default_registry() -> ToolRegistry:
    """The Stage 1A registry: the single read-only deployment-status tool."""
    registry = ToolRegistry()
    registry.register(
        RegisteredTool(
            name="get_deployment_status",
            description=DEPLOYMENT_STATUS_DESCRIPTION,
            arguments_model=DeploymentStatusArguments,
            handler=get_deployment_status,
        )
    )
    return registry
