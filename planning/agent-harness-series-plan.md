# Planning: Inside the Agentic Harness

Internal planning and implementation-evidence document. This file is not part of the published site and must not be linked from `index.html`, `llms.txt`, `README.md`, or the lifecycle-series landing page until the implementation and supporting tests are ready.

Primary lifecycle connection: `content/agent-lifecycle-03-build.md`.

Related architecture references:

- `content/control-plane-pattern.md`
- `content/control-plane.md`
- `content/agent-security.md`
- `content/observability.md`

## Purpose

Build a working, tested, and reproducible implementation that demonstrates the agentic-harness responsibilities introduced in Article 3 of the Secure Agent Lifecycle series.

The project has three equally important outcomes:

1. **Learning:** understand and explain the model/tool loop, message protocol, trust boundaries, policy enforcement, failure behavior, and evidence.
2. **Reference implementation:** provide working code based on Microsoft-native model and identity services.
3. **Public narrative:** publish a design-oriented article on `abhisingh.org`, supported by focused excerpts from the real implementation and linked to a complete companion repository.

> The harness coordinates the model and tool loop; deterministic application logic retains authorization.

> First build the loop explicitly. Then map the same responsibilities to Microsoft Agent Framework.



Engineering Change Readiness Agent — Stage 1 Harness Design
Approach: Bare-metal orchestration first, Microsoft Agent Framework mapping second

Portfolio objective
Demonstrate genuine understanding of an agentic harness using Microsoft-native services. Build the project incrementally with GitHub Copilot, publish the learning journey on abhisingh.org, and provide well-commented, tested, reproducible code that readers can follow.

The harness coordinates the model and tool loop; deterministic application logic retains authorization.

First build the loop explicitly. Then map the same responsibilities to Microsoft Agent Framework.

1. Design decision
Stage 1 is divided into two parts.

Stage 1A — Explicit harness
Build a custom orchestration loop so that the important harness responsibilities remain visible:

Model-request construction
Conversation state
Model invocation
Response parsing
Tool-proposal detection
Tool registry and dispatch
Schema validation
Authorization
Execution limits and timeout
Exception handling
Tool-result correlation
Result insertion into model context
Loop continuation and termination
Security-evidence generation
Stage 1B — Microsoft Agent Framework mapping
Reimplement the same behavioral and security contract with Microsoft Agent Framework. Document which orchestration mechanics the framework handles and which security responsibilities still belong to application code.

“Bare-metal” does not mean abandoning Microsoft-native services or unnecessarily implementing raw HTTP and OAuth. It means that our code owns and exposes the orchestration loop.

API-surface decision
Stage 1A intentionally uses the Microsoft Foundry OpenAI-compatible Chat Completions API because its explicit message history makes orchestration and tool-result correlation easy to inspect and teach. Stage 1B maps the same behavioral contract to Microsoft Agent Framework, using its recommended Responses client where appropriate.

This is a pedagogical choice. It is not a claim that Chat Completions is preferred for new, full-featured agents.

2. Stage 1A architecture
Final answer

Tool proposal

Unknown tool

Known tool

Invalid

Valid

Denied

Allowed

Success

Timeout or failure

User or test client

Custom harness

Build context and conversation state

Microsoft Foundry model endpoint

Response type

Return grounded answer

Resolve registered tool

Emit minimized denial evidence

Pydantic schema validation

Deterministic authorization policy

Bounded tool execution

Emit minimized decision and outcome evidence

Create correlated tool-result message

Conceptually:

User prompt
    → construct model context
    → invoke Foundry model
    → parse response
    → return final answer
         or
      process tool proposal
        → resolve approved tool
        → validate argument shape
        → evaluate authorization policy
        → execute within limits
        → normalize result or failure
        → emit minimized evidence
        → append correlated tool result
        → continue the loop
3. Responsibility layers
Orchestration
Construct model context.
Maintain conversation messages.
Invoke the model.
Parse responses.
Detect final answers and tool proposals.
Correlate proposals with tool results.
Append results to conversation state.
Continue or terminate the loop.
Enforcement
Permit only registered tools.
Validate argument structure.
Evaluate caller, agent, purpose, and environment policy when available.
Apply step, tool-call, and time budgets.
Explicitly deny production.
Fail closed on unknown tools and malformed proposals.
Execution
Invoke the selected handler.
Apply a timeout.
Catch and classify exceptions.
Normalize successful and failed results.
Ensure the tool independently enforces its contract.
Evidence
Record the proposal metadata.
Record the policy decision and reason.
Record the target, outcome, latency, and policy version.
Exclude unnecessary content and credentials.
4. Responsibility split
Component	Stage 1 responsibility	Later responsibility
Microsoft Foundry	Provide and process requests through the model endpoint	Hosted Agent endpoint, sessions, scaling, agent identity, lifecycle, and platform observability
Azure Identity	Acquire supported credentials for model access	Authenticate hosted workloads and supporting Azure components
Custom harness	Own the loop, conversation state, response parsing, tool registry, correlation, budgets, and termination	Continue to own custom orchestration when hosted unless deliberately replaced by framework/runtime features
Pydantic	Validate structural shape and types	Remains structural validation; never becomes authorization
Application policy	Decide whether a valid proposal is permitted	Expand to user, agent, tenant, purpose, approval, and resource context
Target tool	Independently enforce its contract and production denial	Later become a protected Azure API with its own authentication and authorization
Microsoft Agent Framework	Not used to drive the Stage 1A loop	In Stage 1B, replace selected orchestration mechanics while application policy remains explicit
A framework can automate orchestration. It does not remove application responsibility for authorization, validation, execution limits, target-side controls, or evidence.

5. Demonstration scenario
User request
Check deployment DEP-1003 for payments-api in test. Is it ready for a change request?

Synthetic deployment record
{
  "deployment_id": "DEP-1003",
  "application": "payments-api",
  "environment": "test",
  "status": "validation_complete",
  "tests_passed": true,
  "open_blockers": 0,
  "change_window_available": true
}
Tool contract
get_deployment_status(
    application: str,
    environment: str,
    deployment_id: str,
) -> DeploymentStatus
The tool must be:

Read-only.
Limited to development, test, and sandbox.
Explicitly denied for production.
Limited to known applications and deployment records.
Strict about missing and unexpected arguments.
Backed only by bundled synthetic data during Stage 1.
It must never accept:

Arbitrary URLs.
Azure subscription or resource identifiers.
Database queries.
Connector names.
Access tokens.
Credentials or connection strings.
6. Harness-loop pseudocode
messages = build_initial_context(user_prompt)

for step in range(MAX_STEPS):
    response = model.invoke(
        messages=messages,
        tools=tool_registry.schemas(),
    )

    if response.is_final_answer:
        evidence.emit_final_response_metadata(
            step=step,
            outcome="success",
        )
        return response.text

    if not response.tool_calls:
        raise InvalidModelResponse("No final answer or tool proposal")

    for proposal in response.tool_calls:
        tool = tool_registry.resolve(proposal.name)

        if tool is None:
            decision = Decision.deny("unknown_tool")
            result = ToolResult.denied("unknown_tool")

        else:
            try:
                # Structural validation only.
                arguments = tool.schema.model_validate(proposal.arguments)

                # Authorization remains a separate deterministic decision.
                decision = policy.authorize(
                    tool=tool,
                    arguments=arguments,
                    context=execution_context,
                )

                if not decision.allowed:
                    result = ToolResult.denied(decision.reason)
                else:
                    result = execute_with_timeout(
                        handler=tool.handler,
                        arguments=arguments,
                        timeout=TOOL_TIMEOUT,
                    )

            except ValidationError:
                decision = Decision.deny("invalid_arguments")
                result = ToolResult.denied("invalid_arguments")

            except ToolTimeout:
                decision = Decision.fail("tool_timeout")
                result = ToolResult.failed("tool_timeout")

            except Exception:
                decision = Decision.fail("tool_execution_failed")
                result = ToolResult.failed("tool_execution_failed")

        evidence.emit_minimized(
            proposal=proposal,
            decision=decision,
            result=result,
        )

        messages.append(
            create_tool_result_message(
                proposal_id=proposal.id,
                result=result,
            )
        )

raise HarnessLimitExceeded("maximum agent steps reached")
Validation is not authorization
arguments = ToolArguments.model_validate(raw_arguments)

decision = policy.authorize(
    tool=tool,
    arguments=arguments,
    context=execution_context,
)
Pydantic can establish that:

environment is a string.
Required fields are present.
Unknown fields are rejected.
Values match an expected enum or format.
Pydantic cannot establish that:

The caller is authorized.
This agent may invoke the tool.
Production is permitted.
The requested deployment belongs to the caller.
7. Conversation and tool-message protocol
Stage 1A keeps conversation state explicit so the relationship between the assistant’s tool proposal and the tool’s result is visible.

For a tool-using turn, messages are stored in this order:

The existing conversation and current user message.
The complete assistant message containing tool_calls.
One correlated tool message for the permitted proposal.
The subsequent assistant response.
# Preserve the complete assistant response, including its tool_calls.
messages.append(response_message)

for proposal in response_message.tool_calls or []:
    result = process_tool_proposal(proposal)

    messages.append({
        "role": "tool",
        "tool_call_id": proposal.id,
        "name": proposal.function.name,
        "content": json.dumps(result.to_dict()),
    })
Correlation rules
Every tool proposal receives exactly one result.
A tool-result message must use the original proposal’s tool_call_id.
The identifier must belong to the current pending assistant turn.
Missing, duplicate, reused, invented, or orphaned identifiers fail closed.
A protocol-correlation failure prevents tool execution.
Mixed text and tool proposals
An assistant response can contain explanatory text and one or more tool proposals in the same turn. Stage 1A preserves the entire assistant message but treats accompanying text as provisional commentary rather than a final answer.

Tool proposals take precedence. A turn is final only when no tool calls are pending and the response contains final text.

assistant_message = response.choices[0].message
messages.append(assistant_message)

tool_calls = assistant_message.tool_calls or []

if tool_calls:
    process_tool_calls(tool_calls)
    continue

if assistant_message.content:
    return assistant_message.content

raise InvalidModelResponse(
    "Assistant returned neither final content nor tool calls"
)
Sequential execution constraint
Stage 1A sets:

parallel_tool_calls = False
It permits at most one tool proposal per assistant turn. If multiple proposals are returned despite that setting, the harness fails closed, emits unexpected_multiple_tool_calls, and executes none of them.

if len(tool_calls) > 1:
    evidence.emit_denial(
        reason="unexpected_multiple_tool_calls",
        proposed_count=len(tool_calls),
    )
    raise InvalidModelResponse(
        "Stage 1A permits one tool call per assistant turn"
    )
Parallel execution, result ordering, partial failure, cancellation, and concurrency-safe evidence are deferred to a later stage.

8. Security invariants
Instructions are not authorization. Instructions influence model behavior, while code enforces policy.
Tool calls are proposals. A model-generated call has no authority until deterministic validation and authorization succeed.
Unknown tools fail closed. The harness never dynamically imports or executes a model-supplied function name.
Validation and authorization are separate. Correctly shaped input may still be prohibited.
Tool output is untrusted data. Returned text cannot override instructions or policy.
Production is denied twice. Application policy and tool implementation both reject production.
Targets are constrained. The client and model cannot supply arbitrary endpoints, subscriptions, queries, connectors, or credentials.
Execution is bounded. The harness enforces maximum steps, a tool-call budget, and execution timeout.
Failures are normalized. Exceptions do not leak credentials, stack traces, or sensitive details into model context.
Evidence minimizes content. Raw prompts, completions, tokens, credentials, and full tool results are excluded by default.
Tool-message correlation is mandatory. Missing, duplicate, reused, invented, or orphaned tool_call_id values fail closed.
Tool proposals take precedence over provisional text. Mixed assistant content is not treated as final while a tool call remains pending.
Stage 1A is sequential. Unexpected multiple tool proposals cause a denial and none are executed.
Example event:

{
  "run_id": "run-example",
  "stage": "tool_authorization",
  "tool": "get_deployment_status",
  "decision": "denied",
  "reason": "production_environment_prohibited",
  "target_environment": "production",
  "outcome": "not_executed",
  "policy_version": "stage1-v1"
}
9. Acceptance tests
Successful behavior
Test	Expected result
Known application and deployment in test	Structured status returned
Known deployment in sandbox	Structured status returned
Valid tool result	Model answer reflects returned facts
Successful execution	Evidence records allow and success
Denial and failure behavior
Test	Expected enforcement point	Expected result
production environment	Application policy and tool	Denied; tool does not return production data
Unknown application	Policy/tool contract	Denied
Unknown deployment	Tool contract	Not-found result without data leakage
Missing field	Pydantic schema	Denied as invalid arguments
Unexpected field	Pydantic schema	Denied as invalid arguments
Arbitrary URL supplied	Schema/policy	Denied
Nonexistent tool	Tool registry	Denied as unknown tool
Prompt says to ignore restrictions	Policy/tool	Denied if prohibited action is proposed
Tool timeout	Execution boundary	Normalized timeout result and evidence
Tool exception	Execution boundary	Normalized failure without sensitive details
Maximum steps exceeded	Harness	Run terminated with limit evidence
Assistant returns text and a tool proposal	Response parser	Text preserved as provisional; tool proposal processed first
Missing or orphaned tool_call_id	Conversation protocol	Fail closed; no tool execution
Duplicate or reused tool_call_id	Conversation protocol	Fail closed; no tool execution
Multiple tool calls in one turn	Sequential constraint	Denied as unexpected_multiple_tool_calls; none executed
For every denial, verify:

The expected enforcement point made the decision.
The prohibited tool execution did not occur.
The decision and reason were recorded.
Evidence remained content-minimizing.
10. Two-stage learning plan
Stage 1A — Explicit harness
Implement:

Foundry model client
Manual orchestration loop
Conversation-state representation
Tool registry
Pydantic schemas
Application-policy module
Bounded execution
Evidence emitter
Allowed and denied tests
The goal is to make every transition visible and explainable.

Stage 1B — Microsoft Agent Framework mapping
Implement the same logical contract through Microsoft Agent Framework.

Preserve where practical:

Tool contract
Policy module
Synthetic data
Security invariants
Evidence shape
Acceptance tests
Compare the implementations:

Responsibility	Stage 1A: explicit harness	Stage 1B: Agent Framework	Remains application-owned?
Model invocation	Explicit client call	Framework model client	Configuration and approved target remain owned
Conversation state	Explicit message list	Framework abstractions	Data-minimization decisions remain owned
Tool registry	Custom registry	Framework tool registration	Approved tool inventory remains owned
Loop	Manual bounded loop	Framework-managed or assisted	Limits and expected behavior must still be verified
Schema validation	Explicit Pydantic validation	Framework parsing plus explicit validation	Yes
Authorization	Explicit policy call	Policy hook/middleware/tool wrapper	Yes
Timeouts and budgets	Explicit	Framework configuration and custom controls	Yes
Tool execution	Explicit handler dispatch	Framework dispatch	Tool-side authorization remains owned
Evidence	Explicit emitter	Middleware/callback plus explicit events	Yes
Target authorization	Tool code	Tool code or protected API	Yes
11. Proposed repository structure
engineering-change-agent/
├── README.md
├── pyproject.toml
├── .env.example
├── src/
│   └── change_agent/
│       ├── __init__.py
│       ├── cli.py
│       ├── harness.py
│       ├── model_client.py
│       ├── instructions.py
│       ├── tool_registry.py
│       ├── policy.py
│       ├── evidence.py
│       ├── models.py
│       ├── errors.py
│       └── tools/
│           ├── __init__.py
│           └── deployment_status.py
├── synthetic-data/
│   └── deployments.json
├── tests/
│   ├── test_tool_contract.py
│   ├── test_policy.py
│   ├── test_harness_read_flow.py
│   └── test_limits.py
└── docs/
    ├── architecture.md
    ├── stage-1-request-flow.md
    └── framework-mapping.md
Stage 1B can later add:

src/change_agent/framework_adapter/
Keep these responsibilities separate:

Model communication
Harness orchestration
Tool registration
Structural validation
Authorization policy
Tool implementation
Evidence generation
Framework integration
12. Deliberately deferred
Stage 1 excludes:

Foundry Hosted Agent deployment.
Microsoft Entra Agent ID authorization.
Protected Azure Function or App Service tools.
Azure API Management AI gateway.
Azure AI Search.
Write tools.
Human approval.
Copilot Studio.
Microsoft Sentinel.
Model Context Protocol servers.
Multi-agent orchestration.
These should be introduced later, one responsibility at a time, after the explicit loop and its security properties are understood and tested.

13. Definition of done
Stage 1 is complete when I can:

Demonstrate a successful read-only path.
Demonstrate the production-denial path.
Trace a complete loop through the code.
Explain every trust boundary.
Distinguish structural validation from authorization.
Explain what happens when the model is wrong.
Explain timeout, exception, and maximum-step behavior.
Show minimized evidence for allowed and denied operations.
Explain what Foundry manages and what the custom harness manages.
Compare the explicit harness with Agent Framework abstractions.
Identify which security duties remain application-owned after adopting the framework.
Explain and demonstrate conversation-protocol correctness: assistant tool-proposal storage, tool_call_id correlation, mixed-content handling, and sequential execution.
Base the public article on actual code and test evidence rather than unsupported claims.
14. Article evidence to preserve
Capture during implementation:

Architecture diagram.
Annotated successful request trace.
Annotated denied request trace.
Example model tool proposal.
Pydantic validation outcome.
Authorization decision and reason.
Successful tool result.
Timeout or failure result.
Maximum-step termination.
Content-minimizing evidence event.
Test output for allowed and denied cases.
Stage 1A versus Stage 1B framework-mapping table.
Do not claim that a behavior was tested unless the corresponding test or captured evidence exists in the repository.

15. Public article and code principle
Develop the article and implementation together:

Explain the responsibility
    → implement the smallest explicit mechanism
    → test allowed and denied behavior
    → capture evidence
    → map the mechanism to Agent Framework
    → document what changed and what did not
    → publish reproducible, commented code
The public narrative should demonstrate both first-principles understanding and practical use of Microsoft-native services.

---

## Companion implementation track — Inside the Agentic Harness

The lifecycle articles describe how EngBot evolves from a defined use case into an identified, connected, authorized, observable, and eventually retired agent. They intentionally explain the architectural responsibilities without turning the series into a file-by-file implementation tutorial.

A separate companion track will build and document the agentic harness behind the example:

- Planning document: `planning/agent-harness-series-plan.md`
- Working title: **Inside the Agentic Harness: From Model Proposal to Governed Execution**
- Primary lifecycle connection: Article 3, `content/agent-lifecycle-03-build.md`
- Supporting connections:
  - Article 2 for user, agent, and workload identity
  - Article 4 for retrieval and read-only tools
  - Article 5 for authorization, approval, and side effects
  - Article 6 for evidence, operations, and retirement

The companion track has three related goals:

1. Build a tested, reproducible harness using Microsoft-native model and identity services.
2. Demonstrate the harness responsibilities explicitly before mapping them to Microsoft Agent Framework.
3. Publish a narrative technical article whose code blocks are evidence for the design patterns being explained.

The implementation will use the same EngBot scenario as the lifecycle series. The first vertical slice is deliberately small:

```text
User asks about a synthetic test deployment
    → model proposes get_deployment_status
    → harness validates the proposal
    → deterministic policy authorizes or denies it
    → read-only tool returns structured synthetic data
    → model produces a grounded readiness assessment
    → harness emits content-minimizing evidence

All six lifecycle articles are now drafted. This planning document has no remaining lifecycle-article outlines. Keep it as the historical record of the lifecycle-series drafting decisions and as the pointer to the active companion implementation track in `planning/agent-harness-series-plan.md`.