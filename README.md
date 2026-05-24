# Information Contracts for Multi-Agent Reasoning Systems

[![CI](https://github.com/gianpremrajaram/precept/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/gianpremrajaram/precept/actions/workflows/ci.yml)
[![Pages](https://github.com/gianpremrajaram/precept/actions/workflows/pages.yml/badge.svg?branch=main)](https://gianpremrajaram.github.io/precept/)

An open-source framework for measuring, enforcing, and studying information integrity at the boundaries between reasoning components in multi-agent AI systems.

**Live observatory:** [gianpremrajaram.github.io/precept](https://gianpremrajaram.github.io/precept/) renders the committed demo trace; drop your own `*.json` trace into the page to inspect a handoff locally (no upload, all rendering is client-side).

## The Problem

Multi-agent AI systems degrade information at every handoff. When context passes from one agent to another, it is compressed, distorted, or silently dropped. Empirical measurements show information fidelity collapsing from 0.91 to below 0.20 across extended reasoning chains.

```
Orchestrator          Agent A             Agent B             Agent C
[full context] ──→ [~70% fidelity] ──→ [~40% fidelity] ──→ [~20% fidelity]
                        ↓                    ↓                    ↓
                   context compressed   details silently     output appears
                   at handoff           dropped              coherent but is
                                                             built on eroded
                                                             evidence
```

Every existing tool operates **downstream** of this problem:

| Layer | Examples | What it does | Position |
|-------|----------|-------------|----------|
| Observability | LangSmith, Langfuse, Arize, Datadog | Traces what agents *did* after execution | Downstream |
| Guardrails | CrewAI task guardrails, OpenAI SDK | Validates what agents *produce* | Postcondition |
| Orchestration | LangGraph conditional edges, AutoGen | Routes control flow between agents | Structural |
| **Information Contracts** | **This framework** | **Validates what agents *receive*** | **Upstream (precondition)** |

The upstream boundary is the only position where information loss can be **prevented**, not merely diagnosed.

## Architecture

Four independent, composable modules:

```
                    ┌──────────────────────────────────────────────┐
                    │         Information Contract Layer           │
                    │  Declare → Intercept → Score → Enforce       │
                    └──────────┬───────────────────┬───────────────┘
                               │                   │
                    ┌──────────▼──────────┐  ┌─────▼──────────────┐
                    │    Coordination     │  │   Experimental     │
                    │  Pattern Observatory │  │     Testbed        │
                    │  MI + Transfer      │  │  5 information     │
                    │  Entropy monitoring │  │  conditions, MARL  │
                    └──────────┬──────────┘  └─────┬──────────────┘
                               │                   │
                    ┌──────────▼───────────────────▼───────────────┐
                    │       Collective Decision Interface          │
                    │  Policy sim · Science orchestration · Gov    │
                    └─────────────────────────────────────────────┘
```

Architectural decisions are recorded under [`docs/adr/`](docs/adr/); see [ADR 0001 — Contract Intermediate Representation](docs/adr/0001-contract-ir.md) for how the YAML and decorator frontends converge on a single Pydantic IR consumed by the evaluator.

### 1. Information Contract Layer

The core design principle: **govern agent input vs output** If information has been silently degraded before an agent receives it, no amount of output evaluation can recover what was lost.

A contract declares what information must survive a handoff:

```yaml
contract:
  boundary: "researcher_to_analyst"
  required_fields:
    - query_intent
    - source_constraints
    - confidence_intervals
    - methodology_flags
  min_integrity: 0.75
  on_violation: reject_and_log
```

At runtime, the system intercepts the handoff boundary, scores information preservation, and enforces the contract **before** the receiving agent processes anything.

**Scoring uses a dual-track architecture:**

| Track | Method | Use case | Latency |
|-------|--------|----------|---------|
| Real-time | Calibrated embedding-similarity proxy | Production enforcement | <1ms |
| Offline | KSG mutual information estimator | Measurement, calibration | Minutes |

The KSG (Kraskov-Stogbauer-Grassberger) estimator provides rigorous mutual information measurement but scales poorly with dimensionality. The embedding proxy is calibrated against KSG benchmarks and deployed for runtime enforcement.

#### Enforcing a contract in LangGraph

Two integration surfaces ship for LangGraph; pick whichever matches your supervisor pattern (the v0 import path is the integration package — the top-level `precept` namespace is finalised later):

```python
from precept.contract.registry import default_registry
from precept.contract.yaml_loader import load_contract
from precept.integrations.langgraph import create_precept_handoff_tool, evaluate_handoff

default_registry.register(load_contract("contracts/researcher_to_summariser.yaml"))

# Pattern A — pure hook, for the Command(goto=...) pattern.
# Framework-API-independent: imports no langgraph symbol.
from langgraph.types import Command

def supervisor(state):
    evaluate_handoff(state, state, "researcher_to_summariser")
    return Command(goto="summariser")  # raises on a block-mode violation

# Pattern B — drop-in handoff tool for tool-calling supervisors.
# Migration from an uncontracted supervisor: change the import, add contract_name.
handoff = create_precept_handoff_tool("summariser", "researcher_to_summariser")
```

**Fail-open (deliberate, loud).** If the named contract is not registered, `evaluate_handoff` logs a `WARNING`, returns a synthetic *pass* event, and does **not** block. Observability tooling that crashes the pipeline is worse than observability that misses a check.

**Block semantics.** A `mode: block` contract that fails raises `HandoffBlockedError`. In Pattern A it raises inside your node; in Pattern B LangGraph's `ToolNode` surfaces it to the supervisor LLM as an error `ToolMessage` so it can retry or reroute. `warn` mode emits the event and never raises.

**Async safety.** Called from inside an async node, `evaluate_handoff` detects the running loop and offloads the CPU-bound scoring to a worker thread. The fully non-blocking idiom from a coroutine is `await asyncio.to_thread(evaluate_handoff, ...)`.

### 2. Coordination Pattern Observatory

Information-theoretic monitoring that makes multi-agent coordination dynamics visible:

- **Mutual information** between agent action trajectories measures synchronisation (are agents behaving similarly?)
- **Transfer entropy** measures directed causal influence (is Agent A's behaviour causing Agent B's?)

Together, these classify emergent coordination into three categories:

```
Cooperation:  High MI, symmetric TE     → agents coordinating toward shared goal
Competition:  Low MI, low TE            → agents acting independently
Collusion:    High MI, asymmetric TE    → unintended coordination, one agent leading
```

This is distinct from agent-drift metrics that track individual behavioural degradation. The Observatory monitors coordination dynamics *between* agents, making system-level behaviour auditable.

### 3. Experimental Testbed

Five systematically varied information conditions, applied to the same multi-agent environments:

| Condition | What agents observe | Tests |
|-----------|-------------------|-------|
| Full | Complete state information | Baseline |
| Aggregate-only | Mean values, compressed summaries | Information compression effects |
| Delayed | True state with k-step lag | Temporal degradation |
| Noisy | True state + calibrated noise | Signal corruption |
| Asymmetric | Uneven information across agents | Power imbalances |

Environments: DeepMind's Melting Pot (sequential social dilemmas) and the MARL-BC economic simulation framework (Cobb-Douglas production economies with heterogeneous agents).

Keep agents, tasks, learning algorithms constant, isolate information that crosses the boundary.
Hypothesis: **information structure at agent boundaries shapes collective outcomes more than individual agent capability.**

### 4. Collective Decision Interface

Application layer connecting the framework to domains where collective reasoning passes through computational intermediaries before reaching human decision-makers.

**Scenario: Multi-domain policy simulation**

```
Agent 1: Macroeconomic modelling
    │
    ├── [Handoff] Uncertainty bounds compressed ← CONTRACT INTERCEPTS HERE
    │
Agent 2: Health & demographic forecasting
    │
    ├── [Handoff] Regional variance flattened  ← CONTRACT INTERCEPTS HERE
    │
Agent 3: Regional resource allocation
    │
    └── Recommendation reaches human decision-makers
```

Without information contracts, compressed uncertainty at the first handoff silently narrows the range of scenarios downstream agents evaluate. The recommendations appear robust but are derived from a truncated possibility space; populations in the tails of the distribution, those most affected by the policy, are the ones whose outcomes were quietly dropped.

With an information contract at each boundary, this narrowing is detected and surfaced before it propagates.

## Why Upstream, Not Downstream

The existing ecosystem validates **outputs** or traces **execution**. Information contracts validate **inputs**. These are complementary positions in the agent execution stack:

```
Agent A produces output
       │
       ├── Output guardrails check format, safety, hallucination (postcondition)
       │
       ▼
   HANDOFF BOUNDARY
       │
       ├── Information contract scores fidelity of context transfer (precondition)
       │
       ▼
Agent B receives input
       │
       ├── Observability platform logs what Agent B does (downstream trace)
       │
       ▼
Agent B produces output
```

The contract layer is the only position where degraded context is caught before it enters a reasoning process. Once an agent has processed corrupted input, the information loss is irrecoverable.

## Alignment: Collective Flourishing

ARIA identifies *systemic fog*, the opacity that prevents societies from navigating the future, as a defining barrier to collective flourishing. The foundational technologies for modelling, simulating, and coordinating are maturing, but the **integration layer** connecting them remains under-explored.

This framework operates directly at that integration layer:

- The **Observatory** makes systemic complexity legible, converting opaque multi-agent dynamics into auditable coordination patterns
- The **Contract Layer** provides a new coordination mechanism, a declarative way to govern what reasoning processes require at their input boundaries
- The **Testbed** builds the empirical evidence base for *designing* coordination architectures rather than just implementing them
- When information integrity is maintained, collective reasoning becomes a genuine augmentation of human deliberative capacity rather than a source of unobserved distortion

## Status

This framework is the subject of an active research programme combining an MSc dissertation (UCL, completing August 2026) with a fellowship application to Encode: AI for Science (Cohort 2, backed by Pillar VC and ARIA). The Contract Layer and MI estimation engine form the first build phase, followed by the Coordination Observatory and full MARL experimental validation.

## References

1. Hill, Koh & Jishnuanandh (NeurIPS 2025), "Communicating Plans, Not Percepts": agents communicating compressed latent representations achieve 99.9% coordination success vs 12.2% for raw observation passing. Independent validation that information structure at agent boundaries determines collective performance.

2. Lin, Dong, Hao & Zhang (NeurIPS 2023), "Information Design in Multi-Agent Reinforcement Learning": demonstrates the revelation principle fails when both sender and receivers are learning agents. Classical information-theoretic results do not transfer directly to multi-agent learning systems.

3. Johanson, Hughes, Timbers & Leibo (DeepMind, 2022), "Emergent Bartering Behaviour in Multi-Agent Reinforcement Learning": RL agents develop supracompetitive pricing not predicted by conventional theory, establishing the disconnect between autonomous agent behaviour and designed models.

## Author

**Gian Prem Rajaram**
MSc Computer Science, University College London
gian.rajaram.23@ucl.ac.uk
