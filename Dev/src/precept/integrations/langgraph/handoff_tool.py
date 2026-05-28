# SPDX-License-Identifier: Apache-2.0
"""LangGraph handoff-tool wrapper (PRC-014).

``create_precept_handoff_tool`` is the *convenience* surface: a drop-in
replacement for a manual ``create_handoff_tool`` that runs a Precept
contract check before the handoff. It is built on top of the durable
:func:`precept.integrations.langgraph.eval_hook.evaluate_handoff`; if
LangGraph's tool API churns (DEPENDENCIES.md section 4.1 -- ``langgraph``
is a HIGH-instability dependency), only this module needs updating, never
the pure hook.

**This module requires ``langgraph`` to be installed.** It is a hard
runtime dependency of Precept (``pyproject.toml`` ->
``langgraph>=0.5,<0.7``, ``langchain-core>=0.3,<1``), so a normal
``pip install precept`` already satisfies it. The package ``__init__``
exposes this symbol lazily (PEP 562) so importing the pure hook never
imports ``langgraph``.

Handoff-tool shape: this uses the manual ``InjectedState`` +
``InjectedToolCallId`` + ``Command(goto=..., graph=Command.PARENT)``
pattern, i.e. the documented workaround for
``langchain-ai/langgraph-supervisor-py#205`` (where the
``langgraph_supervisor`` helper did not pass supervisor state cleanly to
sub-agent handoffs). We do not depend on ``langgraph_supervisor`` at
runtime -- it is a test-only dependency exercised by the integration
suite -- per DEPENDENCIES.md section 3.1, which lists only ``langgraph``
and ``langchain-core`` as runtime deps and section 4.1, which steers
toward manual tool patterns over the partially-deprecated helper.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, cast

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from precept.integrations.langgraph.eval_hook import evaluate_handoff

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from precept.contract.registry import ContractRegistry
    from precept.evaluator.engine import Evaluator

__all__ = ["create_precept_handoff_tool"]


def create_precept_handoff_tool(
    agent_name: str,
    contract_name: str,
    *,
    registry: ContractRegistry | None = None,
    evaluator: Evaluator | None = None,
    name: str | None = None,
    description: str | None = None,
) -> BaseTool:
    """Create a handoff tool that contract-checks before transferring.

    The returned tool, when called by a supervisor LLM, evaluates
    ``contract_name`` against the routed state and then transfers control
    to ``agent_name`` via ``Command(goto=..., graph=Command.PARENT)``.

    Signature mirrors a manual ``create_handoff_tool`` where overlapping
    (``agent_name``, ``name``, ``description``) and extends it with
    ``contract_name`` (required) plus ``registry`` / ``evaluator`` for the
    same wiring the pure hook accepts. Migration from an uncontracted
    supervisor is: change the import and add ``contract_name``.

    Contract-failure behaviour is inherited verbatim from
    :func:`evaluate_handoff`:

    * **block** mode + failing contract -> ``HandoffBlockedError`` is
      raised from inside the tool. LangGraph's ``ToolNode`` converts a
      raised exception into an error ``ToolMessage`` routed back to the
      supervisor LLM, which can retry or route elsewhere (AC).
    * **warn** mode, passing, or a missing contract (fail-open) -> the
      handoff proceeds normally.
    """

    tool_name = name if name is not None else f"transfer_to_{agent_name}"
    tool_description = (
        description if description is not None else f"Transfer control to {agent_name}."
    )

    # @tool resolves to Any (langgraph/langchain surface is intentionally
    # untyped -- see pyproject mypy overrides; DEPENDENCIES.md 4.1), so
    # strict mode flags the decorator as untyped. Expected and uniform
    # across environments because follow_imports=skip makes the treatment
    # install-independent.
    @tool(tool_name, description=tool_description)  # type: ignore[untyped-decorator]
    def _precept_handoff_tool(
        state: Annotated[dict[str, Any], InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        # Evaluate the contract on the state the supervisor is about to
        # forward, BEFORE the transfer. In the tool-routing pattern the
        # supervisor forwards the shared state unchanged -- there is no
        # separately-transformed target payload at this boundary in v0 --
        # so source and target are the same state object; the contract
        # still checks required-field presence, entity preservation, and
        # forbidden drops on what is being handed across. A block-mode
        # failure raises HandoffBlockedError here; ToolNode surfaces it
        # as an error ToolMessage to the supervisor.
        evaluate_handoff(
            source=state,
            target=state,
            contract_name=contract_name,
            registry=registry,
            evaluator=evaluator,
        )
        tool_message = ToolMessage(
            content=f"Successfully transferred to {agent_name}",
            name=tool_name,
            tool_call_id=tool_call_id,
        )
        return Command(
            goto=agent_name,
            update={"messages": [tool_message]},
            graph=Command.PARENT,
        )

    # langchain-core's @tool returns a StructuredTool (a BaseTool); the
    # cast pins the public return type across the type-ignored langgraph
    # boundary (see pyproject mypy overrides; DEPENDENCIES.md 4.1).
    return cast("BaseTool", _precept_handoff_tool)
