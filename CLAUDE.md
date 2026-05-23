# CLAUDE.md

> Operating guide for Claude Code sessions on the Precept repository. Read this end-to-end before starting any ticket.

---

## What Precept is

Python SDK for declaring **handoff integrity contracts** on multi-agent pipelines (LangGraph-first), evaluating boundary payloads against them, and emitting violation events via OTel GenAI semantic conventions.

- **Positioning:** boundary fidelity, not behaviour governance. Tagline: "the policy passes, the information fails."
- **v0 scorer:** embedding-similarity proxy (cosine). **Phase 2 scorer:** research-validated calibrated scorer (MSc dissertation deliverable).
- **Distinct from:** output validators (Guardrails, Pydantic AI), trace observability (Langfuse, LangSmith, Arize, Galileo), behavioural contract tools (agentcontract/spec, relari-ai/agent-contracts), policy governance (Microsoft Agent Governance Toolkit).
- **NOT at v0:** mutual-information measurement (dissertation-gated), A2A protocol, general LLM-eval framework, trace observability replacement.

---

## Authoritative planning documents

**GitHub Issues is the source of truth for the backlog.** The local `ISSUES.md` and `DEPENDENCIES.md` files mirror GH for offline reference and are large (~129 KB and ~38 KB respectively). **Do not read them wholesale** - pull only the slice you need.

If a ticket on GitHub conflicts with this CLAUDE.md, the GH ticket wins for that specific ticket. Raise the conflict explicitly rather than silently picking one.

### Lookup index

Use the narrowest read that answers the question.

| Need | How to get it |
|---|---|
| Active ticket details | `gh issue view <number> --json title,body,labels,state` (PRC-XXX is the title prefix, not the number) |
| Find a ticket by ID | `gh issue list --search "PRC-XXX in:title" --state all --json number,title,state` |
| Open backlog | `gh issue list --state open --limit 50` |
| Recent merges | `git log --oneline -20` |
| Dep graph for a ticket's prerequisites | `grep -n "PRC-XXX" DEPENDENCIES.md` then read that section only |
| Risk register | DEPENDENCIES.md §4 (read just that section) |
| Cross-cutting concerns | DEPENDENCIES.md §5 |
| Release gates | DEPENDENCIES.md §8 |
| Critical-path priorities | DEPENDENCIES.md §1 |
| Architectural constraints | this file, "Critical architectural constraints" section |
| Code style rules | this file, "Code style and architecture" section |
| Offline ticket lookup (no network) | `grep -n "^## PRC-XXX" ISSUES.md` then read that line range only |

---

## Ticket workflow

1. **Pick a ticket.** Fetch it: `gh issue view <number> --json title,body,labels,state`. Confirm its listed dependencies are merged on `main` (cross-check DEPENDENCIES.md §2 only if the listed deps look ambiguous). If a blocker isn't merged, stop and work on the blocker first.
2. **Branch.** Name: `<type>/PRC-XXX-short-slug`. Types: `feat`, `fix`, `docs`, `infra`, `test`, `research`. Example: `feat/PRC-011-embedding-proxy`.
3. **Scope discipline.** Do exactly what the Acceptance Criteria list, nothing more. If you identify scope creep temptation mid-ticket (e.g., "while I'm here, let me also fix..."), write it as a follow-up issue - do not pull it into the current PR.
4. **Tests alongside code.** Every acceptance-criteria test listed in "Testing Requirements" must be written and passing before the PR opens.
5. **Commit style.** Conventional Commits. Example: `feat(scoring): add EmbeddingProxy v0 with constructor-time model load (PRC-011)`. Include the ticket ID in the body if not in the title.
6. **PR title.** `PRC-XXX: <one-line summary>`. PR body: Summary, Linked issue, Testing, Checklist (tests pass, types check, lint clean, CHANGELOG updated).
7. **CHANGELOG.md.** Update the `[Unreleased]` section under the appropriate category (Added, Changed, Deprecated, Removed, Fixed, Security). Every user-visible change gets an entry.
8. **Definition of Done is a gate.** Do not mark the ticket done until every DoD item is verified. "Tests pass" means "pytest exits 0 locally AND CI is green".

---

## Code style and architecture

### When to use classes vs functions

Use OOP when: (1) a component holds injected dependencies or mutable state (`Evaluator`, `ContractRegistry`), (2) multiple concrete implementations share a stable interface (`Scorer` ABC), or (3) you need lifecycle methods. Use module-level functions when logic is stateless and composable (`rules.py`, loaders). Prefer Pydantic models over dataclasses for all data-carrying types. Never create a class just to namespace functions - use a module for that.

### Concrete application in this repo

| Component | Class or function? | Reason |
|---|---|---|
| `HandoffContract`, `ViolationEvent`, `ScoreResult`, `HandoffPayload`, `FieldScore`, `RuleResult` | Pydantic model | Data-carrying types; validation; `model_dump` for serialisation. |
| `Scorer`, `Exporter` | ABC | Multiple concretes sharing a stable interface. |
| `EmbeddingProxy`, `CalibratedScorer` (stub) | Class inheriting ABC | Holds model state. |
| `NoOpExporter`, `MultiExporter`, `JSONFileExporter`, `OTelExporter` | Class inheriting ABC | Holds transport state. |
| `Evaluator` | Class | Holds injected `Scorer` and `Exporter`. |
| `ContractRegistry` | Class | Holds mutable dict + `threading.Lock`. |
| `required_fields_rule`, `preserved_entities_rule`, `forbidden_drops_rule` | Module-level function | Pure; no state; composable. |
| `load_contract`, `load_contract_from_string` | Module-level function | Stateless YAML → IR transform. |
| `handoff_contract` | Module-level function (decorator) | Stateless metadata attachment. |
| `extract_payload` | Module-level function | Stateless state → payload transform. |
| `populate_impact_summary`, `render_impact_text` | Module-level function | Pure templating. |

### Pydantic conventions

- Pydantic v2 only. Use `ConfigDict`, `field_validator`, `model_dump`, `model_validate`.
- All data-carrying types get `model_config = ConfigDict(extra="forbid")` unless there's an explicit reason to allow extras.
- Never use dataclasses for data that will cross module boundaries. Pydantic wins on validation, serialisation, and schema export.
- `from __future__ import annotations` at the top of every module.

### Type discipline

- `mypy --strict` is mandatory. CI will reject PRs that fail it.
- No `Any` in public function signatures unless the type is genuinely polymorphic (payload field values are the only legitimate case).
- Prefer `typing.Protocol` over `typing.Callable` for callbacks with more than one method.
- Use `typing.Literal` for enum-like string parameters (e.g., `mode: Literal["block", "warn"]`).

### Public API surface

- Everything importable as `from precept import X` is a semver commitment. PRC-026 defines the exact `__all__`; do not add to it without reviewing that ticket.
- Internal modules do NOT use a leading underscore on filenames (Python's convention of `_internal.py` is noisy); rely on `__all__` discipline and documentation instead.
- `OTelExporter` is NEVER exported from the top-level namespace. Users import via `from precept.exporters.otel import OTelExporter`. This is so base-install users without the `[otel]` extra do not trigger an ImportError.

### Error handling

- Raise only Precept-specific exceptions from the public API: `ContractValidationError`, `HandoffBlockedError`. Wrap and re-raise third-party exceptions (e.g., `pydantic.ValidationError`) at the module boundary.
- Exporter implementations MUST swallow transport errors (log + continue). An evaluator call should never fail because OTel is misconfigured.
- On missing contract in `evaluate_handoff`: log WARNING, do NOT raise, do NOT emit an event. This is fail-open behaviour. Document it loudly in the calling module.
- Never use bare `except:` or `except Exception:`. Catch specific exception types.

### Logging

- Module-level loggers only: `logger = logging.getLogger(__name__)`.
- DEBUG for per-evaluation trace detail; INFO for lifecycle events (contract registration, model load); WARNING for fail-open degraded modes; never ERROR (errors are exceptions or `ViolationEvent`s, not log lines).
- Never log payload content at INFO or above.
- Library code never configures handlers. The user's application owns `logging.config`.

### Naming

- UK spelling is NOT used in code identifiers (Python convention is US: `color`, `serialize`). UK spelling IS used in docstrings, comments, markdown, and user-facing strings, per repo convention.
- Classes: PascalCase. Functions/variables: snake_case. Constants: UPPER_SNAKE_CASE. Private helpers: `_leading_underscore`.
- Module names: lowercase, short, no underscores unless needed (`schema.py` not `contract_schema.py` - the directory gives context).

### Implementation discipline

- **Surface assumptions before coding.** If a request admits multiple reasonable interpretations, name them and ask - do not pick silently. Ambiguity hidden upfront becomes rework at review.
- **Minimum code that satisfies the Acceptance Criteria.** No speculative abstractions, no configurability nobody asked for, no error paths for states that cannot occur. If a 200-line diff could be 50, rewrite it.
- **Surgical edits.** When modifying existing code, touch only what the change requires. Do not reformat adjacent code, do not refactor working code, do not delete pre-existing dead code (flag it in the PR description instead). Every changed line should trace to the ticket.
- **Orphan cleanup is yours; pre-existing cruft is not.** Remove imports, variables, and symbols that YOUR change leaves unused. Leave unrelated dead code alone unless the ticket scope covers it.

---

## Toolchain

### Python

- Python >= 3.10 required. Use match statements, PEP 604 union syntax (`int | None`), and other 3.10+ features freely.
- Target testing matrix: 3.10, 3.11, 3.12 on Ubuntu. macOS tested manually for release.

### Package management

- `pip install -e .[dev]` for dev environment. Do NOT commit venv directories.
- A `requirements-dev.lock` file exists for reproducible CI environments. Regenerate it via `pip-compile pyproject.toml --extra dev -o requirements-dev.lock` when deps change.
- Never add a runtime dependency without filing a GH issue (deps analysis criteria in DEPENDENCIES.md §3) AND getting explicit approval.

### Lint, format, type

- `ruff check .` for linting. `ruff format .` for formatting. **`black` is NOT used** - `ruff format` is its drop-in replacement. Installing black would create a dual-formatter conflict.
- `mypy --strict src/precept` for type checking.
- `bandit -r src/precept -ll` for security scanning.
- `pip-audit` for supply-chain CVE scanning (runs weekly via scheduled GH Action).
- `pre-commit install` on first clone. Hooks auto-run on commit; never bypass with `--no-verify`.

### Testing

- `pytest` with coverage: `pytest --cov=src/precept --cov-report=term-missing`.
- Test layout mirrors source layout: `src/precept/scoring/embedding_proxy.py` → `tests/unit/scoring/test_embedding_proxy.py`.
- Three tiers:
  - `tests/unit/` - no I/O, single module, runs in < 30s total, executed on every commit.
  - `tests/integration/` - exercises multiple modules together, may take 1-3 minutes, runs on every PR.
  - `tests/e2e/` (if added) - real LangGraph + LLM calls, manual runs only.
- Property-based tests via `hypothesis` for input validation logic (contract schema, rules, extractor). Property tests find edge cases example-based tests miss - use them.
- Coverage gate: ≥ 80% on `src/precept/contract/` and `src/precept/scoring/`. Do not chase 100%; chasing the last 20% typically tests boilerplate.

---

## Critical architectural constraints

### IR-first contract architecture
- Single source of truth: `HandoffContract` Pydantic model.
- Both the YAML loader AND the decorator frontend produce `HandoffContract` instances; the evaluator consumes only `HandoffContract`.
- **Never add frontend-specific fields to the evaluator.** A future frontend (JSON, A2A, TOML) drops in as a new parser module without touching the engine.

### Scorer stays generic
- The `Scorer` ABC docstring must NEVER reference "mutual information". MI is one of four candidate methods (KSG, Gaussian closed-form, InfoNCE, MINE) the dissertation will evaluate; the interface must not over-commit before research validates one.
- v0 concrete: `EmbeddingProxy` (embedding cosine). Phase 2 concrete: `CalibratedScorer`.
- Do NOT name the Phase 2 class `MIScorer`.

### Two integration paths for LangGraph
- PRC-014 ships BOTH `create_precept_handoff_tool` (wraps `langgraph_supervisor.create_handoff_tool`) AND `evaluate_handoff()` (pure function for `Command(goto=...)` users).
- Do NOT collapse into one path. Pure function = framework-API-independent fallback; tool wrapper = convenience on top.

### Contracted-fields-only extraction
- `extract_payload()` (PRC-016) reads ONLY fields named in the contract. **Never recurse into uncontracted state.**
- This is the primary defence against leaking secrets from state into events/exporters. A regression test enforces it; do NOT relax.

### Constructor-time model load
- `EmbeddingProxy` loads its sentence-transformer model in `__init__`, NOT lazily on first `score()`.
- Moves the ~5 s first-run cost to application startup; avoids blocking the asyncio loop mid-handoff.
- Do NOT "optimise" this back to lazy loading.

### 4 KiB event payload ceiling
- `ViolationEvent.to_compact_dict()` enforces 4 KiB total with progressive truncation; OTel exporter has a secondary per-attribute check.
- 4 KiB is the realistic OTel-backend lower bound (Datadog, Jaeger). Larger events get silently dropped, which breaks Precept's value prop.
- Do NOT relax without a backend-specific justification.

### Async safety
- `evaluate_handoff()` auto-detects a running asyncio loop via `asyncio.get_running_loop()` and dispatches the sync `Scorer.score()` to `asyncio.to_thread()`.
- This lets the sync Scorer API coexist with async LangGraph nodes without blocking.
- Do NOT add a separate async Scorer API; the wrapper is sufficient for v0.

### Fail-open on missing contract
- If `evaluate_handoff` is called with a contract name not in the registry: log WARNING, return a synthetic pass event. Do NOT raise.
- Rationale: observability that crashes the pipeline is worse than observability that silently misses a check.
- Document this behaviour prominently wherever it's invoked.

---

## Things to never do

1. **Never add a runtime dependency** without updating `pyproject.toml`, regenerating `requirements-dev.lock`, AND updating DEPENDENCIES.md section 3.
2. **Never use `yaml.load`.** Use `yaml.safe_load` exclusively. `yaml.load` is a remote code execution surface.
3. **Never use `pickle`** anywhere in the codebase.
4. **Never use `eval`, `exec`, or `compile`** on user-provided data.
5. **Never commit credentials, tokens, or API keys** - even in test fixtures. Use `os.environ` or `pytest.fixture`-provided mocks.
6. **Never write to or read from `/tmp` without using `tempfile`.** Race conditions and cleanup issues are guaranteed otherwise.
7. **Never configure loggers at import time** from within the library. That's the user's application's job.
8. **Never raise generic `Exception`** from public API - always use Precept-specific subclasses.
9. **Never mark a ticket Done without verifying every Definition-of-Done item.** "Almost done" is not done.
10. **Never bypass pre-commit or CI** with `--no-verify`, `[skip ci]`, or equivalent. If a hook fails, fix the underlying issue.
11. **Never push to any remote and never open pull requests.** Commit locally on the feature branch and stop. All pushes and PR creation are reserved for the human maintainer; offering to push is also out of scope.
12. **Never claim the proxy scorer measures mutual information.** It is a cosine-similarity proxy. The README, docstrings, and marketing must say so honestly.
13. **Never rename a public API entry from `__all__` between patch versions.** Semantic versioning applies from v0.1.0 onward.

---

## Things to always do

1. **Always read the ticket end-to-end** before starting work. Acceptance criteria + testing requirements are the checklist.
2. **Always check the ticket's listed prerequisites are merged.** Cross-check DEPENDENCIES.md §2 only if the ticket's dep list looks incomplete or ambiguous.
3. **Always write tests first or alongside code**, never after. PRs with implementation and no tests get bounced.
4. **Always run `ruff check . && ruff format --check . && mypy --strict src/precept && pytest` locally** before pushing.
5. **Always update CHANGELOG.md** for user-visible changes, under `[Unreleased]` in the appropriate section.
6. **Always pin external dependencies** with both floor AND upper bound (e.g., `pydantic>=2.5,<3`).
7. **Always document fail-open / degraded modes loudly** in docstrings and README, never silently.
8. **Always wrap third-party exceptions** at module boundaries; re-raise as Precept-specific.
9. **Always use `from __future__ import annotations`** at the top of every Python module.
10. **Always prefer composition over inheritance** - the ABCs are for interface contracts, not code reuse. Use helpers/mixins only when a real pattern emerges across 3+ concrete classes.

---

## Release discipline

### Version bumping
- Pre-1.0 minor bumps (0.1 → 0.2) MAY contain breaking changes, only with a CHANGELOG migration note.
- Post-1.0, breaking changes are major bumps only.
- Patch bumps (0.1.0 → 0.1.1) are strictly additive or bug-fix only.

### Before tagging a release
- Consult DEPENDENCIES.md §8 (Release Readiness Checklist). Every gate must be green.
- Timeline does not override quality: a release delayed 24h for a failing gate beats shipping broken.

### Release mechanics
- PyPI + TestPyPI OIDC trusted publishers pre-configured (PRC-004a). Release workflow (`release.yml`) fires on tag push matching `v*.*.*`.
- Dry-run to TestPyPI via `release-testpypi.yml` (`workflow_dispatch`) before tagging.
- Rollback runbook: `docs/release_process.md`. Know it before a release; do not learn it mid-incident.

---

## Scope boundaries (Phase 2 items)

Do not add Phase 2 work to MVP PRs. These are explicitly deferred and labelled P2 in ISSUES.md:

- Mutual-information-theoretic scoring (post-dissertation, Aug 2026+)
- A2A protocol compatibility (PRC-031 to PRC-033)
- Research folder scaffolding with full literature map + testbed (PRC-028 to PRC-030)
- OpenAI Agents SDK `input_filter` integration
- Claude Agent SDK `Agent` tool integration
- NER-based entity matching (substring is v0)
- Native async Scorer API (`asyncio.to_thread` shim is v0)
- Async decorator support
- Nested-path field extraction in contracts
- LangGraph checkpointer integration for resumable violations
- Multilingual / non-English embedding models
- Hosted observatory app (static HTML is v0)

If a user request or emergent need implies one of these, open an issue against the relevant P2 ticket number rather than pulling it into a current PR.

---

## When in doubt

1. Re-fetch the ticket: `gh issue view <number>`. Acceptance Criteria + Testing Requirements answer most "should I do X?" questions.
2. Grep the relevant section of DEPENDENCIES.md (§4 risks, §5 cross-cutting). Do NOT read it wholesale.
3. If still unclear, ask in the PR description or pin the question at the top of a draft PR. Do not guess on architectural decisions.
4. For anything marked P0 on the critical path (DEPENDENCIES.md §1), err heavily on the side of caution and explicit clarification.

---

*End of CLAUDE.md. Keep this file current as the repo evolves; stale operating guides are worse than no guide at all.*
