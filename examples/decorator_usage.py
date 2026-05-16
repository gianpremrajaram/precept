# SPDX-License-Identifier: MIT
"""Decorator frontend usage (PRC-008).

Run directly::

    python examples/decorator_usage.py

This example is intentionally self-contained: it does not import or
require ``langgraph``. At v0 the decorator is a pure metadata-attachment
mechanism (PRC-008); the LangGraph integration (PRC-014) is what reads the
attached ``__precept_contract__`` to evaluate a handoff. The function below
plays the role a LangGraph handoff node would: it builds the next agent's
payload and (once PRC-014 lands) the integration layer evaluates the
contract attached here before the handoff proceeds.
"""

from __future__ import annotations

from precept.contract.decorator import handoff_contract


@handoff_contract(
    name="researcher_to_summariser",
    required=["hypothesis", "citations"],
    preserved_entities=["primary_source"],
    min_fidelity=0.75,
    forbidden_drops=["uncertainty_bounds"],
    mode="block",
)
def handoff_to_summariser(state: dict[str, object]) -> dict[str, object]:
    """A stand-in for a LangGraph handoff node.

    Returns the payload the summariser agent would receive. The contract
    declared above rides along on this function as ``__precept_contract__``.
    """

    return {
        "hypothesis": state["hypothesis"],
        "citations": state["citations"],
        "primary_source": state["primary_source"],
        "uncertainty_bounds": state["uncertainty_bounds"],
    }


def main() -> None:
    contract = handoff_to_summariser.__precept_contract__

    print(f"Attached contract : {contract.name} (mode={contract.mode})")
    print(f"  required_fields   : {contract.fields.required_fields}")
    print(f"  preserved_entities: {contract.fields.preserved_entities}")
    print(f"  min_fidelity      : {contract.fields.min_fidelity}")
    print(f"  forbidden_drops   : {contract.fields.forbidden_drops}")

    # The decorated function is unchanged at call time (v0: no evaluation).
    payload = handoff_to_summariser(
        {
            "hypothesis": "Renewable adoption accelerates as storage cost falls.",
            "citations": ["IEA 2025", "IRENA 2024"],
            "primary_source": "IEA World Energy Outlook 2025",
            "uncertainty_bounds": "+/- 8% on 2030 projections",
        }
    )
    print(f"Handoff payload   : {sorted(payload)}")


if __name__ == "__main__":
    main()
