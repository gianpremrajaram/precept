# Information Contracts for Multi-Agent Reasoning Systems

[![CI](https://github.com/gianpremrajaram/precept/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/gianpremrajaram/precept/actions/workflows/ci.yml)
[![Pages](https://github.com/gianpremrajaram/precept/actions/workflows/pages.yml/badge.svg?branch=main)](https://gianpremrajaram.github.io/precept/)
[![Status: research preview](https://img.shields.io/badge/status-research%20preview-blueviolet)](#status)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

> **Research preview (v0).** APIs are intentionally unstable and will change before v1. The framework is developed alongside an MSc dissertation at UCL (completing August 2026). Suitable for research, experimentation, and early integration feedback; not yet recommended for production.

An open-source framework for measuring, enforcing, and studying how much **usable information** survives the boundaries between reasoning components in multi-agent AI systems - not how much information is shared, but how much the receiving agent can actually use for its task.

**Live observatory:** [gianpremrajaram.github.io/precept](https://gianpremrajaram.github.io/precept/) renders the committed demo trace; drop your own `*.json` trace into the page to inspect a handoff locally (no upload, all rendering is client-side).

## The Problem

Multi-agent AI systems degrade information at every handoff. When context passes from one agent to another, it is compressed, distorted, or silently dropped. In the first empirically grounded taxonomy of multi-agent LLM failures, Cemri et al. (MAST, NeurIPS 2025 Datasets & Benchmarks) attribute ~37% of failures to *inter-agent misalignment* - context lost, ignored, or distorted as it crosses agent boundaries - one of the three top-level categories in their failure taxonomy.

```
Orchestrator          Agent A             Agent B             Agent C
[full context] ──→ [context lost] ──→ [more dropped] ──→ [coherent output]
                        ↓                    ↓                    ↓
                   context compressed   details silently     built on eroded
                   at handoff           dropped              evidence
```

*Schematic, not measured values - quantifying how much usable information is lost at each boundary is exactly what Precept exists to do.*

Every existing tool operates **downstream** of this problem:

| Layer | Examples | What it does | Position |
|-------|----------|-------------|----------|
| Observability | LangSmith, Langfuse, Arize, Datadog | Traces what agents *did* after execution | Downstream |
| Guardrails | CrewAI task guardrails, OpenAI SDK | Validates what agents *produce* | Postcondition |
| Orchestration | LangGraph conditional edges, AutoGen | Routes control flow between agents | Structural |
| **Information Contracts** | **This framework** | **Validates what agents *receive*** | **Upstream (precondition)** |

The upstream boundary is the only position where information loss can be **prevented**.

## Architecture

The package is the information-contract layer plus the surfaces needed to run and inspect it:

1. **Information Contract Layer** - declare, intercept, score, and enforce what must survive a handoff.
2. **Runtime scorer** - the target-free statistic enforced at the boundary, with the offline CPVI measure for calibration.
3. **Trace observatory** - client-side rendering of committed handoff traces.
4. **Integrations** - LangGraph today; AutoGen, CrewAI, and the OpenAI Agents SDK planned.

The CPVI measurement stack and the evaluation testbed live in a companion research repository (see [Measurement and validation](#2-measurement-and-validation)).

Architectural decisions are recorded under [`docs/adr/`](docs/adr/); see [ADR 0001 - Contract Intermediate Representation](docs/adr/0001-contract-ir.md) for how the YAML and decorator frontends converge on a single Pydantic IR consumed by the evaluator.

### 1. Information Contract Layer

The core design principle: **govern agent input vs output.** If information has been silently degraded before an agent receives it, no amount of output evaluation can recover what was lost.

A contract declares what information must survive a handoff. This is the exact shape the YAML loader accepts today:

```yaml
name: researcher_to_analyst
mode: block          # block raises on a violation; warn only emits an event
description: "Research agent handing off to analyst"
fields:
  required_fields:
    - query_intent
    - source_constraints
    - confidence_intervals
    - methodology_flags
  min_fidelity: 0.75
```

`min_fidelity` is the floor on retained fidelity the downstream task requires - conceptually, the minimum *usable information* the receiving agent needs to do its job. In v0 the embedding proxy reads this as a cosine-similarity threshold; it is **not yet** a calibrated usable-information (CPVI) measurement. Richer CPVI-aware contract fields (for example, naming the downstream task or the model family the floor is calibrated for) are a roadmap item and are **not implemented today**.

At runtime, the system intercepts the handoff boundary, scores information preservation, and enforces the contract **before** the receiving agent processes anything.

Scoring measures **usable information** - how much decision-relevant information survives a handoff *for the receiving agent's task*, not how much information is merely shared. It uses a dual-track architecture:

| Track | Method | Use case | Status |
|-------|--------|----------|--------|
| Inline (runtime) | Target-free statistic: embedding-similarity (cosine) gate on a sentence-transformer | Inline enforcement at the handoff boundary | **Ships in v0**; target **<1 ms** inline (see *Latency* below); explicitly a proxy |
| Offline | Conditional usable information via CPVI (conditional pointwise V-usable information) | Measurement, calibration, ground truth | **In development** (dissertation deliverable, Aug 2026) |

**Why not mutual information?** Accurate KSG / k-nearest-neighbour MI estimation is unreliable much beyond ~10-13 dimensions, and the boundary payloads here are 384-dimensional sentence embeddings. MI therefore cannot serve as either the runtime score *or* the offline measure. KSG, MINE, and InfoNCE remain research baselines, not the method.

The offline measure in development is **conditional pointwise V-usable information (CPVI)**: two probes from a fixed model family are fitted, one on the shared state and one on the shared state plus the handoff message, and the score is how much *usable* information the message adds about the downstream outcome beyond the state alone. This is V-information (Xu et al., 2020) conditioned on the shared state (Hewitt et al., 2021), used in place of a raw mutual-information estimator because MI is intractable at embedding dimensionality while a small fitted probe is exactly what V-information is for. In plain terms: train one small model that sees the shared state and one that also sees the message; CPVI is how much more accurately the second predicts the outcome. The v0 inline gate is a deliberately **cheap embedding-similarity (cosine) proxy**: it is *not* a mutual-information measurement and *not yet* the calibrated runtime statistic. The runtime proxy is a target-free statistic, calibrated offline against realised outcomes rather than against CPVI, so it stays valid to threshold at the live boundary. A Jensen-Shannon distribution-match gate is a planned addition to the inline track and is **not yet implemented**.

**Latency.** The cosine comparison itself is sub-millisecond - a 384-dimensional dot product, ~0.3 µs. The cost is the embedding step: v0 re-embeds both sides of every contracted field on each call, so a typical handoff scores in roughly **5-40 ms on a laptop CPU** (a few milliseconds per contracted field). The **<1 ms inline target** is reached by reusing the producer's embedding rather than recomputing it at the boundary, a change v0 does not yet make.

#### Enforcing a contract in LangGraph

Two integration surfaces ship for LangGraph; pick whichever matches your supervisor pattern (the v0 import path is the integration package - the top-level `precept` namespace is finalised later):

```python
from precept.contract.registry import default_registry
from precept.contract.yaml_loader import load_contract
from precept.integrations.langgraph import create_precept_handoff_tool, evaluate_handoff

default_registry.register(load_contract("contracts/researcher_to_summariser.yaml"))

# Pattern A - pure hook, for the Command(goto=...) pattern.
# Framework-API-independent: imports no langgraph symbol.
from langgraph.types import Command

def supervisor(state):
    evaluate_handoff(state, state, "researcher_to_summariser")
    return Command(goto="summariser")  # raises on a block-mode violation

# Pattern B - drop-in handoff tool for tool-calling supervisors.
# Migration from an uncontracted supervisor: change the import, add contract_name.
handoff = create_precept_handoff_tool("summariser", "researcher_to_summariser")
```

**Fail-open (deliberate, loud).** If the named contract is not registered, `evaluate_handoff` logs a `WARNING`, returns a synthetic *pass* event, and does **not** block. Observability tooling that crashes the pipeline is worse than observability that misses a check.

**Block semantics.** A `mode: block` contract that fails raises `HandoffBlockedError`. In Pattern A it raises inside your node; in Pattern B LangGraph's `ToolNode` surfaces it to the supervisor LLM as an error `ToolMessage` so it can retry or reroute. `warn` mode emits the event and never raises.

**Async safety.** Called from inside an async node, `evaluate_handoff` detects the running loop and offloads the CPU-bound scoring to a worker thread. The fully non-blocking idiom from a coroutine is `await asyncio.to_thread(evaluate_handoff, ...)`.

### 2. Measurement and validation

The CPVI measurement stack and the evaluation testbed are developed in a companion research repository, not in this package. The package here ships the contract layer, the runtime scorer, the LangGraph integration, and the trace observatory; the dissertation harness consumes them.

The evaluation substrate is a two-agent cooperative-transport task: two LLM agents negotiate, in natural language, to manoeuvre a T-shaped load through a Pymunk physics arena under a degradable communication channel (full, length-capped, delayed, asymmetric-visibility, noisy). Each agent-to-agent handoff is the boundary Precept scores. External validity is checked on published multi-agent failure logs: the MAST corpus (Cemri et al., above) and Who&When (Zhang et al., 2025). The companion repository is released as a reproducibility artefact alongside the paper.

Companion repository: link forthcoming.

### Future direction: coordination monitoring

Information-theoretic coordination monitoring (mutual information and transfer entropy between agent trajectories, to separate cooperation, competition, and collusion) is an exploratory direction, not part of the current package or roadmap.

## Why Upstream

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

*Systemic fog*, the opacity that prevents societies from anticipating the future, as a defining barrier to collective flourishing. The foundational technologies for modelling, simulating, and coordinating are maturing, but the **integration layer** connecting them remains under-explored.

This framework operates directly at that integration layer:

- The **contract layer** provides a new coordination mechanism: a declarative way to govern what reasoning processes require at their input boundaries.
- The **runtime scorer and trace observatory** make boundary fidelity legible, turning an otherwise invisible handoff into an inspectable, scored event.
- The companion **measurement work** builds the empirical evidence base for *designing* coordination architectures rather than just implementing them.

When information integrity is maintained, collective reasoning becomes a genuine augmentation of human deliberative capacity rather than a source of unobserved distortion.

## Status

This framework is the subject of an active research programme built around an MSc dissertation (UCL, completing August 2026). The contract layer, runtime proxy scorer, LangGraph integration, and trace observatory form the shipping v0; the calibrated CPVI scorer is the dissertation deliverable; the CPVI measurement stack and the evaluation testbed live in a companion research repository.

| Component | State | Notes |
|-----------|-------|-------|
| Contract Layer (YAML and decorator frontends, registry, evaluator) | Working | v0 surface ships with the package |
| LangGraph integration (`evaluate_handoff`, `create_precept_handoff_tool`) | Working | Sync and async-from-coroutine paths |
| Embedding-similarity proxy scorer (`EmbeddingProxy`) | Working | v0 default; cosine on `all-MiniLM-L6-v2` |
| OpenTelemetry exporter | Working | Opt-in via the `[otel]` extra |
| Static HTML trace observatory and demo trace | Working | Live at the link above; client-side rendering only |
| Calibrated scorer | In development | Dissertation deliverable; CPVI offline measure plus a target-free runtime statistic calibrated against outcomes |
| Measurement stack and testbed (Pymunk T-transport, channel conditions, Who&When/MAST) | Companion repo | Developed alongside the dissertation; released with the paper |
| Coordination monitoring (MI / transfer entropy) | Exploratory | Not on current roadmap; see Future direction above |
| AutoGen, CrewAI, OpenAI Agents SDK integrations | Planned | Post-MVP |

The public API surface under `precept.*` is not yet committed: `__all__` declarations finalise at the v0.1.0 release, and any imported symbol should be treated as subject to change until then.

## References

1. **Cemri, Pan, Yang, et al. (NeurIPS 2025 Datasets & Benchmarks), "Why Do Multi-Agent LLM Systems Fail?"** (MAST) - arXiv:2503.13657. A failure taxonomy over 200+ annotated multi-agent traces; ~37% of failures attributed to *inter-agent misalignment* (context lost, ignored, or distorted at handoffs). Anchors the problem statement above.

2. **Xu, Zhao, Song, Stewart & Ermon (ICLR 2020), "A Theory of Usable Information Under Computational Constraints"** - arXiv:2002.10689. Introduces predictive *V-information*, which, unlike Shannon mutual information, is reliably estimable in high dimensions with PAC-style guarantees. The theoretical basis for scoring *usable* information rather than mutual information.

3. **Ethayarajh, Choi & Swayamdipta (ICML 2022, Outstanding Paper), "Understanding Dataset Difficulty with V-Usable Information"** - arXiv:2110.08420. Defines V-usable information and **pointwise V-usable information (PVI)**, the basis for Precept's offline CPVI measure.

4. **Lu, Chen, Li, Bitterman, Savova & Gurevych (Findings of EMNLP 2023), "Measuring Pointwise V-Usable Information In-Context-ly"** - arXiv:2310.12300. In-context PVI: estimating PVI from a handful of exemplars.

5. **Hewitt, Ethayarajh, Liang & Manning (EMNLP 2021), "Conditional probing: measuring usable information beyond a baseline"** - arXiv:2109.09234. Conditions V-information on a baseline representation, measuring the usable information a signal adds *beyond* what the baseline already carries. The conditioning move behind CPVI: the handoff message is scored for what it adds beyond the shared state.

6. Hill, Koh En Wei & Jishnuanandh (NeurIPS 2025 SEA workshop), "Communicating Plans, Not Percepts: Scalable Multi-Agent Coordination with Embodied World Models" - arXiv:2508.02912. An engineered world model that communicates compact *plans* sustains near-perfect coordination as the environment scales (96.5-99.9% success), while a learned end-to-end message protocol collapses (to 12.2% at the 15×15 scale). Evidence that *how* information is structured at agent boundaries, not merely that agents communicate, governs collective performance.

7. Lin, Dong, Hao & Zhang (NeurIPS 2023), "Information Design in Multi-Agent Reinforcement Learning": demonstrates the revelation principle fails when both sender and receivers are learning agents. Classical information-theoretic results do not transfer directly to multi-agent learning systems.

8. Johanson, Hughes, Timbers & Leibo (DeepMind, 2022), "Emergent Bartering Behaviour in Multi-Agent Reinforcement Learning": RL agents develop supracompetitive pricing not predicted by conventional theory, establishing the disconnect between autonomous agent behaviour and designed models.

## Author

**Gian Prem Rajaram**
MSc Computer Science, University College London
gian.rajaram.23@ucl.ac.uk
