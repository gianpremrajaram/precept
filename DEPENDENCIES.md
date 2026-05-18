# Precept v0.1.0 - Technical Dependencies, Risks, and Production Readiness

> Companion document to [ISSUES.md](./ISSUES.md). Read ISSUES.md first. This document is the technical governance layer on top of the issue backlog - dependency analysis, cross-cutting concerns, risk register, and release readiness criteria in depth.

---

## How to use this document

This file serves three audiences. Engineers picking up issues use the critical path section to understand what must already be merged before their work is unblocked. The release manager (Gian, at v0.1.0) uses the readiness checklist and risk register to decide when to ship. A Phase 2 maintainer inheriting the repo uses the cross-cutting concerns and technical-debt ledger to understand why the v0 surface looks the way it does.

Every section refers to specific issues by ID (PRC-XXX). When the implementation inevitably deviates from the plan, update the referenced sections here, not scattered in commit messages.

## Document changelog

**Revision 2** (current): incorporates production-readiness feedback. Key changes from Rev 1: (1) PRC-004a added - front-loads PyPI/TestPyPI OIDC to Sprint 0. (2) Circular dependency between PRC-014 and PRC-015 removed by relocating `HandoffBlockedError` to PRC-013. (3) PRC-016 narrowed from full state serialiser to focused contracted-field extractor. (4) PRC-014 expanded to provide both tool wrapper AND `evaluate_handoff()` pure function, with async-context auto-dispatch. (5) PRC-011 model load moved to constructor. (6) `Exporter` ABC added to PRC-013. (7) 4 KiB event-payload ceiling added to `ViolationEvent.to_compact_dict()`. (8) PRC-026 excludes `OTelExporter` from top-level `__all__`. (9) PRC-019 exit codes follow Unix convention. (10) Toolchain consolidation: `ruff format` replaces `black`. Dependency graph, critical path, risk register, and performance baseline all updated accordingly.

---

## 1. Critical Path Analysis

The critical path is the longest chain of dependent issues that determines the earliest possible release date. Slippage on any critical-path item delays the release one-for-one; slippage off the path is absorbable.

### 1.1 The v0.1.0 critical path

```
PRC-001 (repo skeleton)
   ↓
PRC-003 (CI pipeline) ─────────┐
   ↓                            ↓
PRC-005 (architecture ADR)   PRC-004a (OIDC publishers)
   ↓                            │
PRC-006 (HandoffContract IR)    │
   ↓                            │
PRC-010 (Scorer ABC) ─────┐     │
   ↓                       ↓     │
PRC-011 (EmbeddingProxy)  PRC-012 (rule evaluators)
   ↓                       ↓     │
   └───────┬───────────────┘     │
           ↓                     │
       PRC-013 (Evaluator + HandoffBlockedError + Exporter ABC + ViolationEvent)
           ↓                     │
       PRC-016 (extract_payload)─┤
           ↓                     │
       PRC-014 (LangGraph: tool wrapper + evaluate_handoff hook)
           ↓                     │
       PRC-015 (impact summaries populator)
           ↓                     │
       PRC-017 + PRC-018 (fixtures + contracts, co-designed)
           ↓                     │
       PRC-019 (demo runner)     │
           ↓                     │
       PRC-022 (observatory) ─┐  │
           ↓                   ↓  │
       PRC-023 (Pages deploy) PRC-024 (README)
           ↓                   ↓  │
           └─────┬─────────────┘  │
                 ↓                │
           PRC-026 (public API) ──┤
                 ↓                ↓
           PRC-027 (release) ←────┘
```

**Path length:** ~15 dependent items (added PRC-016 into the chain because PRC-014 now depends on `extract_payload`, added PRC-004a as a Sprint-0 prerequisite for PRC-027). At the S/M/L sizing, the critical path totals approximately 60-90 hours of focused work. That maps to a 10-12 day timeline at 6-8 focused hours per day with some concurrency slack; the timeline philosophy is "ship when right, not on day 10".

### 1.2 Dependency changes vs Rev 1

| Change | Reason |
|---|---|
| PRC-004 no longer depends on PRC-003 | Pre-commit hooks don't require CI to be set up; repo scaffold alone suffices. |
| PRC-004a inserted as new Sprint-0 ticket | Front-loads OIDC publisher config; prevents day-10 release-workflow failure. |
| PRC-015 no longer depends on PRC-014 | `HandoffBlockedError` class moved to PRC-013 to break the circular reference; PRC-015 is now purely the impact-template populator and depends only on PRC-013. |
| PRC-016 simplified; on critical path | Original full-state serialiser was off-path (P1); new focused contracted-field extractor is used by PRC-014's `evaluate_handoff` and is therefore now P0 on path. |
| PRC-014 expanded (now XL) | Two integration surfaces (tool wrapper + pure hook) instead of one. Absorbs more engineering time; this is the pragmatic response to LangGraph's dual pattern landscape. |
| PRC-025 (arch docs) off path | Still P1 but can land post-release as v0.1.1 docs if time-constrained. |
| PRC-020/021 (exporters) off path | P1; release can ship with JSON-only export and add OTel in v0.1.1 if needed. Both are scheduled for MVP. |

### 1.3 Off-path items (parallelisable)

- PRC-002 (CONTRIBUTING/CoC): Sprint 0, repo hygiene.
- PRC-004 (pre-commit): improves dev velocity.
- PRC-007 (YAML loader): required for PRC-018 but can be picked up alongside PRC-006/010.
- PRC-008 (decorator, sync only): developer ergonomics; required for PRC-026 export but a 3-4h task.
- PRC-009 (registry): enables PRC-014 but is low-effort.
- PRC-020 (OTel exporter), PRC-021 (JSON exporter): P1.
- PRC-025 (arch docs, contract reference): P1.
- PRC-028 through PRC-036: Phase 2.

### 1.4 Parallel work recommendations

For a single engineer (Gian solo): follow the critical path sequentially. Use Sprint 0 Day 0 to set up PRC-001/003/004a in one sitting (PyPI/TestPyPI OIDC is a 2-3h click-through task); PRC-005 and PRC-006 in parallel; PRC-010/011/012 as a single Sprint 1 block. Sprint 2 is the biggest chunk: PRC-013 (enlarged) + PRC-014 (enlarged XL) + PRC-015 + PRC-016 + PRC-017/018. Budget 4-5 days for Sprint 2.

If a second engineer joins, split as: path driver on contract/scoring/evaluator/integration, second on exporters + observatory + docs. Handoff point is PRC-013 completion; both converge at PRC-024.

---

## 2. Dependency Graph (table form)

Direct dependencies (issue cannot start until dependencies are merged):

| Issue | Direct dependencies | Transitive depth | On critical path? |
|---|---|---|---|
| PRC-001 | none | 0 | Yes |
| PRC-002 | PRC-001 | 1 | No |
| PRC-003 | PRC-001 | 1 | Yes |
| PRC-004 | PRC-001 | 1 | No |
| PRC-004a | PRC-001 | 1 | Yes (enables PRC-027) |
| PRC-005 | PRC-001 | 1 | Yes |
| PRC-006 | PRC-005 | 2 | Yes |
| PRC-007 | PRC-006 | 3 | No (required for PRC-018) |
| PRC-008 | PRC-006 | 3 | No (required for PRC-026 list) |
| PRC-009 | PRC-006, PRC-007, PRC-008 | 4 | No |
| PRC-010 | PRC-006 | 3 | Yes |
| PRC-011 | PRC-010 | 4 | Yes |
| PRC-012 | PRC-010 | 4 | Yes |
| PRC-013 | PRC-011, PRC-012 | 5 | Yes |
| PRC-014 | PRC-006, PRC-009, PRC-013, PRC-016 | 7 | Yes |
| PRC-015 | PRC-013 | 6 | Yes |
| PRC-016 | PRC-006, PRC-013 | 6 | Yes |
| PRC-017 | PRC-006 | 3 | Yes (via PRC-019) |
| PRC-018 | PRC-007 | 4 | Yes (via PRC-019) |
| PRC-019 | PRC-014, PRC-015, PRC-017, PRC-018 | 8 | Yes |
| PRC-020 | PRC-013 | 6 | No (P1 exporter) |
| PRC-021 | PRC-013 | 6 | No (P1 exporter) |
| PRC-022 | PRC-017, PRC-018, PRC-019, PRC-021 | 9 | Yes |
| PRC-023 | PRC-022 | 10 | Yes |
| PRC-024 | PRC-019, PRC-022, PRC-023 | 11 | Yes |
| PRC-025 | PRC-005, PRC-006, PRC-011 | 5 | No |
| PRC-026 | PRC-006, PRC-008, PRC-013, PRC-014 | 7 | Yes |
| PRC-027 | PRC-004a, all P0 items | terminal | Yes |

The deepest chain (11 levels) still runs through PRC-024, confirming README-readiness as the latest-to-land critical artefact. PRC-014 and PRC-027 now have wider fan-in than Rev 1.

### 2.1 Verifying the circular-dependency fix

Before Rev 2: PRC-014 "raise HandoffBlockedError" → PRC-015 "defines HandoffBlockedError" → depends on PRC-014 (circular).

After Rev 2: PRC-014 imports `HandoffBlockedError` from `precept.errors` (defined in PRC-013). PRC-015 defines the impact-summary populator only, imports `HandoffBlockedError` from `precept.errors` (defined in PRC-013). No cycle.

Regression test in PRC-013 Definition of Done confirms: "circular dependency with PRC-014 confirmed broken (PRC-014 imports `HandoffBlockedError` from `precept.errors` with no upstream import path back to PRC-014/015)".

---

## 3. External Dependency Analysis

Every external dependency is a risk surface: upstream breakage, security advisories, API drift, licence changes. v0.1.0 pins aggressively to minimise exposure and documents the pin rationale for future maintainers.

### 3.1 Runtime dependencies

| Package | Version floor | Rationale for floor | Upper bound | Risk level |
|---|---|---|---|---|
| `pydantic` | `>=2.5` | IR requires Pydantic v2 (`ConfigDict`, `field_validator`, `model_dump`) | `<3` | Low - mature, widely used, predictable releases |
| `pyyaml` | `>=6.0` | `safe_load` with modern loader defaults | `<7` | Low - stable, no signals of v7 |
| `sentence-transformers` | `>=2.2,<4` | `encode()` API stable across 2.x/3.x | `<4` | Medium - fast-moving; pin tightly post-v0.2 |
| `numpy` | `>=1.24,<3` | Typing support, avoiding numpy 2.0 pre-release issues | `<3` | Low |
| `langgraph` | `>=0.5,<0.7` | `create_handoff_tool` shape; issue #205 context; `Command` API stable | `<0.7` | **High** - see section 4.1 |
| `langchain-core` | `>=0.3` | Used transitively via langgraph; pin to what langgraph needs | `<1` | Medium |
| `opentelemetry-api` | `>=1.30` | GenAI semantic conventions coverage | `<2` | Medium - GenAI conventions experimental |

### 3.2 Optional dependencies (extras)

| Extra | Packages | Rationale |
|---|---|---|
| `precept[otel]` | `opentelemetry-sdk>=1.30,<2` | OTel SDK is ~15MB install; users who don't export to OTel shouldn't pay. PRC-020 import-guards this explicitly. |
| `precept[dev]` (contributors only) | `pytest`, `pytest-cov`, `hypothesis`, `mypy`, `ruff`, `bandit`, `pip-audit`, `pre-commit` | All contributor tools. Note: `black` NOT included; `ruff format` is the formatter. |

Dev-deps change from Rev 1: `black` removed; it duplicated `ruff format` and added hook latency and potential format conflicts. `ruff` alone handles both lint and format.

### 3.3 Dependency risk mitigation

1. **Every runtime dep is pinned with both floor and upper bound.** No floating-upper-bound specifiers. This prevents transitive major-version breakage on `pip install precept` six months from now.

2. **Optional dependencies via extras.** `opentelemetry-sdk` ships as `precept[otel]`. The import-guard pattern in PRC-020 means base installs don't encounter the OTel surface at all.

3. **`requirements-dev.lock`.** Generate a fully-resolved lockfile via `pip-tools` or `uv pip compile` committed to the repo under `requirements-dev.lock`. CI uses the lockfile; the `pyproject.toml` specifiers are the published surface.

4. **Renovate configuration.** `.github/renovate.json` with rules: auto-PR patch and minor updates, batch updates weekly, require CI green to automerge patch updates. Major version updates open a PR for human review.

5. **Supply-chain hygiene.** `pip-audit` runs weekly via a scheduled GitHub Action (add to `.github/workflows/audit.yml`). Alerts on known CVEs in any direct or transitive dep.

### 3.4 Model / weight dependencies

`all-MiniLM-L6-v2` is downloaded from HuggingFace on constructor-time `EmbeddingProxy` instantiation (~80MB). This is an external dependency the typical Python supply-chain audit does not cover.

- **Pinning:** specify the exact model revision commit (e.g., `sentence-transformers/all-MiniLM-L6-v2@<commit>`) in the `EmbeddingProxy` constructor default.
- **Integrity:** HuggingFace ships model weights with SHA256 checksums; verify on load.
- **Offline operation:** `EmbeddingProxy` fails at constructor time (not first `score()` call) if the model is not cached and the network is unavailable, with a clear error message.
- **Model licence:** `all-MiniLM-L6-v2` is Apache 2.0. Include a notice in `docs/legal/model_notices.md` listing every model weight redistributed with or invoked by Precept.

Rev 2 change: model download now happens at `EmbeddingProxy()` constructor, not lazily at first `score()`. This shifts the failure mode from "mysterious hang during first handoff" to "clear failure at application startup", which is strictly better for production debugging and prevents asyncio-loop-blocking surprises.

---

## 4. Integration Risk Register

Risks specific to external framework integrations. These need active monitoring post-release.

### 4.1 LangGraph API instability (HIGH)

**Context:** `langgraph-supervisor` (the library PRC-014's tool-wrapper path builds against) carried an open issue (#205) where supervisor handoffs didn't cleanly pass state. LangChain's guidance post-2025 is to use manual supervisor patterns via tools rather than the `langgraph-supervisor` helper. The `Command(goto=...)` pattern is increasingly preferred. `langgraph` itself is a pre-1.0 library with ongoing API churn.

**Impact:** Breakage in PRC-014's tool wrapper on any `langgraph` minor version bump.

**Mitigation (strengthened in Rev 2):**
1. Pin `langgraph>=0.5,<0.7` in v0.1.0.
2. PRC-014 now provides BOTH a tool wrapper AND a pure `evaluate_handoff()` function. The pure function is framework-API-independent: if LangGraph's tool-creation API changes radically, only the wrapper breaks; the pure function continues working.
3. Add a CI job that exercises both integration paths against the pinned version on every PR.
4. Document in PRC-014's tests: which LangGraph API surface each path depends on, so drift is detectable.
5. On LangGraph minor-version releases: run the integration test suite against the new version on a branch; only bump the upper bound after green.

**Owner:** PRC-014 owner, permanent.

### 4.2 Async/sync boundary (MEDIUM, new in Rev 2)

**Context:** LangGraph nodes can be sync OR async. `EmbeddingProxy.score()` is CPU-bound sync (~500ms). Called naively from an async coroutine, it blocks the event loop, potentially crashing concurrent agent runs.

**Impact:** User reports of Precept "hanging" or degrading agent throughput when used in async LangGraph pipelines.

**Mitigation:**
1. Constructor-time model load (PRC-011) removes the multi-second cold-start spike that would otherwise be the worst-case loop block.
2. `evaluate_handoff()` auto-detects running asyncio loop and dispatches to `asyncio.to_thread()` (PRC-014).
3. Async-safety smoke test in PRC-011 and PRC-014 verifies event loop is not blocked measurably.
4. Documented prominently in PRC-011 docstring and README.

**Owner:** PRC-011 and PRC-014 owners.

### 4.3 OTel GenAI semantic conventions churn (MEDIUM)

**Context:** OTel GenAI semantic conventions are status `Development` / experimental as of April 2026. Attribute names (`gen_ai.evaluation.score.value`, etc.) may change before the conventions mark stable.

**Impact:** Precept's OTel exports become incompatible with the conventions or with downstream consumers (Datadog, Grafana, etc.) that track the evolving spec.

**Mitigation:**
1. PRC-020 pins to a specific semantic conventions version in the module docstring.
2. Respect `OTEL_SEMCONV_STABILITY_OPT_IN` environment variable per OTel guidance.
3. Commit to emit-then-migrate pattern: when OTel renames `gen_ai.evaluation.score.value` to something else, Precept supports both emissions in parallel for one minor version, then deprecates the old.
4. Changelog any semantic-conventions version bump explicitly.

**Owner:** PRC-020 owner, permanent.

### 4.4 OTel payload size limits (HIGH, new in Rev 2)

**Context:** OTel attribute size limits vary by backend: Datadog 4 KiB, Jaeger similar, OpenObserve 8 KiB, Honeycomb 64 KiB. 4 KiB is the realistic worst-case. Events exceeding this are silently dropped by some backends.

**Impact:** Silent event loss = silent observability loss = Precept's core value proposition broken.

**Mitigation:**
1. Two-tier enforcement: (a) event-level ceiling in `ViolationEvent.to_compact_dict()` progressively truncates summaries to keep total under 4 KiB; (b) per-attribute check in OTel exporter catches any single attribute exceeding the limit even within a compliant total.
2. `precept.payload_truncated: True` attribute surfaces when truncation occurred, so users can investigate.
3. Test with synthetically inflated 10 KiB events to verify truncation works.

**Owner:** PRC-013 and PRC-020 owners.

### 4.5 Import-surface failure on base install (MEDIUM, new in Rev 2)

**Context:** If `OTelExporter` is listed in top-level `__all__` or re-exported from `precept.exporters`, users on base install (`pip install precept` without `[otel]`) will hit `ImportError` on `from precept import *` or similar wildcard patterns.

**Impact:** Broken user experience on first import for the common case.

**Mitigation:**
1. PRC-026 explicitly excludes `OTelExporter` from top-level `__all__`.
2. `precept.exporters.__init__` does NOT import from `.otel`.
3. Import-surface smoke test in CI runs on a fresh venv with ONLY `pip install precept`; asserts `import precept`, `from precept import Evaluator`, etc. all succeed without touching OTel.
4. Same test asserts `from precept.exporters.otel import OTelExporter` raises clear ImportError with install hint.

**Owner:** PRC-026 owner.

### 4.6 sentence-transformers model changes (LOW-MEDIUM)

**Context:** HuggingFace model revisions can occur. If `all-MiniLM-L6-v2` is updated upstream and Precept pins only the model name (not revision), outputs become non-deterministic.

**Impact:** Proxy scores drift without a code change. Testing no longer reproducible.

**Mitigation:**
1. Pin model revision commit in `EmbeddingProxy` default.
2. Document in CHANGELOG any model revision change with before/after calibration on the demo fixtures.

### 4.7 Pydantic v3 (FUTURE)

Not a v0.1.0 risk; flagged for Phase 2. Pydantic v3 will introduce breaking changes. Monitor Pydantic roadmap quarterly.

---

## 5. Cross-Cutting Concerns

Implementation concerns that span multiple issues. Handling these consistently from day one prevents the kind of uneven code quality that makes a codebase feel "early" for longer than it needs to.

### 5.1 Error handling discipline

- All public API functions raise Precept-specific exceptions only: `ContractValidationError`, `HandoffBlockedError`. Downstream `pydantic.ValidationError` is wrapped and re-raised.
- Every exception carries actionable information: contract name, field name, expected vs actual values.
- Never use bare `except:` or `except Exception:` swallows. Errors either propagate or are handled with explicit logging.
- Default behaviour on missing contract (PRC-014): log WARNING, do NOT raise, do NOT emit an event. This is "fail-open" design for observability tooling. Document loudly.
- Exporter failures are ALWAYS swallowed per `Exporter` ABC contract (PRC-013): an evaluator should never fail because an exporter did.
- `HandoffBlockedError.impact_summary` is mutable-by-default-empty; populator runs immediately before raise in PRC-014.

### 5.2 Logging strategy

- Use `logging` with module-level loggers: `logger = logging.getLogger(__name__)`.
- Log levels:
  - `DEBUG`: per-handoff evaluation trace, per-field scores, model loading events.
  - `INFO`: contract registration, exporter initialisation, model load complete with memory footprint.
  - `WARNING`: missing contract on evaluation, degraded mode (e.g., OTel not configured, falling back to no-op exporter), payload truncation.
  - `ERROR`: never used by Precept itself.
- Never log payload content at `INFO` or above.
- Library code never configures handlers; the user's application owns logger configuration.

### 5.3 Type discipline

- `mypy --strict` clean across `src/precept/`. Enforced in CI (PRC-003).
- Public API functions fully annotated with concrete types; no `Any` escapes except where genuinely polymorphic (payload field values).
- Prefer `typing.Protocol` over `typing.Callable` for callback interfaces with more than one method.
- `from __future__ import annotations` at the top of every module.

### 5.4 Testing strategy

- Test layout mirrors source layout.
- Three test tiers:
  - **Unit** (`tests/unit/`): in-process, no I/O, single module scope. Run on every commit. Must complete in < 30s total.
  - **Integration** (`tests/integration/`): exercises multiple modules together. Run on every PR. May take 1-3 minutes.
  - **E2E** (`tests/e2e/`, if added): real LangGraph pipeline including LLM calls. Not run in CI by default.
- Property-based testing (`hypothesis`) for input validation logic (PRC-006, PRC-012, PRC-016). Property tests find edge cases example-based tests miss.
- Fixtures are real-seeming, not lorem ipsum (PRC-017).
- Coverage target: 80%+ on `src/precept/contract/` and `src/precept/scoring/`.
- `pytest-xdist` for parallel unit test execution.

### 5.5 Production-readiness test gates (new in Rev 2)

Three tests added to release criteria that gate against real production surfaces, not just unit-level behaviour:

1. **Import-surface smoke test** (PRC-026): fresh venv on PyPI; verifies base install doesn't trigger OTel ImportError; verifies `[otel]` extra enables OTel imports.
2. **Async-safety smoke test** (PRC-011, PRC-014): verifies `evaluate_handoff()` called from inside a running asyncio loop does not block the loop measurably. Implementation: measure loop tick count before/during the call.
3. **Secret-leakage regression test** (PRC-016): state dict with uncontracted fields containing secret-like strings; assert those strings NEVER appear in the resulting `HandoffPayload`, `ViolationEvent`, or any exporter output.

These are the three "failure modes I actually worry about in production" translated into CI gates.

### 5.6 Versioning and API stability

- Semantic versioning strictly from v0.1.0 onward.
- Pre-1.0 minor versions (0.1 → 0.2) MAY contain breaking changes but only with CHANGELOG notice and migration guidance.
- Post-1.0, breaking changes are major version bumps only.
- Everything not in `__all__` (PRC-026) is private.
- `CHANGELOG.md` follows Keep a Changelog format.

### 5.7 Observability of Precept itself (meta-observability)

Precept is an observability tool. Its own operational state must be observable too.

- Emit internal metrics via OTel (when `precept[otel]` installed): counter for evaluations performed, counter for violations by contract name, histogram of scorer latency, gauge of registered contracts. Namespace: `precept.*`.
- Metric emission opt-in via `precept.enable_self_metrics()`; not on by default.

### 5.8 Concurrency model

- Evaluator and exporters are thread-safe.
- `EmbeddingProxy` (PRC-011): model inference is thread-safe; multiple threads calling `score()` are safe. One instance per process recommended.
- No native `asyncio` in v0 core. `evaluate_handoff()` (PRC-014) auto-dispatches to `asyncio.to_thread` when called from a coroutine - addresses the async story without requiring a dual API.
- Native async API is a v0.2 consideration based on user demand.

### 5.9 Memory and resource management

- `EmbeddingProxy` holds a ~80MB model in memory (~150-200MB resident total with Python overhead). Document in PRC-011. Users should reuse a single instance.
- No unbounded state accumulation. `ContractRegistry` has no eviction, but contracts are small.
- File handles closed deterministically: all file I/O in context managers.

### 5.10 Payload size enforcement (new in Rev 2)

- `ViolationEvent.to_compact_dict()` enforces 4 KiB total ceiling with progressive truncation.
- OTel exporter (PRC-020) has secondary per-attribute check.
- JSON exporter (PRC-021) does NOT truncate (file storage is not size-constrained; full events are more useful for post-hoc analysis).
- `precept.payload_truncated: True` flag propagates when truncation occurred.

---

## 6. Security Posture

A tool that instruments production AI pipelines is a potential attack surface. v0.1.0's security posture is conservative by design.

### 6.1 Code-level security

- `bandit -r src/precept -ll` runs in CI (PRC-003). Any MEDIUM or HIGH finding blocks merge.
- `pip-audit` runs weekly.
- YAML loading uses `yaml.safe_load` exclusively (PRC-007).
- Pickle is not used anywhere.
- No `eval` / `exec` / `compile` on user-provided data.
- Regex patterns for validation are anchored, bounded, safe from ReDoS.

### 6.2 Supply-chain security

- Dependency pinning per section 3.
- PyPI trusted publishing via OIDC (PRC-004a + PRC-027). No long-lived API tokens. Both PyPI and TestPyPI configured in Sprint 0.
- GitHub Actions environments gate PyPI deploys behind reviewer approval.
- `pyproject.toml` integrity verified in CI.
- GitHub repo: branch protection, signed commits optional but recommended, 2FA required for maintainers.

### 6.3 Data handling

- **Contracted-fields-only extraction** (PRC-016): uncontracted state is never read. This is the strongest possible defence against accidental secret extraction - we literally cannot leak what we don't touch. Regression test enforces this.
- `ViolationEvent.source_summary` and `target_summary` truncate to 100 chars per field; event-level 4 KiB ceiling applies further.
- Full-content capture requires explicit opt-in via env var (PRC-020).
- No telemetry phone-home. Precept does not contact any Precept-operated server.

### 6.4 Disclosure policy (future)

Set up `SECURITY.md` at the first external-user indication. For v0.1.0, security reports route to the maintainer email in `CODE_OF_CONDUCT.md`. Document a response SLA of 72h for initial acknowledgement.

---

## 7. Performance Baseline

v0.1.0 performance is honest-proxy-level, not production-latency. The dissertation's calibrated scorer (Phase 2) addresses the latency moat claim.

| Operation | Target | Rationale |
|---|---|---|
| Contract load (YAML) | < 50ms | PyYAML + Pydantic validation on a typical-sized YAML (~1KB) |
| Decorator application | < 1ms (decoration time) | Just attaching a Pydantic instance |
| `EmbeddingProxy()` constructor (cold cache) | < 5s | Model download + load. Documented as startup cost. |
| `EmbeddingProxy()` constructor (warm cache) | < 1.5s | Local model load. |
| `EmbeddingProxy.score()` first call | < 500ms per 3-field contract | No longer includes download (handled in constructor). |
| `EmbeddingProxy.score()` subsequent calls | < 500ms per 3-field contract | CPU-only, typical laptop. |
| `extract_payload()` (PRC-016) | < 1ms | Dict/attribute access on contracted fields only; no recursion. |
| `Evaluator.evaluate()` excluding scorer | < 10ms | Rules are pure CPU logic on small dicts. |
| `ViolationEvent.to_compact_dict()` with no truncation | < 5ms | JSON serialisation + size check. |
| `ViolationEvent.to_compact_dict()` with truncation needed | < 15ms | Iterative truncation. |
| JSON exporter write | < 1ms per event | File buffer write. |
| OTel exporter emit | < 5ms per event | SDK overhead. |
| `evaluate_handoff()` from async context (loop non-blocking) | Loop tick delay < 10ms | `asyncio.to_thread` dispatch. |
| Demo runner full execution | < 30s | Per release criterion. |

Any regression >20% post-MVP opens an investigation ticket. Observability tools whose costs exceed their value are not adopted.

Rev 2 change: separated constructor-load timing from score()-call timing; added `extract_payload()` and `to_compact_dict()` rows; added async-context dispatch target.

---

## 8. Release Readiness Checklist (v0.1.0)

In addition to the per-issue Definition of Done, the release itself has gate criteria that the release manager verifies before tagging v0.1.0.

### 8.1 Code gates

- [ ] All P0 issues closed.
- [ ] CI green on `main` for 24 consecutive hours with no retries.
- [ ] `mypy --strict` clean.
- [ ] `ruff check .` and `ruff format --check .` clean.
- [ ] `bandit` HIGH/MEDIUM findings: 0.
- [ ] `pip-audit` known CVEs: 0 in direct deps; documented exemptions for transitive deps.
- [ ] Coverage: ≥ 80% on `src/precept/contract/`, ≥ 80% on `src/precept/scoring/`, ≥ 60% overall.

### 8.2 Functional gates

- [ ] Demo runs in < 30s on fresh Ubuntu 22.04 with no API keys.
- [ ] Demo runs in < 30s on fresh macOS 14+.
- [ ] Demo exit code is 0 for both clean and degraded traces (PRC-019 convention).
- [ ] Observatory `docs/index.html` loads on Chrome, Firefox, Safari latest stable; renders both demo traces without JS errors.
- [ ] `pip install precept==0.1.0` from TestPyPI then PyPI succeeds on Python 3.10/3.11/3.12 on Linux x86_64 and macOS ARM64.
- [ ] **Base-install import-surface smoke test passes**: fresh venv, `pip install precept` (no extras), `import precept` and all `__all__` entries work; `from precept.exporters.otel import OTelExporter` raises ImportError with install hint.
- [ ] **Extras-install import-surface smoke test passes**: fresh venv, `pip install precept[otel]`, OTel import succeeds.
- [ ] **Async-safety smoke test passes**: `evaluate_handoff()` called from inside asyncio coroutine does not block event loop measurably.
- [ ] **Secret-leakage regression test passes**: state with uncontracted secret-like fields produces `HandoffPayload` containing only contracted fields.
- [ ] Every code snippet in README executes verbatim.
- [ ] Every link in README returns HTTP 200.
- [ ] CHANGELOG entry for v0.1.0 enumerates all shipped features with issue links.

### 8.3 Documentation gates

- [ ] README covers: positioning, quickstart (BOTH tool-wrapper and `evaluate_handoff` patterns), competitive contrast, scorer-status honesty, A2A roadmap note.
- [ ] Architecture doc (`docs/architecture.md`) ships.
- [ ] Contract reference (`docs/contract_reference.md`) ships and matches PRC-006 schema.
- [ ] Release process doc (`docs/release_process.md`) includes rollback runbook.
- [ ] Observatory URL live, accessible, rendering.
- [ ] Gian opens repo in fresh browser tab, runs demo, narrates Precept in under 5 minutes without notes.

### 8.4 Release mechanics

- [ ] Tag `v0.1.0` created on `main`.
- [ ] GitHub Release created with changelog body.
- [ ] PyPI package published via OIDC trusted publisher (pre-configured in PRC-004a).
- [ ] Fresh-environment smoke test (scripted, in `scripts/release/fresh_smoke.sh`) passes.

### 8.5 Abort criteria

Any single checklist item failing defers the release by at least 24 hours. Shipping with a failing item is not acceptable even under timeline pressure. Timeline is not a release gate; quality is.

---

## 9. Post-Launch Monitoring

v0.1.0 is an open-source library with no server-side component; there is no uptime to monitor. What remains is adoption telemetry and feedback.

### 9.1 Adoption signals to track weekly

- PyPI download counts (via pypi-stats)
- GitHub stars, forks, clones, traffic
- GitHub issues opened, closed, and their category
- External mentions in blog posts, forum discussions

### 9.2 Feedback channels

- GitHub issues: primary.
- GitHub Discussions: secondary, enabled at release.
- Email (from CODE_OF_CONDUCT.md): sensitive issues only.

### 9.3 Patch release cadence

- Critical bugs (crashes, incorrect violations, security): patch release within 7 days.
- Non-critical bugs, minor improvements: monthly cadence until v0.2.
- Major version bumps: planned against Phase 2 roadmap.

---

## 10. Technical Debt Ledger

Known debt incurred by v0 simplifications, explicitly tracked. Each item has a trigger condition for revisiting.

| Item | Location | Trigger to revisit |
|---|---|---|
| Substring-based entity matching | PRC-012 | First user-reported false-positive or false-negative on real payload → upgrade via PRC-030 |
| Single-file YAML contract loader (no directory conventions, no includes) | PRC-007 | More than 20 contracts in a single user project → add `!include` directive |
| No batch scoring API | PRC-011 | User requests scoring thousands of archived events in a single run → add `score_batch()` |
| Demo runs on fixtures only, not a live LangGraph pipeline | PRC-019 | First complaint that the demo "isn't real" → add optional `--live` mode |
| Observatory is static, renders one trace | PRC-022 | Users submit traces for review → multi-trace mode or hosted instance |
| Impact templates are hand-written Python dict | PRC-015 | Contract count exceeds hand-editable scale (~50) OR non-engineers need to edit impact copy → YAML override layer |
| No checkpointer integration (LangGraph resumability) | PRC-014 | User reports blocked handoffs cannot be resumed after remediation |
| Per-call single-worker `ThreadPoolExecutor` in `evaluate_handoff`'s in-loop branch (no shared/bounded pool; one worker thread created and joined per call) | PRC-014 (`eval_hook._evaluate`) | Real-world report of thread-churn or throughput loss under burst-concurrent async handoffs → replace with a bounded module-level executor (deliberate `max_workers` + shutdown lifecycle) or the Phase 2 native async path (PRC-011b) |
| Embedding proxy model hardcoded to `all-MiniLM-L6-v2` | PRC-011 | Multilingual support requested, or English-bias complaints |
| No caching of embeddings across evaluations | PRC-011 | Performance regression reports on repeat-payload evaluations |
| No scorer benchmarking harness | - | Needed at v0.2 for comparing proxy to calibrated (PRC-036) |
| Decorator frontend sync-only | PRC-008 | User requests async function support → PRC-008b in Phase 2 |
| No native async API on Scorer | PRC-011 | Users complain about `asyncio.to_thread` boilerplate despite the `evaluate_handoff` auto-dispatch → dual sync/async Scorer API in Phase 2 |
| Contracted-field extractor does not recurse into nested objects | PRC-016 | Users need dotted-path field access (e.g., `metadata.source`) → extend extractor with path-expression support |
| No concurrency stress tests on registry | PRC-009 | Real-world report of registry corruption under worker-pool contention → add stress test and verify lock behaviour |
| OTel GenAI schema pinned to experimental version | PRC-020 | Conventions mark stable → migrate and lock to stable version |
| Impact-summary agent names parsed from the `<source>_to_<target>` contract-name convention (first `_to_` is the separator) | PRC-015 | A user contract whose *source* agent name embeds `_to_` mis-attributes the split → carry explicit source/target agent fields on `HandoffContract` or `ViolationEvent` and feed them to `render_impact_text` |

Review this ledger at every minor version bump.

Rev 2 change: added decorator sync-only, no-native-async, extractor-no-recursion, no-concurrency-stress, OTel-experimental items. Removed "no async story" entry (it's now documented behaviour, not debt).

---

## 11. Phase 2 Readiness Assessment

Phase 2 issues (PRC-028 through PRC-036) are labelled and scoped in ISSUES.md but not scheduled. Before picking any up, verify:

- **PRC-028, PRC-029** (research scaffolding, MARL testbed): requires dissertation context and compute budget. Do not start without Prof Treleaven alignment.
- **PRC-030** (NER entity matching): safe to pick up any time after v0.1.0 ships. Small scope.
- **PRC-031, PRC-032, PRC-033** (A2A): depends on A2A spec stability and Precept having enough users to justify the investment.
- **PRC-034, PRC-035, PRC-036** (calibrated scorer): strictly gated on dissertation completion (August 2026 target).

Additional Phase 2 candidates added in Rev 2 from the tech debt ledger:

- **PRC-008b** (async decorator frontend): if user demand materialises.
- **PRC-011b** (native async Scorer API): if the `asyncio.to_thread` pattern proves insufficient.
- **PRC-016b** (nested-path field extraction): if contracts need dotted-path access.

The absence of these items from v0.1.0 is a deliberate design choice.

---

## 12. Document Maintenance

This document is not written once and forgotten. Keep it current.

- Update section 2 (dependency graph) whenever an issue is re-scoped.
- Update section 4 (integration risk register) whenever an upstream dep has a material API change.
- Update section 8 (release checklist) after every release; capture lessons as new items.
- Update section 10 (debt ledger) whenever a v0 simplification is made or retired.
- Section 7 (performance baseline) gets a new row for every new user-visible operation.

At every minor version bump, spend 30 minutes re-reading this file with a red pen. Anything stale, delete. Anything new, add.

---

*End of DEPENDENCIES.md. See [ISSUES.md](./ISSUES.md) for the canonical issue list.*
