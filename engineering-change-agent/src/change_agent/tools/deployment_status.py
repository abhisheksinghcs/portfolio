"""The ``get_deployment_status`` tool: a read-only lookup over synthetic
deployment records.

This tool is the innermost trust boundary in the harness. It is invoked only
after the harness has validated argument *shape* and application policy has
*authorized* the call — but it does not rely on either. It re-checks its own
contract so that a mistake in an outer layer cannot cause it to return
production data or leak information about unknown records.

Contract (Stage 1A):
    * Read-only. No writes, ever.
    * Serves development, test, and sandbox only. Production is denied.
    * Serves known applications and known deployment records only.
    * Backed exclusively by bundled synthetic data.
    * Accepts exactly three named arguments; anything else is rejected upstream
      by the argument schema.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from change_agent.errors import ReasonCode
from change_agent.models import DeploymentStatus, Environment, ToolResult

# synthetic-data/ is a sibling of src/ at the project root.
_SYNTHETIC_DATA = (
    Path(__file__).resolve().parents[3] / "synthetic-data" / "deployments.json"
)


class DeploymentStatusArguments(BaseModel):
    """Structural schema for the model-generated tool arguments.

    ``extra="forbid"`` is the mechanism that refuses arbitrary URLs, resource
    IDs, connection strings, or any other field the model might invent: only
    these three named fields are accepted. This establishes *shape*, not
    permission.
    """

    model_config = ConfigDict(extra="forbid")

    application: str = Field(min_length=1)
    environment: Environment
    deployment_id: str = Field(min_length=1)


@lru_cache(maxsize=1)
def _load_deployments() -> tuple[dict[str, Any], ...]:
    """Load the bundled synthetic records once. Immutable to callers."""
    with _SYNTHETIC_DATA.open(encoding="utf-8") as handle:
        records = json.load(handle)
    return tuple(records)


def get_deployment_status(
    arguments: DeploymentStatusArguments,
    *,
    deployments: tuple[dict[str, Any], ...] | None = None,
) -> ToolResult:
    """Return the readiness status for a single synthetic deployment.

    Returns a normalized :class:`ToolResult`. The tool never raises for expected
    conditions (production, unknown application, unknown deployment); it returns
    a denial or not-found result with a stable reason code and no target data.
    """
    records = deployments if deployments is not None else _load_deployments()

    # Second line of defense: the tool denies production even if an outer layer
    # somehow authorized it. Structural validation accepted "production" as a
    # real environment name; authorization to read it is refused here.
    if arguments.environment is Environment.PRODUCTION:
        return ToolResult.denied(ReasonCode.PRODUCTION_ENVIRONMENT_PROHIBITED)

    known_applications = {record["application"] for record in records}
    if arguments.application not in known_applications:
        return ToolResult.denied(ReasonCode.UNKNOWN_APPLICATION)

    for record in records:
        if (
            record["deployment_id"] == arguments.deployment_id
            and record["application"] == arguments.application
            and record["environment"] == arguments.environment.value
        ):
            status = DeploymentStatus.model_validate(record)
            return ToolResult.success(status.model_dump(mode="json"))

    # Known application, no matching record: report not-found without echoing
    # any record contents, so the caller learns nothing about other records.
    return ToolResult.not_found(ReasonCode.UNKNOWN_DEPLOYMENT)
