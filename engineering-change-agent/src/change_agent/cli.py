"""Command-line entry point.

Wires the real Foundry model client, tool registry, policy, and execution
context into the harness, then prints the grounded answer (stdout) and the
content-minimizing evidence trace (stderr).

Prerequisites: sign in with ``az login`` and set the variables from
``.env.example`` (e.g. ``set -a; source .env``). The model client is injectable
so the happy path can be tested without a network.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from change_agent.errors import (
    ConfigurationError,
    HarnessLimitExceeded,
    InvalidModelResponse,
)
from change_agent.harness import Harness
from change_agent.model_client import FoundryChatModel, ModelConfig
from change_agent.models import ExecutionContext
from change_agent.policy import Policy
from change_agent.tool_registry import default_registry


def main(argv: list[str] | None = None, *, model: Any | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="change-agent",
        description="Ask EngBot about a synthetic deployment's change readiness.",
    )
    parser.add_argument("prompt", nargs="+", help="the question to ask EngBot")
    args = parser.parse_args(argv)
    prompt = " ".join(args.prompt)

    try:
        config = ModelConfig.from_env()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    chat_model = model if model is not None else FoundryChatModel(config)
    context = ExecutionContext(
        caller_id=os.environ.get("USER", "cli-user"),
        agent_id="engbot",
        purpose="change-readiness",
    )
    harness = Harness(
        model=chat_model,
        registry=default_registry(),
        policy=Policy(),
        context=context,
        evidence_sink=lambda event: print(json.dumps(event), file=sys.stderr),
    )

    try:
        result = harness.run(prompt)
    except (InvalidModelResponse, HarnessLimitExceeded) as exc:
        print(f"Run stopped: {exc}", file=sys.stderr)
        return 1

    print(result.answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
