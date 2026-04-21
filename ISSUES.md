# Precept v0.1.0 - Implementation Backlog

> Handoff integrity contracts for multi-agent pipelines. LangGraph-first MVP. Target ~10 days; the release gate is production quality, not the calendar.

---

## Overview

This document is the canonical engineering backlog for Precept v0.1.0. The scope is a working open-source Python SDK that lets developers declare handoff integrity contracts for LangGraph multi-agent pipelines, evaluate boundary payloads against those contracts using a v0 embedding-based proxy scorer, and emit violation events via OpenTelemetry GenAI semantic conventions. A static HTML observatory renders a canned demo trace for reviewers.

The MVP deliberately defers: mutual-information-theoretic scoring (validated post-dissertation, Phase 2), A2A protocol compatibility (Phase 2), research folder scaffolding (Phase 2), and additional framework adapters beyond LangGraph (Phase 2).

**Timeline philosophy.** The 10-day target is aggressive but achievable for a focused single engineer. If a P0 ticket reveals deeper-than-estimated complexity (LangGraph API churn, OTel spec drift, scorer-determinism issues), the response is to extend the timeline, not to ship a degraded surface. Accelerator deadlines do not override release exit criteria (section at end of this document). A v0.1.0 that ships on day 12 and works robustly is a stronger signal than a v0.1.0 that ships on day 10 and embarrasses on first run.

**Changes since first draft.** This document has been revised to address feedback on production-readiness gaps. Material changes: (1) `HandoffBlockedError` class moved from PRC-015 to PRC-013 to remove a circular dependency with PRC-014. (2) PRC-016 narrowed from full LangGraph state serialiser to a focused contracted-field extractor (security and performance win). (3) PRC-014 now provides two integration paths - `create_precept_handoff_tool` for tool-based supervisors AND `evaluate_handoff()` pure function for `Command(goto=...)` pattern users. (4) `EmbeddingProxy` model loaded in constructor, not lazily, to avoid blocking async event loops on first call. (5) PRC-013 now defines the `Exporter` ABC alongside `ViolationEvent` and enforces a 4KB payload-size ceiling. (6) PRC-026 OTelExporter is lazily imported and not re-exported from top-level. (7) Sprint 0 picks up a TestPyPI OIDC publisher setup sub-task. (8) Toolchain consolidation: `ruff format` replaces `black`; `black` removed from dev deps and pre-commit. (9) PRC-008 scoped to sync decorators only; async support deferred. (10) PRC-019 exit code follows Unix convention (0 on success, regardless of violations).

---

## Conventions

### Priority
- **P0**: MVP-critical. Blocks v0.1.0 release.
- **P1**: MVP-important. Target for v0.1.0 but not release-blocking.
- **P2**: Phase 2. Deferred past MVP. Labelled but not scheduled.

### Effort sizing
- **S**: ≤4 hours
- **M**: 4-8 hours (half day to one day)
- **L**: 8-16 hours (1-2 days)
- **XL**: >16 hours. Re-split before picking up.

### Issue type
- `feat`: feature
- `infra`: build, CI, packaging, tooling
- `docs`: documentation
- `test`: test coverage expansion
- `research`: exploration / design study

### Sprint map
| Sprint | Days | Theme |
|---|---|---|
| Sprint 0 | Day 0 | Foundation (repo, CI, packaging) |
| Sprint 1 | Days 1-3 | Contract + Scoring Engine |
| Sprint 2 | Days 4-6 | LangGraph Integration + Demo |
| Sprint 3 | Days 7-8 | Telemetry Exporters + Observatory |
| Sprint 4 | Days 9-10 | Documentation + Release |
| Phase 2 | Post-release | Deferred research, A2A, calibrated scorer |

### Python / stack baseline
- Python >= 3.10 (modern typing, match statements)
- Primary deps: `pydantic>=2`, `pyyaml`, `sentence-transformers`, `numpy`, `opentelemetry-api`, `langgraph`, `langchain-core`
- Optional deps via extras: `precept[otel]` adds `opentelemetry-sdk`
- Dev deps: `pytest`, `pytest-cov`, `hypothesis`, `mypy`, `ruff` (lint + format), `bandit`, `pip-audit`, `pre-commit`
- Packaging: `pyproject.toml` (PEP 621), `setuptools` backend
- Tests: pytest with coverage target 80%+ on `precept/contract/` and `precept/scoring/`
- Toolchain note: `ruff format` is used as the formatter (drop-in `black` replacement). No separate `black` install. This avoids dual-formatter conflicts and reduces hook latency.

---

## Epic Map

| Epic | ID range | Priority | Sprint | Issues |
|---|---|---|---|---|
| E1. Repository & Build Foundation | PRC-001 to PRC-004, PRC-002a, PRC-004a | P0 (PRC-002a P2) | Sprint 0 / pre-release | 6 |
| E2. Contract Specification Layer | PRC-005 to PRC-009 | P0 | Sprint 1 | 5 |
| E3. Scoring & Evaluation Engine | PRC-010 to PRC-013 | P0 | Sprint 1 | 4 |
| E4. LangGraph Integration | PRC-014 to PRC-016 | P0 | Sprint 2 | 3 |
| E5. Demo Pipeline & Fixtures | PRC-017 to PRC-019 | P0 | Sprint 2 | 3 |
| E6. Telemetry Exporters | PRC-020 to PRC-021 | P1 | Sprint 3 | 2 |
| E7. Static Observatory | PRC-022 to PRC-023 | P1 | Sprint 3 | 2 |
| E8. Documentation & Release | PRC-024 to PRC-027 | P0/P1 | Sprint 4 | 4 |
| E9. Phase 2 - Research Scaffolding | PRC-028 to PRC-030 | P2 | Deferred | 3 |
| E10. Phase 2 - A2A Compatibility | PRC-031 to PRC-033 | P2 | Deferred | 3 |
| E11. Phase 2 - Calibrated Scorer Integration | PRC-034 to PRC-036 | P2 | Deferred | 3 |

**Total: 38 issues. MVP scope: 28 issues (PRC-001 to PRC-027 + PRC-004a). Pre-public-release gate: PRC-002a. Phase 2: 9 issues (PRC-028 to PRC-036).**

---

## Target Package Structure

```
precept/
├── pyproject.toml
├── LICENSE
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── .github/
│   ├── workflows/
│   │   └── ci.yml
│   └── ISSUE_TEMPLATE/
├── src/
│   └── precept/
│       ├── __init__.py
│       ├── contract/
│       │   ├── __init__.py
│       │   ├── schema.py         # Pydantic IR
│       │   ├── yaml_loader.py    # YAML frontend
│       │   └── decorator.py      # Decorator frontend
│       ├── scoring/
│       │   ├── __init__.py
│       │   ├── base.py           # Scorer ABC, ScoreResult
│       │   ├── embedding_proxy.py
│       │   └── calibrated.py     # Phase 2 stub
│       ├── evaluator/
│       │   ├── __init__.py
│       │   ├── engine.py         # Evaluates a payload against a contract
│       │   └── rules.py          # Per-field rule implementations
│       ├── integrations/
│       │   ├── __init__.py
│       │   └── langgraph/
│       │       ├── __init__.py
│       │       └── handoff_tool.py
│       ├── exporters/
│       │   ├── __init__.py
│       │   ├── otel.py
│       │   └── json_exporter.py
│       ├── types.py              # HandoffPayload, ViolationEvent, etc.
│       └── errors.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── examples/
│   ├── demo.py                   # 3-hop pipeline demo runner
│   ├── contracts/
│   │   ├── researcher_to_summariser.yaml
│   │   └── summariser_to_writer.yaml
│   └── fixtures/
│       ├── clean_trace.json
│       └── degraded_trace.json
├── docs/
│   ├── index.html                # Observatory static site
│   ├── architecture.md
│   ├── contract_reference.md
│   └── competitive_landscape.md
└── Research/                     # Phase 2 scaffold, initially a README pointer
    └── README.md
```

---

# Sprint 0: Foundation

---

## PRC-001: Initialise repository scaffolding and package metadata

**Epic:** E1. Repository & Build Foundation
**Type:** infra
**Priority:** P0
**Effort:** S (2-3h)
**Sprint:** 0
**Dependencies:** none

### Context
The repository currently contains `Dev/`, `Research/`, `LICENSE`, and a README. We need a proper Python package structure, `pyproject.toml` configured for PEP 621 metadata, a minimum-viable `README.md` stub (full version lands in PRC-024), and a clean `.gitignore`. This is the foundation every subsequent ticket builds on.

### Acceptance Criteria
- [ ] `pyproject.toml` with PEP 621 metadata: name (`precept`), version (`0.0.1` initial), description, authors, licence (MIT), Python requirement (`>=3.10`), classifiers, `project.urls`
- [ ] Build backend: `setuptools.build_meta` with `tool.setuptools.packages.find` rooted at `src/`
- [ ] Dependency groups: `[project.dependencies]` for runtime deps, `[project.optional-dependencies]` with `dev`, `test`, `docs` extras
- [ ] `src/precept/__init__.py` with `__version__` string synced with pyproject
- [ ] `.gitignore` covering Python (`__pycache__`, `.pyc`, `.venv`, `dist/`, `build/`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `*.egg-info`), IDE (`.idea/`, `.vscode/`), and OS (`.DS_Store`) artefacts
- [ ] `CHANGELOG.md` with `[Unreleased]` section using Keep a Changelog format
- [ ] Package installable locally: `pip install -e .` succeeds and `import precept; precept.__version__` returns the expected string

### Technical Notes
- Prefer `src/` layout over flat layout: prevents accidental import of the source directory during test runs and is the current Python packaging best practice (PEP 517/518).
- Pin dependency versions with floor-only constraints (e.g., `pydantic>=2.5,<3`) to allow security updates while preventing major-version breakage.
- Do not add `__all__` to `__init__.py` yet; defer public API surface decisions to PRC-027.

### Testing Requirements
- Manual verification: `pip install -e .[dev]` succeeds on a fresh virtualenv
- Manual verification: `python -c "import precept; print(precept.__version__)"` prints the expected version

### Out of Scope
- Full README content (PRC-024)
- CI workflow (PRC-003)
- Pre-commit hooks (PRC-004)

### Definition of Done
- Branch merged to `main`
- Local install works on macOS (ARM64) and Linux (x86_64)
- CHANGELOG entry added under `[Unreleased]`

---

## PRC-002: Contributing guide, licence headers, and code of conduct

**Epic:** E1. Repository & Build Foundation
**Type:** docs
**Priority:** P1
**Effort:** S (2h)
**Sprint:** 0
**Dependencies:** PRC-001

### Context
Open-source projects that show up for accelerator review need a baseline of community hygiene files. These signal that the project is maintained, not a throwaway. Low effort, high signal.

### Acceptance Criteria
- [ ] `CONTRIBUTING.md` covering: dev setup (`pip install -e .[dev]`, `pre-commit install`), branch naming convention (`feat/`, `fix/`, `docs/`, `chore/`), commit message conventions (Conventional Commits), PR template reference, local test/lint/type-check commands
- [ ] `CODE_OF_CONDUCT.md` using Contributor Covenant v2.1 verbatim with contact email filled in
- [ ] `.github/PULL_REQUEST_TEMPLATE.md` with sections: Summary, Linked issue, Testing, Checklist (tests pass, types check, lint clean, CHANGELOG updated)
- [ ] `.github/ISSUE_TEMPLATE/bug_report.md` and `feature_request.md`
- [ ] All source files carry a minimal SPDX header comment: `# SPDX-License-Identifier: MIT`
- [ ] `LICENSE` file confirmed as MIT (already present in repo); verify copyright line is current year

### Technical Notes
- Conventional Commits is chosen over Angular format because it is tooling-compatible with `release-please` and `semantic-release` if future release automation is added.
- Keep CONTRIBUTING.md under 150 lines; link to `docs/architecture.md` for deep-dive content.

### Testing Requirements
- Manual: open every linked file and verify no broken links
- Manual: verify PR template renders correctly by opening a test PR on a fork

### Out of Scope
- Governance document (not needed at this stage)
- Security policy (`SECURITY.md`) - defer until first external user

### Definition of Done
- Files merged, visible on GitHub repo landing page
- `CODE_OF_CONDUCT.md` has a real reporting contact, not `[INSERT EMAIL]` *(deferred to PRC-002a - see below)*

---

## PRC-002a: CODE_OF_CONDUCT.md and public reporting contact

**Epic:** E1. Repository & Build Foundation
**Type:** docs
**Priority:** P2 (pre-public-release gate; does not block MVP development)
**Effort:** S (1-2h)
**Sprint:** pre-1.0 release
**Dependencies:** PRC-002

### Context
PRC-002 intentionally deferred two items: the full `CODE_OF_CONDUCT.md` body and the real reporting-contact address. Both are required for a public open-source project but not for internal / solo MVP development. Once an email address is committed to a public repo, git history retains it forever, so the decision is parked until a public contact channel (project alias, forwarding address, or GitHub's private reporting flow) is chosen.

### Acceptance Criteria
- [ ] `CODE_OF_CONDUCT.md` at repo root, Contributor Covenant v2.1 verbatim
- [ ] Real reporting contact filled into the enforcement section - no placeholder
- [ ] `README.md` links to `CODE_OF_CONDUCT.md` from a "Community" / "Code of Conduct" section
- [ ] PRC-002 DoD's open item closed (it referred explicitly to this file)
- [ ] `Dev/CHANGELOG.md` entry under the appropriate pre-release version

### Technical Notes
- Contributor Covenant v2.1 source: <https://www.contributor-covenant.org/version/2/1/code_of_conduct/>
- Prefer a project alias (e.g., `conduct@<domain>`) over a personal email; aliases can be rotated, committed emails cannot be retracted from git history
- Evaluate GitHub's community / private reporting flows as a substitute before committing to an email
- Update `DEPENDENCIES.md` §8 (Release Readiness Checklist) if this gate is tracked there

### Testing Requirements
- Manual: confirm the chosen contact channel actually receives mail / routes to a human

### Out of Scope
- `SECURITY.md` (security vulnerability reporting - separate ticket if/when needed)
- Governance document

### Definition of Done
- File merged, README links to it, real contact in place and functional
- No `[INSERT EMAIL]` or equivalent placeholder anywhere in the repo

---

## PRC-003: Continuous integration pipeline (GitHub Actions)

**Epic:** E1. Repository & Build Foundation
**Type:** infra
**Priority:** P0
**Effort:** M (4-6h)
**Sprint:** 0
**Dependencies:** PRC-001

### Context
Every PR must pass lint, type-check, and tests before merge. Without CI from day one, tech debt accumulates silently. The pipeline also produces evidence (green checks) that the project is maintained and testable - material for both developer trust and accelerator review.

### Acceptance Criteria
- [ ] `.github/workflows/ci.yml` triggered on `push` to `main` and on all `pull_request` events
- [ ] Matrix: Python versions `["3.10", "3.11", "3.12"]` on `ubuntu-latest` (macOS matrix deferred until cross-platform issues appear)
- [ ] Jobs (run in parallel where possible):
  - `lint`: runs `ruff check .` and `ruff format --check .`
  - `typecheck`: runs `mypy --strict src/precept`
  - `security`: runs `bandit -r src/precept -ll`
  - `test`: runs `pytest --cov=src/precept --cov-report=xml --cov-report=term-missing`, uploads coverage to job artefact
- [ ] Cache: `actions/setup-python` with `cache: 'pip'` keyed on `pyproject.toml` hash
- [ ] Branch protection rule (configured in GitHub UI, documented in CONTRIBUTING.md): all jobs required, at least one approving review, linear history required
- [ ] README badge: CI status badge visible at top of README

### Technical Notes
- Do not add Codecov until the project is stable. Codecov adds a failure surface (token management, rate limits, their own outages) without adding much at this stage. Coverage reports are uploaded as job artefacts and readable directly in the GitHub Actions UI.
- Use `actions/checkout@v4` and `actions/setup-python@v5` (latest stable as of 2026).
- Keep `mypy --strict` from day one. Retrofitting strict typing is expensive; starting strict keeps it cheap.

### Testing Requirements
- Verify CI passes on an empty PR that only touches `.github/workflows/ci.yml`
- Intentionally introduce a lint error in a throwaway branch to confirm the `lint` job catches it
- Intentionally introduce a type error to confirm `typecheck` catches it

### Out of Scope
- Release automation (PRC-027)
- PyPI publish step (PRC-027)
- Documentation build CI (PRC-023 uses GitHub Pages directly)

### Definition of Done
- All four jobs pass on a clean `main`
- Branch protection enforced and documented
- CI badge visible in README

---

## PRC-004: Pre-commit hooks and local developer tooling

**Epic:** E1. Repository & Build Foundation
**Type:** infra
**Priority:** P1
**Effort:** S (2h)
**Sprint:** 0
**Dependencies:** PRC-001

### Context
Pre-commit hooks catch lint and type errors before the CI pipeline runs, which saves developer time and CI minutes. They also enforce consistent file hygiene (trailing whitespace, end-of-file newlines, YAML/JSON validity). PRC-003 (CI) is not a dependency - hooks operate purely against local repo state.

### Acceptance Criteria
- [ ] `.pre-commit-config.yaml` with hooks: `trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-toml`, `check-merge-conflict`, `detect-private-key`, `ruff` (linting), `ruff-format` (formatting), `mypy` (scoped to `src/precept`)
- [ ] Hook versions pinned to specific revs (not `master`) for reproducibility
- [ ] CONTRIBUTING.md references `pre-commit install` in the setup steps
- [ ] Running `pre-commit run --all-files` on a clean repo passes

### Technical Notes
- `ruff` replaces both `flake8` and `isort`. `ruff-format` replaces `black`. Single tool for lint + format reduces install time and eliminates dual-formatter conflicts.
- `mypy` hook must use local install (`language: system`, `entry: mypy`) rather than the mirrored repo to ensure it uses the project's exact pinned version and sees project deps.

### Testing Requirements
- Manual: run `pre-commit run --all-files` and confirm it passes
- Manual: intentionally add trailing whitespace, run `pre-commit run`, confirm it is caught and auto-fixed

### Out of Scope
- Commit message linting (`commitizen`) - nice to have, not MVP-critical

### Definition of Done
- Hooks install cleanly, run cleanly, documented in CONTRIBUTING.md

---

## PRC-004a: PyPI and TestPyPI trusted publisher (OIDC) configuration

**Epic:** E1. Repository & Build Foundation
**Type:** infra
**Priority:** P0
**Effort:** S (2-3h)
**Sprint:** 0
**Dependencies:** PRC-001

### Context
PyPI's trusted publishing (OIDC) is the modern, secure way to publish from GitHub Actions without long-lived API tokens. Both real PyPI and TestPyPI require independent trusted-publisher configuration; setting them up at release time (PRC-027) means the day-10 release workflow fails on first invocation. Configure both in Sprint 0 so the release workflow has a working path on day 10 with zero new infrastructure setup.

### Acceptance Criteria
- [ ] PyPI account created for the `precept` project name (reserve the name; do not publish v0 yet)
- [ ] TestPyPI account created for `precept`
- [ ] Trusted publisher configured on PyPI: GitHub repo, workflow filename (`release.yml`), environment name (`pypi`)
- [ ] Trusted publisher configured on TestPyPI: same repo and workflow, environment name (`testpypi`)
- [ ] Two GitHub Actions environments created: `pypi` (with required reviewer protection) and `testpypi` (no protection, used for release dry-runs)
- [ ] `docs/release_process.md` documents the configuration with screenshots/links so a future maintainer can reproduce
- [ ] Smoke test: a throwaway pre-release version (e.g., `0.0.1.dev0`) published to TestPyPI via a manually-triggered workflow_dispatch job, confirming the OIDC trust works end-to-end
- [ ] Throwaway version YANKED from TestPyPI after smoke test passes (do not pollute the namespace)

### Technical Notes
- Trusted publisher setup requires the GitHub repo to be PUBLIC at the time of configuration (PyPI checks repo visibility). If repo is private, use API token publishing as a fallback for v0.1.0 and migrate to trusted publisher when going public.
- Environment-based gating means `pypi` deploys can require a reviewer approval click before the upload step runs. Configure this; it is the cheapest defence against accidental releases.
- Reserve the project name early. PyPI namespace squatting is a real risk; even if v0 ships in 10 days, claim the name on day 0.

### Testing Requirements
- Smoke test: workflow_dispatch publishes `0.0.1.dev0` to TestPyPI, package installs in a fresh venv via `pip install -i https://test.pypi.org/simple/ precept==0.0.1.dev0`, then yanked
- Manual: confirm both PyPI and TestPyPI projects exist and trusted publisher is listed in project settings

### Out of Scope
- Real v0.1.0 release (PRC-027)
- Sigstore signing (Phase 2)

### Definition of Done
- Both publishers configured, smoke test passes, throwaway version yanked, documented

---

# Sprint 1: Contract Specification Layer + Scoring Engine

---

## PRC-005: Architecture decision record - contract IR with multiple frontends

**Epic:** E2. Contract Specification Layer
**Type:** docs
**Priority:** P0
**Effort:** S (2h)
**Sprint:** 1
**Dependencies:** PRC-001

### Context
The MVP supports both YAML and decorator-based contract declarations. These must not be two parallel implementations that will drift apart. Instead, both are frontends producing the same intermediate representation (IR): a Pydantic `HandoffContract` model. Adding a third frontend in future (JSON, A2A extension, TOML) becomes a parser module, not an engine rewrite. This architectural constraint must be captured before implementation begins.

### Acceptance Criteria
- [ ] `docs/architecture.md` (or ADR file `docs/adr/0001-contract-ir.md`) documenting:
  - Problem: how to support multiple contract declaration surfaces without duplication
  - Decision: single Pydantic IR (`HandoffContract`), multiple parser modules produce IR instances, evaluator consumes IR only
  - Diagram (ASCII or mermaid) showing: YAML file / decorator args / [future: A2A extension] → `HandoffContract` IR → Evaluator
  - Explicit non-goals: no runtime code generation, no dynamic schema extension at v0
  - Consequences: adding a new frontend is additive, not a rewrite; evaluator is unit-testable in isolation from parsers
- [ ] ADR linked from README and from CONTRIBUTING.md

### Technical Notes
- Writing the ADR before PRC-006 and PRC-008 is deliberate: it prevents the YAML and decorator implementations from drifting into parallel stacks during implementation.
- Use [MADR](https://adr.github.io/madr/) format lightly. Full heavyweight MADR is overkill for a v0 tool; a 1-page file with Problem/Decision/Consequences is sufficient.

### Testing Requirements
- Documentation review only

### Out of Scope
- A2A frontend implementation (PRC-032)
- Runtime schema extension / plugin mechanism

### Definition of Done
- ADR merged, linked from README and CONTRIBUTING.md

---

## PRC-006: HandoffContract Pydantic schema (intermediate representation)

**Epic:** E2. Contract Specification Layer
**Type:** feat
**Priority:** P0
**Effort:** M (4-6h)
**Sprint:** 1
**Dependencies:** PRC-005

### Context
The `HandoffContract` Pydantic model is the IR that both frontends (YAML, decorator) produce and the evaluator consumes. This is the contract declaration surface in canonical form. Schema correctness here determines the reliability of every downstream component.

### Acceptance Criteria
- [ ] `src/precept/contract/schema.py` defines:
  - `ContractFields` (Pydantic model): `required_fields: list[str]`, `preserved_entities: list[str]`, `min_fidelity: float | None` (constrained `[0.0, 1.0]`), `forbidden_drops: list[str]`
  - `HandoffContract` (Pydantic model): `name: str`, `version: str` (default `"0.1"`), `mode: Literal["block", "warn"]` (default `"warn"`), `fields: ContractFields`, `description: str | None`, `metadata: dict[str, str]` (default empty)
  - Custom validators: `required_fields` and `forbidden_drops` must not intersect; `min_fidelity` must be explicitly provided if any field scoring is enabled; `name` must match `^[a-z][a-z0-9_-]*$` regex for safe use in OTel event names and URLs
- [ ] `precept.errors.ContractValidationError` raised with clear message on invalid input
- [ ] Schema has `model_config = ConfigDict(extra="forbid")` to catch typos in YAML (misspelled field name should error, not silently ignore)
- [ ] Schema documented via docstrings that render correctly under `pydoc` and the eventual docs site

### Technical Notes
- Use Pydantic v2 syntax (`ConfigDict`, `Field(default=...)`, `field_validator`). Pydantic v1 compatibility is not required.
- `version` is a string not a semver object; keep the IR simple. Version semantics (breaking vs non-breaking) are a Phase 2 concern.
- Consider but defer: JSON Schema export via `HandoffContract.model_json_schema()`. Useful for editor tooling; not MVP-critical.

### Testing Requirements
- Unit tests in `tests/unit/contract/test_schema.py` covering:
  - Valid contract instantiation with all fields populated
  - Valid contract with only required fields populated (defaults applied)
  - `extra="forbid"` rejects unknown field names
  - `min_fidelity` rejects values outside `[0.0, 1.0]` and non-numeric types
  - `required_fields` + `forbidden_drops` overlap is rejected
  - Invalid `name` patterns rejected (uppercase, starts with digit, contains spaces)
  - Invalid `mode` value rejected
- Property-based tests using `hypothesis`:
  - Any string matching `^[a-z][a-z0-9_-]*$` is accepted as `name`
  - Any float in `[0.0, 1.0]` is accepted as `min_fidelity`
- Coverage target: 95%+ on `schema.py`

### Out of Scope
- YAML parser (PRC-007)
- Decorator frontend (PRC-008)
- Runtime contract modification (intentionally immutable)

### Definition of Done
- All unit and property tests pass
- `mypy --strict` clean
- Code reviewed, merged

---

## PRC-006a: JSON Schema export helper for HandoffContract

**Epic:** E2. Contract Specification Layer
**Type:** feat
**Priority:** P2
**Effort:** S (1-2h)
**Sprint:** post-MVP
**Dependencies:** PRC-006

### Context
`HandoffContract.model_json_schema()` is one Pydantic call away. Exposing it via a tiny helper (e.g. `precept.contract.schema.json_schema()`) would enable editor tooling (VS Code YAML LSP, IntelliJ JSON Schema integration) to validate contract YAML in-place and power the observatory's "contract source" panel. Deliberately deferred from PRC-006 to keep the MVP schema surface minimal.

### Acceptance Criteria
- [ ] `precept.contract.schema.json_schema()` returns a JSON Schema dict for `HandoffContract`.
- [ ] Helper available at `precept.json_schema()` once PRC-026 wires the public API.
- [ ] Unit test verifies the returned schema round-trips through `json.dumps` cleanly.
- [ ] Documented in `docs/contract_reference.md` (PRC-025) once that ticket lands.

### Out of Scope
- A generated `contract.schema.json` file shipped in the repo (emit-on-demand only).
- Publishing to JSON-Schema-store registries.

### Definition of Done
- Helper exported, test passes, referenced in the eventual contract reference doc.

---

## PRC-007: YAML contract loader

**Epic:** E2. Contract Specification Layer
**Type:** feat
**Priority:** P0
**Effort:** M (4-6h)
**Sprint:** 1
**Dependencies:** PRC-006

### Context
YAML is the artefact-bearing contract format. Compliance owners, reviewers, and VCs can read YAML without knowing Python. This loader is one of two frontends producing a `HandoffContract` IR instance.

### Acceptance Criteria
- [ ] `src/precept/contract/yaml_loader.py` exports: `load_contract(path: str | Path) -> HandoffContract`, `load_contract_from_string(yaml_str: str) -> HandoffContract`
- [ ] Uses `yaml.safe_load` exclusively (never `yaml.load`, which is a security risk)
- [ ] Returns `HandoffContract` instance; raises `ContractValidationError` with line/column info where possible on malformed YAML or schema violation
- [ ] Supports YAML anchors/aliases for contract reuse across files
- [ ] Example contract files under `examples/contracts/`:
  - `researcher_to_summariser.yaml`: requires `hypothesis`, `citations`, preserves entities `[primary_source, author]`, `min_fidelity: 0.75`, forbids dropping `uncertainty_bounds`
  - `summariser_to_writer.yaml`: requires `summary`, `key_entities`, preserves entities `[primary_source]`, `min_fidelity: 0.70`

### Technical Notes
- Example YAML structure:
  ```yaml
  name: researcher_to_summariser
  version: "0.1"
  mode: block
  description: "Contract for research agent handing off to summariser"
  fields:
    required_fields:
      - hypothesis
      - citations
    preserved_entities:
      - primary_source
      - author
    min_fidelity: 0.75
    forbidden_drops:
      - uncertainty_bounds
  ```
- Error messages must be actionable. "Invalid contract" is not acceptable; "Field 'min_fidelity' must be between 0.0 and 1.0, got 1.5 (line 7)" is.
- Consider `ruamel.yaml` for preserving comments on round-trip in Phase 2 (observatory could show contract source alongside violations); use `pyyaml` for MVP.

### Testing Requirements
- Unit tests in `tests/unit/contract/test_yaml_loader.py`:
  - Load each example file and assert field values
  - Round-trip: load YAML, serialise IR back, reload, assert equal
  - Malformed YAML (unclosed bracket, bad indent) raises `ContractValidationError` with line info
  - YAML with unknown top-level key raises error (forbidden extras from schema)
  - Empty file raises error
  - YAML anchor/alias correctly resolves
- Integration test: loading both example files produces two distinct valid contracts

### Out of Scope
- YAML schema validation via JSON Schema export (nice-to-have)
- Directory-based bulk loading (deferred)

### Definition of Done
- All tests pass, examples are loadable, error messages reviewed for actionability

---

## PRC-007a: YAML loader error enrichment (line/column on schema violations)

**Epic:** E2. Contract Specification Layer
**Type:** feat
**Priority:** P2
**Effort:** S-M (2-4h)
**Sprint:** post-MVP
**Dependencies:** PRC-007

### Context
PRC-007 ships with actionable errors for YAML *syntax* failures (line/column carried via `ContractValidationIssue.yaml_mark`). Errors originating from Pydantic schema validation (e.g. "min_fidelity must be between 0.0 and 1.0") carry only a field path, not a YAML position. Users debugging larger contract files benefit from "got 1.5 (line 7)" over "field fields.min_fidelity: input should be less than or equal to 1".

Implementation requires a position-tracking YAML loader (custom `yaml.SafeLoader` subclass that annotates each node with `(line, column)`) so the loader can map Pydantic error `loc` tuples back to their source positions.

### Acceptance Criteria
- [ ] A position-tracking loader annotates scalar/mapping/sequence nodes with line/column.
- [ ] On `pydantic.ValidationError`, each resulting `ContractValidationIssue` carries a `yaml_mark` pointing at the offending value's position (not the parent mapping).
- [ ] Unit tests cover: out-of-range `min_fidelity`, unknown field, bad `mode`, forbidden-drops intersection — each asserting the `yaml_mark` matches the line the bad value appears on.
- [ ] No regression on v0 acceptance criteria (syntax errors still report line/column as today).

### Out of Scope
- Column-perfect positions for values inside inline flow sequences (line-only is acceptable).
- Round-trip preservation of comments (`ruamel.yaml` territory).

### Definition of Done
- Enriched errors verified on the two example contracts via a malformed-copy fixture per error type.

---

## PRC-007b: README for examples/contracts

**Epic:** E2. Contract Specification Layer
**Type:** docs
**Priority:** P2
**Effort:** XS (<1h)
**Sprint:** post-MVP
**Dependencies:** PRC-007

### Context
`examples/contracts/` currently holds two YAML fixtures. As PRC-017/018/019 land and more fixtures accumulate, a short README next to the files explaining *what each fixture demonstrates* keeps the demo story self-documenting and helps new contributors pick the right fixture for a new scenario.

### Acceptance Criteria
- [ ] `examples/contracts/README.md` with a one-paragraph header plus a table of fixture → purpose → associated scenario.
- [ ] Updated each time a new fixture lands, per PRC-017/018 DoD.

### Out of Scope
- Mechanism-level documentation of the YAML schema (covered by PRC-025 contract reference).

### Definition of Done
- README merged, linked from the main README's examples section once PRC-024 lands.

---

## PRC-008: Decorator frontend `@handoff_contract` (sync only)

**Epic:** E2. Contract Specification Layer
**Type:** feat
**Priority:** P0
**Effort:** S (3-4h)
**Sprint:** 1
**Dependencies:** PRC-006

### Context
The decorator is the lightest-weight frontend: Python developers can attach a contract to a handoff function without writing a YAML file. The decorator produces the same `HandoffContract` IR as the YAML loader. Both frontends share the IR and the evaluator.

**Scope decision (v0):** sync functions only. Async function decoration introduces signature-preservation edge cases (return-type narrowing, awaitable wrapping, exception propagation across await boundaries) that are not worth the surface area for v0. Async decorator support is tracked as a Phase 2 enhancement; users with async handoff functions can use the YAML frontend or instantiate `HandoffContract` directly until then.

### Acceptance Criteria
- [ ] `src/precept/contract/decorator.py` exports `handoff_contract(...)` decorator
- [ ] Decorator signature accepts all `HandoffContract` fields as kwargs: `name`, `required`, `preserved_entities`, `min_fidelity`, `forbidden_drops`, `mode`, `description`, `version`
- [ ] Decorator attaches a `HandoffContract` instance to the decorated function as a `__precept_contract__` attribute (retrievable by integration layer)
- [ ] Decorator does NOT execute the contract check at call time in this ticket (evaluation is attached by the LangGraph integration in PRC-014); the decorator is purely a metadata attachment mechanism in v0
- [ ] Decorator is usable as `@handoff_contract(...)` (call form) but NOT as `@handoff_contract` (bare form); bare form raises `TypeError` with guidance
- [ ] Sync functions only: detection via `inspect.iscoroutinefunction()`; if applied to a coroutine function, raises `TypeError` with message: "Async function decoration is not supported in v0.1.0. Use precept.load_contract() or HandoffContract(...) directly with your async function. Tracked: Phase 2 enhancement."
- [ ] `functools.wraps` preserves original function signature for IDE introspection
- [ ] Example in `examples/decorator_usage.py` demonstrating usage alongside a LangGraph handoff tool

### Technical Notes
- Example usage:
  ```python
  from precept import handoff_contract

  @handoff_contract(
      name="researcher_to_summariser",
      required=["hypothesis", "citations"],
      preserved_entities=["primary_source"],
      min_fidelity=0.75,
      forbidden_drops=["uncertainty_bounds"],
      mode="block",
  )
  def handoff_to_summariser(state): ...
  ```
- Kwarg name `required` (not `required_fields`) on decorator is a developer-ergonomics choice. The IR still uses `required_fields`. Mapping happens in the decorator implementation.
- Future: `@handoff_contract.from_yaml("path/to/contract.yaml")` classmethod constructor and async support. Both deferred.

### Testing Requirements
- Unit tests in `tests/unit/contract/test_decorator.py`:
  - Decorated sync function retains original signature and return type
  - `__precept_contract__` attribute is a valid `HandoffContract`
  - Invalid kwargs (e.g., `min_fidelity=2.0`) raise `ContractValidationError` at decoration time, not call time
  - Async function raises `TypeError` with the documented guidance message
  - Bare `@handoff_contract` form raises `TypeError` with clear message
- Integration test: YAML-loaded contract and decorator-declared contract with equivalent inputs produce equal `HandoffContract` instances (IR equivalence)

### Out of Scope
- Async function decoration (Phase 2)
- Runtime evaluation triggering (PRC-014)
- `from_yaml` constructor (Phase 2 convenience ticket)

### Definition of Done
- Tests pass, IR equivalence validated, example runs cleanly, async-rejection message reviewed for clarity

---

## PRC-009: Contract registry and lookup

**Epic:** E2. Contract Specification Layer
**Type:** feat
**Priority:** P1
**Effort:** S (2-3h)
**Sprint:** 1
**Dependencies:** PRC-006, PRC-007, PRC-008

### Context
When a LangGraph handoff is evaluated, the integration layer needs to look up the relevant contract by name. A lightweight in-process registry avoids passing contracts through function arguments everywhere and enables a workflow where contracts are loaded once at startup and referenced by name at evaluation time.

### Acceptance Criteria
- [ ] `src/precept/contract/registry.py` exports `ContractRegistry` class with methods: `register(contract: HandoffContract) -> None`, `get(name: str) -> HandoffContract`, `list_contracts() -> list[str]`, `load_directory(path: str | Path) -> int` (loads all `*.yaml` files, returns count)
- [ ] Module-level singleton `default_registry` for simple use cases
- [ ] `register` raises `KeyError` on duplicate name unless `overwrite=True`
- [ ] `get` raises `KeyError` on missing contract with suggestion ("Contract 'foo' not found. Available: bar, baz")
- [ ] Registration uses a `threading.Lock` defensively (3 LoC; protects against the realistic case of a Gunicorn/Uvicorn worker pool registering at request-handling time rather than startup). Concurrent-write testing not required at v0; the lock is documented but not stress-tested.

### Technical Notes
- Do NOT make the registry a Singleton pattern - use a module-level default instance that can be replaced for testing. Singletons are hostile to unit tests.
- `load_directory` is a convenience for loading multiple contract files; does not recurse unless `recursive=True` passed.
- Thread-safety rationale: the lock is cheap insurance, not an MVP guarantee. If we discover a real concurrency issue post-launch, we have the primitive in place to harden behaviour without API change.

### Testing Requirements
- Unit tests in `tests/unit/contract/test_registry.py`:
  - Register and retrieve a contract
  - Duplicate name raises unless `overwrite=True`
  - Missing name raises with helpful message listing available contracts
  - `load_directory` loads multiple files and returns correct count
  - `load_directory` skips non-YAML files and malformed YAML files with warning logged, not raised

### Out of Scope
- Persistent storage (contracts are in-process only)
- Remote registry (Phase 2 if needed)
- Concurrency stress tests (Phase 2 if real-world reports surface)

### Definition of Done
- Tests pass, module docstring explains intended usage pattern

---

## PRC-010: Scorer abstract base class and ScoreResult type

**Epic:** E3. Scoring Engine
**Type:** feat
**Priority:** P0
**Effort:** M (4h)
**Sprint:** 1
**Dependencies:** PRC-006

### Context
The scorer is the component that answers "how well did information survive the handoff?". The v0 concrete implementation is embedding-based (PRC-011). A research-validated calibrated scorer is a Phase 2 deliverable (PRC-035). Defining a clean abstract interface now means both implementations share a stable contract; swapping the scorer is configuration, not code change.

### Acceptance Criteria
- [ ] `src/precept/scoring/base.py` defines:
  - `HandoffPayload` (Pydantic model or TypedDict): `fields: dict[str, Any]`, `raw: str | None`, `metadata: dict[str, str]`. Fields are the structured payload; `raw` is optional stringified representation for embedding scorers.
  - `FieldScore` (Pydantic model): `field_name: str`, `score: float` (in `[0,1]`), `method: str` (e.g., `"embedding_cosine"`), `passed: bool`
  - `ScoreResult` (Pydantic model): `overall_score: float`, `field_scores: list[FieldScore]`, `scorer_name: str`, `scorer_version: str`, `timestamp_iso: str`
  - `Scorer` (abstract base class using `abc.ABC`): abstract method `score(source: HandoffPayload, target: HandoffPayload, contract: HandoffContract) -> ScoreResult`
- [ ] `Scorer` subclasses must define class-level `name: str` and `version: str` attributes; enforced via `__init_subclass__`
- [ ] Abstract docstring specifies the contract for implementations: `score()` must be deterministic given same inputs; must not mutate payloads; must handle missing optional fields gracefully

### Technical Notes
- Per-field scoring is in-scope for v0 (per Gian's answer on Q6). `ScoreResult.field_scores` captures each field's individual score; `overall_score` is the weighted aggregate.
- `overall_score` aggregation method is a Scorer implementation detail (simple average for v0, weighted for future). Document this in `EmbeddingProxy` not in base.
- Do NOT include mutual information terminology in base class docstrings. Scorer is generic; MI is one possible method among several (KSG, Gaussian closed-form, InfoNCE, MINE per dissertation review) that may populate the Phase 2 calibrated scorer.

### Testing Requirements
- Unit tests in `tests/unit/scoring/test_base.py`:
  - Cannot instantiate `Scorer` directly (abstract)
  - Concrete subclass missing `name` or `version` raises at class definition time
  - `ScoreResult` validates field ranges (score in `[0,1]`, overall_score in `[0,1]`)
  - `HandoffPayload` accepts arbitrary field types (dict values are `Any`)

### Out of Scope
- Concrete implementations (PRC-011, PRC-012)
- Async scoring API (add only if a concrete implementation needs it)

### Definition of Done
- Tests pass, docstrings reviewed

---

## PRC-011: EmbeddingProxy scorer (v0 concrete implementation)

**Epic:** E3. Scoring & Evaluation Engine
**Type:** feat
**Priority:** P0
**Effort:** L (10-12h)
**Sprint:** 1
**Dependencies:** PRC-010

### Context
`EmbeddingProxy` is the v0 scorer: embedding-based cosine similarity on field values, aggregated per-field into an overall score. It is intentionally NOT called `MIScorer` or `MutualInformationScorer` - the MI-theoretic validated scorer is a post-dissertation Phase 2 deliverable (PRC-035). The EmbeddingProxy is honest about being a proxy; its scores are a placeholder until calibration.

### Acceptance Criteria
- [ ] `src/precept/scoring/embedding_proxy.py` defines `EmbeddingProxy(Scorer)` with class attributes `name = "embedding_proxy"`, `version = "0.1.0"`
- [ ] Uses `sentence-transformers` model `all-MiniLM-L6-v2` by default (small, fast, deterministic with fixed seed)
- [ ] **Model loaded in `__init__`**, NOT lazily on first `score()` call. Rationale: lazy loading on first call produces a multi-second latency spike on the first handoff and can block an asyncio event loop for the duration of a model download (~80MB) followed by load. Loading in the constructor moves this cost to application startup, where it belongs. Constructor accepts `model_name: str` for swapping and `_skip_model_load: bool = False` (test-only escape hatch).
- [ ] Constructor logs at INFO level: `"EmbeddingProxy initialised: model={model_name}, ~{N}MB resident memory"` so users notice the cost
- [ ] `score(source, target, contract)` implementation:
  1. For each field in `contract.fields.required_fields`, extract source value and target value
  2. Encode both to embeddings via the sentence-transformer
  3. Compute cosine similarity per field → `FieldScore(field_name, score, method="embedding_cosine", passed=score >= contract.fields.min_fidelity)`
  4. `overall_score` = unweighted mean of field scores
  5. Return `ScoreResult`
- [ ] Handles missing fields gracefully: if a required field is absent in target, that field's score is 0.0 and `passed=False`
- [ ] Non-string field values are stringified via `str()` before encoding (document this; numeric preservation is a calibrated-scorer concern)
- [ ] Docstring explicitly states: "Proxy scorer. Scores are cosine similarity in embedding space; they correlate with but do not equal mutual information. A research-validated calibrated scorer is planned for Phase 2 (see CalibratedScorer)."
- [ ] Async-context documentation: docstring includes guidance: "score() is synchronous and CPU-bound (~100-500ms per call). When called from inside an asyncio coroutine, wrap with `asyncio.to_thread(scorer.score, ...)` to avoid blocking the event loop. The PRC-014 LangGraph integration handles this automatically when async context is detected."
- [ ] Deterministic: same inputs produce same output across runs (model and tokeniser are deterministic; no sampling)

### Technical Notes
- `sentence-transformers` downloads the model on first instantiation (~80MB). Document this in README "first run" section. Pin a known-good revision commit for full reproducibility.
- Avoid `torch` eager mode surprises: set `torch.set_grad_enabled(False)` in the scorer; inference only.
- For CPU-only compatibility (no GPU assumed), do not use `.cuda()` calls; let sentence-transformers auto-detect.
- Performance target: single `score()` call on a 3-field contract < 500ms on a typical laptop CPU. Constructor (one-time, at startup): up to 5s on first run including download, ~1s on warm cache.
- Memory footprint: ~150-200MB resident after model load (sentence-transformer + Python overhead). Document in module docstring; users running many parallel processes need to plan accordingly.
- The `_skip_model_load` constructor flag is for unit tests that exercise the scoring API surface without paying the model-load cost. Marked private; not part of public API.

### Testing Requirements
- Unit tests in `tests/unit/scoring/test_embedding_proxy.py`:
  - Score of identical payloads is ≥ 0.99 (near-perfect; not exactly 1.0 because of tokenisation edges)
  - Score of totally unrelated payloads is < 0.3
  - Missing required field scores 0.0 with `passed=False`
  - `ScoreResult.field_scores` has correct length matching `required_fields`
  - Determinism: same input produces same output across 10 runs
  - Model-swap: passing `model_name="paraphrase-MiniLM-L3-v2"` works (smaller model for test speed)
  - Constructor with `_skip_model_load=True` returns instance with no model attribute (verify scoring raises clear error)
- Integration test: score a real source/target pair from fixture data (PRC-018) and assert expected violation is detected
- Performance test (not blocking CI): assert single score call < 2s on CI runner (generous margin); assert constructor < 10s on cold cache
- Async-safety smoke test: invoke `score()` via `asyncio.to_thread()` from a coroutine; verify it does not block the loop measurably (compare event loop tick count before/after)

### Out of Scope
- GPU acceleration
- Batch scoring API (useful in Phase 2 observability workflows; not MVP)
- Native async API (use `asyncio.to_thread` wrapper at call sites)
- Entity-level scoring (PRC-012 `preserved_entities` rule covers this via a different mechanism)

### Definition of Done
- All tests pass, determinism verified, docstring does not claim MI-level rigour, async-context guidance documented and verified

---

## PRC-012: Per-field rule evaluators (required_fields, preserved_entities, forbidden_drops)

**Epic:** E3. Scoring Engine
**Type:** feat
**Priority:** P0
**Effort:** L (8-10h)
**Sprint:** 1
**Dependencies:** PRC-010

### Context
Not every contract field is scored by embedding similarity. `required_fields` is a presence check. `preserved_entities` requires entity-level name matching across source and target. `forbidden_drops` is a structural check (field must not be absent in target if present in source). Each rule is a separate, independently testable, composable evaluator.

### Acceptance Criteria
- [ ] `src/precept/evaluator/rules.py` defines:
  - `RuleResult` (Pydantic model): `rule_name: str`, `passed: bool`, `details: dict[str, Any]`, `violation_message: str | None`
  - `required_fields_rule(source, target, required: list[str]) -> RuleResult`: checks that every name in `required` exists as a key in `target.fields`
  - `preserved_entities_rule(source, target, entities: list[str]) -> RuleResult`: checks that every entity name in the source's stringified content also appears in the target's stringified content. Uses simple case-insensitive substring matching for v0 (NER-based matching deferred to PRC-030 as a quality uplift)
  - `forbidden_drops_rule(source, target, forbidden: list[str]) -> RuleResult`: for each name, if present in source, must also be present in target
- [ ] All rules return `RuleResult`, never raise; rule failures are data, not exceptions
- [ ] `violation_message` is populated when `passed=False`, templated for human readability: e.g., "Required field 'hypothesis' missing in target payload"

### Technical Notes
- Substring-based entity matching is a conscious v0 simplification. It produces false positives (the word "Smith" matches many strings) and false negatives (morphological variants). Document this clearly. Phase 2 PRC-030 upgrades to spaCy or a light NER model.
- Do not conflate entity matching with embedding scoring. A payload can preserve entity mentions (substring match) while still degrading semantically (low embedding similarity). Both signals are useful; they measure different things.
- Rules are pure functions; no state, no I/O, no logging. All observability happens at the evaluator layer (PRC-013).

### Testing Requirements
- Unit tests in `tests/unit/evaluator/test_rules.py`:
  - `required_fields_rule`: present → pass; missing → fail with named field in message; empty required list → always pass
  - `preserved_entities_rule`: entity present in both → pass; entity present in source but not target → fail; case variations handled; empty entity list → always pass
  - `forbidden_drops_rule`: present in both → pass; present in source, absent in target → fail; present in target only → pass (nothing dropped)
- Property-based tests with `hypothesis`:
  - Rules never raise regardless of input structure (robust to empty strings, unicode, huge field names)
  - `required_fields_rule([any], target_with_those_fields)` always passes

### Out of Scope
- NER-based entity matching (PRC-030, Phase 2)
- Regex-based field matching
- Nested field path support (e.g., `metadata.source` as a dotted path)

### Definition of Done
- Tests pass, rules are pure functions with no side effects

---

## PRC-013: Evaluation engine, ViolationEvent, HandoffBlockedError, and Exporter ABC

**Epic:** E3. Scoring & Evaluation Engine
**Type:** feat
**Priority:** P0
**Effort:** L (12-14h)
**Sprint:** 1
**Dependencies:** PRC-011, PRC-012

### Context
The evaluation engine composes scoring + per-field rules + contract mode (block vs warn) and produces a `ViolationEvent`. This ticket also defines the two abstractions every downstream component depends on: the `HandoffBlockedError` exception class (raised by the LangGraph integration in `block` mode) and the `Exporter` ABC (consumed by both telemetry exporters and the LangGraph integration). Co-locating these here removes a circular dependency that existed when `HandoffBlockedError` was defined in PRC-015 but referenced from PRC-014, and resolves the missing-exporter-abstraction gap that left PRC-014 without a clean integration surface.

### Acceptance Criteria

**Core types (`src/precept/types.py` and `src/precept/errors.py`):**
- [ ] `ViolationEvent` (Pydantic model): `contract_name: str`, `contract_version: str`, `mode: Literal["block", "warn"]`, `passed: bool`, `score_result: ScoreResult`, `rule_results: list[RuleResult]`, `triggered_at_iso: str`, `event_id: str` (UUID4), `source_summary: dict[str, Any]`, `target_summary: dict[str, Any]`, `schema_version: str = "0.1"`
- [ ] `ViolationEvent.to_compact_dict()` method: returns a dict shaped for OTel attributes (no nested dicts at top level; all values are str/int/float/bool); enforces a hard 4 KiB serialised-JSON size ceiling. If exceeded, summaries are progressively truncated (target side first, then source) until under limit; a `precept.payload_truncated: True` attribute is added when truncation occurred. Rationale: OTel attribute size limits in many backends are 4 KiB (Datadog, Jaeger); silently dropped events are worse than truncated ones.
- [ ] `HandoffBlockedError(Exception)`: defined in `src/precept/errors.py` with attributes `violation_event: ViolationEvent`, `impact_summary: str = ""` (default empty; populated by PRC-015's impact module). Carries full violation event so supervisors can route intelligently. The `impact_summary` field is populated post-construction by the integration layer; this keeps the error class itself dependency-free.
- [ ] `ContractValidationError(Exception)`: re-exported here for canonical location (defined originally in PRC-006).

**Exporter abstraction (`src/precept/exporters/base.py`):**
- [ ] `Exporter` (ABC): abstract method `export(event: ViolationEvent) -> None`. Class-level `name: str` attribute required (enforced via `__init_subclass__`).
- [ ] Abstract docstring contract: `export()` MUST NOT raise on transport failure (log and continue); MUST NOT mutate the event; MUST be callable from any thread; MUST be idempotent on repeat calls with the same event_id (best-effort dedup is the exporter's responsibility, not the evaluator's).
- [ ] `NoOpExporter` concrete class (in `base.py`): default safe sink for tests and for users who haven't configured an exporter. Discards events; no I/O.
- [ ] `MultiExporter` concrete class: holds a list of `Exporter` instances; `export()` calls each in order, isolating failures (one exporter raising does not prevent others from receiving the event).

**Evaluator (`src/precept/evaluator/engine.py`):**
- [ ] `Evaluator` class: constructor takes `scorer: Scorer`, `exporter: Exporter | None = None` (defaults to `NoOpExporter`). Method `evaluate(source: HandoffPayload, target: HandoffPayload, contract: HandoffContract) -> ViolationEvent`.
- [ ] `evaluate` implementation:
  1. Run `required_fields_rule`, `preserved_entities_rule`, `forbidden_drops_rule` → collect rule results
  2. Run `scorer.score(source, target, contract)` → ScoreResult
  3. Compute `passed`: `all(rule_results.passed) AND all(field_score.passed for field_score in score_result.field_scores)`
  4. Build `ViolationEvent` with size-ceiling enforcement applied
  5. Call `self.exporter.export(event)` (failures isolated via try/except; exporter problems do not break evaluation)
  6. Return the event
- [ ] `source_summary` and `target_summary` capture field names and first 100 characters of string values; further truncation applied by `to_compact_dict()` if total payload exceeds 4 KiB
- [ ] All timestamps are ISO 8601 UTC strings (`datetime.now(timezone.utc).isoformat()`)

### Technical Notes
- `passed` is the authoritative violation flag. `mode` is metadata; the integration layer (PRC-014/015) decides whether to raise `HandoffBlockedError` based on `mode` + `passed`.
- The 4 KiB ceiling is the realistic upper bound for OTel span attributes across backends as of April 2026 (Datadog: 4 KiB per attribute, 1024 attributes per span; Jaeger: similar; OpenObserve: 8 KiB; Honeycomb: 64 KiB but discouraged). 4 KiB is the safe lower bound.
- `MultiExporter` exists because the realistic deployment has both OTel + JSON-file exporters running (production telemetry + local audit log).
- `HandoffBlockedError`'s `impact_summary` is mutable-by-default-empty rather than required: this lets the error class live in `errors.py` with no dependency on the impact-template module (PRC-015), which is what creates the previous circular dependency.

### Testing Requirements
- Unit tests in `tests/unit/evaluator/test_engine.py`:
  - Clean handoff (all rules pass, score above threshold) → `ViolationEvent.passed == True`
  - Missing required field → `passed == False`, rule failure populated
  - Preserved entity dropped → `passed == False`
  - Embedding similarity below threshold → `passed == False`, `FieldScore.passed == False`
  - `event_id` is unique across multiple evaluations
  - `source_summary` and `target_summary` truncate long strings correctly (no more than 100 chars per value)
  - Evaluator with default `NoOpExporter` produces events without raising
  - Evaluator with a failing exporter (raises in `export()`) still returns the event (exporter failure isolated)
  - Evaluator with `MultiExporter([failing, working])` calls both; working exporter receives event despite first one raising
- Unit tests in `tests/unit/test_types.py`:
  - `ViolationEvent.to_compact_dict()` output passes JSON serialisation
  - `ViolationEvent.to_compact_dict()` with synthetically inflated summaries (10 KB raw) returns dict ≤ 4 KiB serialised, with `precept.payload_truncated: True`
  - `ViolationEvent.to_compact_dict()` with normal-sized event has no truncation flag
- Unit tests in `tests/unit/test_errors.py`:
  - `HandoffBlockedError` carries full violation event
  - Default `impact_summary` is empty string; can be set post-construction
- Unit tests in `tests/unit/exporters/test_base.py`:
  - `Exporter` cannot be instantiated directly
  - `NoOpExporter` accepts events without raising
  - `MultiExporter` calls all child exporters; exception in one does not stop others (verified via mock)
- Integration test: full evaluator run on a fixture source/target pair from PRC-018

### Out of Scope
- Parallel rule execution (not worth the complexity at v0)
- Rule extensibility via plugin (Phase 2+)
- Async exporters (Phase 2; sync API with thread-safety guarantee is sufficient)

### Definition of Done
- Tests pass, `ViolationEvent` structure reviewed with an eye to OTel export shape, payload-size ceiling verified under stress, circular dependency with PRC-014 confirmed broken (PRC-014 imports `HandoffBlockedError` from `precept.errors` with no upstream import path back to PRC-014/015)

---

# Sprint 2: LangGraph Integration + Demo Pipeline

---

## PRC-014: LangGraph integration - tool wrapper + pure evaluation hook

**Epic:** E4. LangGraph Integration
**Type:** feat
**Priority:** P0
**Effort:** XL (14-18h - re-split if needed)
**Sprint:** 2
**Dependencies:** PRC-006, PRC-009, PRC-013

### Context
LangGraph integration is where Precept meets reality. Modern LangGraph code (2026) splits across two patterns: (1) tool-based supervisors using `create_handoff_tool` (via `langgraph_supervisor` or manual implementations), (2) `Command(goto="next_agent")` returns directly from nodes - the more flexible and increasingly recommended pattern. A LangGraph integration that only wraps `create_handoff_tool` becomes useless the moment a user adopts the `Command` pattern. This ticket provides BOTH integration paths from a shared core.

### Acceptance Criteria

**Pure evaluation hook (`src/precept/integrations/langgraph/eval_hook.py`):**
- [ ] `evaluate_handoff(source: dict | BaseModel | Any, target: dict | BaseModel | Any, contract_name: str, *, registry: ContractRegistry | None = None, evaluator: Evaluator | None = None, raise_on_block: bool = True) -> ViolationEvent` - a pure function users call directly inside a node before returning a `Command(goto=...)` or state update
- [ ] Looks up the contract by name from registry (defaults to `default_registry`)
- [ ] Constructs `HandoffPayload` instances from source/target via the contracted-field extractor (PRC-016)
- [ ] Calls `evaluator.evaluate()` and returns the `ViolationEvent`
- [ ] If `raise_on_block=True` (default) AND contract mode is `block` AND `event.passed == False`: raises `HandoffBlockedError` with violation details
- [ ] If `raise_on_block=False`: returns the event unconditionally; caller decides what to do
- [ ] Async-context detection: if called from a running asyncio loop, the synchronous `evaluator.evaluate()` is automatically dispatched to a thread via `asyncio.to_thread()` to prevent loop blocking. Detection via `asyncio.get_running_loop()` in a try/except. Document this clearly.
- [ ] Example usage:
  ```python
  from precept.integrations.langgraph import evaluate_handoff
  from langgraph.types import Command

  def supervisor_node(state):
      next_payload = build_handoff_payload(state)
      evaluate_handoff(
          source=state,
          target=next_payload,
          contract_name="researcher_to_summariser",
      )  # raises HandoffBlockedError on block-mode violation
      return Command(goto="summariser", update={"payload": next_payload})
  ```

**Tool wrapper (`src/precept/integrations/langgraph/handoff_tool.py`):**
- [ ] `create_precept_handoff_tool(agent_name: str, contract_name: str, *, registry: ContractRegistry | None = None, evaluator: Evaluator | None = None, name: str | None = None, description: str | None = None) -> BaseTool`
- [ ] Signature mirrors `langgraph_supervisor.create_handoff_tool` where overlapping; extends with `contract_name`
- [ ] Internal implementation: composes the underlying LangGraph handoff tool with a wrapper that calls `evaluate_handoff()` before delegating to the underlying tool's behaviour
- [ ] Drop-in replacement: existing supervisors using `create_handoff_tool` migrate by changing the import and adding `contract_name`
- [ ] On contract failure (block mode), the raised `HandoffBlockedError` propagates as a ToolMessage error to the supervisor LLM, which can decide to retry or route elsewhere

**Shared behaviour (both paths):**
- [ ] Graceful degradation: if registry does not contain the named contract, log a warning at WARNING level and proceed WITHOUT blocking (fail-open is the safe default for observability-layer tooling; document this loudly in module docstring AND in README)
- [ ] Both paths use the same `Evaluator` and `Exporter` configuration; events flow through `evaluator.exporter` per PRC-013
- [ ] `__init__.py` exports both `evaluate_handoff` and `create_precept_handoff_tool` for easy import

### Technical Notes
- LangGraph's `create_handoff_tool` is internal to `langgraph_supervisor` and has evolved (the supervisor library is partially deprecated in favour of manual tool-based patterns). Integration must work with both the `langgraph_supervisor.create_handoff_tool` path AND the manual tool-based supervisor path AND the `Command(goto=...)` pattern documented in current LangChain guidance. Verify against `langgraph>=0.5` (pinned in project deps).
- Known friction: `langgraph_supervisor` had an open issue (`langgraph-supervisor-py#205`) where supervisors didn't pass state cleanly to subagent handoffs. The wrapper must use `InjectedState` + `task_description` pattern shown in that issue's workaround, not rely on default state propagation. Cite the issue in code comments.
- The `evaluate_handoff()` function is the more durable surface; tool wrapping is convenience built on top. If LangGraph's tool API changes radically, only `handoff_tool.py` needs updating; `eval_hook.py` is framework-API-independent.
- Async-context detection rationale: LangGraph nodes can be sync OR async functions. A sync-only Precept call from inside an async node would block the event loop during the ~500ms scoring call. Auto-dispatching to a thread when an async loop is detected makes the API behave correctly in both contexts without forcing users to think about it.
- `HandoffBlockedError` already exists from PRC-013 (no circular dep).

### Testing Requirements
- Unit tests in `tests/unit/integrations/langgraph/test_eval_hook.py`:
  - `evaluate_handoff` with valid contract evaluates and returns event
  - Block mode + failing contract raises `HandoffBlockedError`
  - Warn mode + failing contract emits event but does not raise
  - Missing contract name logs warning, returns synthetic-pass event, does not raise (fail-open verified)
  - `raise_on_block=False` never raises even on block-mode failure
  - Async-context dispatch: invoke from inside an asyncio coroutine; verify event loop is not blocked (measure tick latency before and during call)
- Unit tests in `tests/unit/integrations/langgraph/test_handoff_tool.py` (mock the LangGraph pieces):
  - Tool created with a valid contract name evaluates on invocation
  - Underlying handoff behaviour is preserved (handoff completes when contract passes)
  - Contract failure surfaces correctly through tool result/error machinery
- Integration tests in `tests/integration/test_langgraph_integration.py`:
  - Build a minimal 2-node LangGraph supervisor using real `langgraph_supervisor`, register a contract, invoke a query, assert the evaluator ran and the event was emitted via the configured exporter
  - Same setup with degraded handoff, assert block occurred
  - Build a 2-node LangGraph using the `Command(goto=...)` pattern + `evaluate_handoff()`; assert same end-to-end behaviour
  - Async LangGraph node calling `evaluate_handoff` does not produce event-loop warnings

### Out of Scope
- OpenAI Agents SDK `input_filter` integration (Phase 2)
- Claude Agent SDK `Agent` tool integration (Phase 2)
- LangGraph checkpointer integration for resumable violations (Phase 2)
- Native async API on the Scorer (Phase 2; `asyncio.to_thread` shim is sufficient)

### Definition of Done
- Both integration paths shipping; unit + integration tests pass for both; graceful degradation behaviour confirmed with a manual smoke test; README snippet demonstrates BOTH usage patterns; async-safety verified

---

## PRC-015: Violation impact summaries (populator)

**Epic:** E4. LangGraph Integration
**Type:** feat
**Priority:** P0
**Effort:** S (3-4h)
**Sprint:** 2
**Dependencies:** PRC-013

### Context
When a contract blocks a handoff, the supervisor needs a human-legible impact description (placeholder at v0, per Q8 decision). The `HandoffBlockedError` class itself lives in PRC-013 with a default-empty `impact_summary`; this ticket is the populator module that fills that field with concrete impact text using a curated lookup table. This separation removes the previously-circular dependency on PRC-014 and keeps impact copy editable independently of error semantics.

### Acceptance Criteria
- [ ] `src/precept/integrations/langgraph/impact.py` defines:
  - `IMPACT_TEMPLATES: dict[tuple[str, str], str]` - keyed by `(contract_name, failing_rule_name)`. Curated dict; not a YAML file. Rationale: Python dict is IDE-refactorable (rename a contract → IDE finds the key), unit-testable (we can assert keys exist for known contracts), and avoids YAML's silent-fallthrough on key typos. YAML-based runtime override deferred to Phase 2 when non-engineer impact-copy editing becomes a real workflow need.
  - `populate_impact_summary(error: HandoffBlockedError) -> None` - mutates the error in place, setting `error.impact_summary` to the templated string
  - `render_impact_text(contract_name: str, rule_name: str, source_agent: str, target_agent: str) -> str` - pure helper for templating, usable independently
- [ ] Templated string format: "Handoff from <source> to <target> blocked: <rule_name> failed on contract '<contract_name>'. Downstream impact: <impact_text>."
- [ ] Default fallback when no template matches: "Downstream agents may receive incomplete or misleading context for this decision." (explicit fallback constant, named `DEFAULT_IMPACT_FALLBACK` for testability)
- [ ] Initial template entries cover the demo contracts (PRC-018):
  ```python
  IMPACT_TEMPLATES = {
      ("researcher_to_summariser", "required_fields"):
          "Writer agent will compose output without hypothesis grounding; conclusions may be unsupported",
      ("researcher_to_summariser", "preserved_entities"):
          "Source attribution is dropped before summarisation; final output cannot trace claims to citations",
      ("summariser_to_writer", "preserved_entities"):
          "Primary sources may be dropped from final output, breaking citation integrity",
      ("summariser_to_writer", "forbidden_drops"):
          "Uncertainty bounds removed; downstream output will overstate confidence",
      # ... extend as new contracts are added
  }
  ```
- [ ] PRC-014's `evaluate_handoff()` calls `populate_impact_summary(error)` immediately before raising any `HandoffBlockedError`

### Technical Notes
- This is explicitly a placeholder at v0 (per Q8 answer). Impact text is hand-written, not computed. Phase 2 can explore learned impact prediction from historical violation-to-outcome pairs once real traffic data exists.
- Why a Python dict and not YAML: silent fallthrough on a renamed contract is a real footgun (a contract rename in YAML would not error - it would silently use the default fallback for every violation). A Python dict surfaces missing keys at test time via the explicit `assert ("contract_x", "rule_y") in IMPACT_TEMPLATES` test.
- Impact copy should be concrete and domain-specific. "Downstream agent may produce incorrect output" is useless. "Writer agent will compose output without hypothesis grounding; conclusions may be unsupported" is useful.
- The `render_impact_text()` helper exists so the observatory (PRC-022) can render impact text without instantiating a full `HandoffBlockedError`.

### Testing Requirements
- Unit tests in `tests/unit/integrations/langgraph/test_impact.py`:
  - Every (contract_name, rule_name) pair in `IMPACT_TEMPLATES` renders without error
  - `populate_impact_summary()` mutates the error in place; original event unmodified
  - Unknown combination falls back to `DEFAULT_IMPACT_FALLBACK`
  - Impact string contains all expected tokens (source, target, rule name, contract name)
  - Test asserting that all demo contract+rule combinations have impact entries (regression test against omissions)

### Out of Scope
- Impact learning from outcomes (Phase 2)
- YAML-based runtime override (Phase 2 if non-engineer editing becomes a real workflow)
- Multi-language impact copy (i18n) - not needed at v0

### Definition of Done
- Tests pass, impact templates cover all demo contracts, fallback behaviour verified, populator integrated into PRC-014

---

## PRC-016: Contracted-field extractor (LangGraph state → HandoffPayload)

**Epic:** E4. LangGraph Integration
**Type:** feat
**Priority:** P0
**Effort:** S (3-4h)
**Sprint:** 2
**Dependencies:** PRC-006, PRC-013

### Context
Precept evaluates handoffs against contracts. Contracts declare `required_fields` and `preserved_entities` - and ONLY those fields matter for evaluation. There is no need to serialise the entire LangGraph state, walk message histories, handle arbitrary Pydantic models, or attempt PII redaction across uncontrolled object graphs. The original "full state serialiser" design was scope creep that introduced security risk (accidentally serialising secrets injected into uncontracted state fields), performance overhead (recursing through large state), and brittleness (LangGraph state shapes evolve). This ticket replaces that with a focused extractor: given a contract and a state object, extract only the fields the contract names. Everything else is ignored.

### Acceptance Criteria
- [ ] `src/precept/integrations/langgraph/extractor.py` defines:
  - `extract_payload(state: Any, contract: HandoffContract, *, max_field_chars: int = 2000) -> HandoffPayload`
  - Inspects `contract.fields.required_fields` and `contract.fields.preserved_entities`; for each named field, attempts to extract the value from `state` via:
    1. `state[field]` if state is a dict-like (TypedDict, plain dict)
    2. `getattr(state, field, None)` if state is an object (Pydantic model, dataclass, namespace)
    3. `state.get(field, None)` as the dict fallback
  - Missing fields are recorded as the literal `None` in the resulting `HandoffPayload.fields` dict (not omitted - so downstream rule evaluators can correctly mark the field as missing rather than mis-attribute the absence)
  - String values longer than `max_field_chars` are truncated with `... [truncated N chars]` suffix; rationale identical to the size-ceiling logic in PRC-013
  - Non-string field values are kept as-is in `fields` (the scorer / rules handle stringification at use site)
  - Result includes `metadata` dict with: `extraction_method`, `extracted_field_count`, `missing_field_count`, `truncated_field_count`
- [ ] No recursive descent into the state object beyond direct field access. The contract names what to look at; we look at exactly that.
- [ ] No attempt at PII redaction (the `__sensitive__` opt-out from the previous design is dropped; users who don't want a field extracted should not include it in the contract)

### Technical Notes
- This is a deliberate scope reduction from the original PRC-016. The previous design tried to serialise arbitrary state; this design extracts only what's contracted. The new design is ~40 lines instead of ~150, has no recursive descent, no special-cases for LangGraph message types, no Pydantic introspection, and no opt-out attribute mechanism.
- LangGraph already has its own checkpointing and state-snapshotting facilities. Precept does not need to replicate those.
- If a user wants to inspect/observe non-contracted fields, that is what the LangGraph tracing layer (or LangSmith, or LangFuse) is for - not Precept.
- Security implication: by only extracting contracted fields, Precept never sees data it doesn't need. Secrets accidentally included in state never reach our `ViolationEvent`, exporters, or the observatory.
- Edge case: a state field is itself a complex object (a Pydantic model, a list of messages). We do NOT recurse. The field value is captured as-is and `str()`-coerced at scoring/rule time. Users wanting structural extraction within nested objects must restructure their state to expose the leaf field directly to the contract.

### Testing Requirements
- Unit tests in `tests/unit/integrations/langgraph/test_extractor.py`:
  - Dict-shaped state: every contracted field extracted; uncontracted fields ignored
  - Object-shaped state (dataclass, Pydantic model): every contracted field extracted via attribute access
  - Missing field is recorded as `None` in `fields`, increments `missing_field_count`
  - Long string truncated; `truncated_field_count` reflects this
  - Nested object captured as-is (no recursion attempted); test asserts the nested structure is preserved
  - Uncontracted secrets in state are NEVER present in the resulting `HandoffPayload` (regression test against the previous design's failure mode)
  - State containing a LangGraph `HumanMessage` in an uncontracted field is not extracted (test confirms uncontracted message content is never read)
- Property-based test: arbitrary dict states with arbitrary contracts produce `HandoffPayload` with `len(fields) == len(required_fields ∪ preserved_entities)` always

### Out of Scope
- Full state serialisation (deliberately removed)
- Sensitive-attribute opt-out (`__sensitive__`) - replaced by the much stronger guarantee that uncontracted fields are never read
- PII detection
- LangGraph message-type special handling (uncontracted state fields are never touched; contracted fields containing message objects are passed through)
- Round-trip deserialisation

### Definition of Done
- Tests pass; the regression test confirming uncontracted secrets are never extracted is the gating criterion

---

## PRC-017: Synthetic demo fixture traces (clean + degraded)

**Epic:** E5. Demo Pipeline & Fixtures
**Type:** feat
**Priority:** P0
**Effort:** M (6-8h)
**Sprint:** 2
**Dependencies:** PRC-006
**Co-designed with:** PRC-018 (contracts and fixtures must be authored together; recommend picking up both tickets at once and merging them in a single PR to prevent shape drift)

### Context
The demo needs high-quality synthetic fixtures (per Q10 answer). Two traces: a clean handoff where all contracts pass, and a degraded handoff where the summariser drops a key entity. Fixtures are stored as JSON files, deterministic, and shippable with the repo so reviewers can run the demo without any API keys.

**Co-design note:** the original ticket structure listed PRC-018 (contract YAMLs) as depending on PRC-017 (fixtures), which created a sequencing problem - co-designing both prevents the "mismatched fixtures + contracts" problem that the ticket itself warned against. Treat PRC-017 and PRC-018 as a single logical unit of work delivered in one PR.

### Acceptance Criteria
- [ ] `examples/fixtures/clean_trace.json` and `examples/fixtures/degraded_trace.json` committed
- [ ] Each trace contains a 3-hop pipeline: `researcher → summariser → writer`
- [ ] Each trace has, per hop:
  - `source_payload`: structured fields present before handoff (e.g., `{hypothesis, citations, primary_source, uncertainty_bounds, author}`)
  - `target_payload`: structured fields present after handoff
  - `handoff_metadata`: `{source_agent, target_agent, contract_name, timestamp_iso}`
- [ ] Clean trace: every contract passes when evaluated
- [ ] Degraded trace: at the summariser → writer boundary, the `primary_source` entity is dropped AND `uncertainty_bounds` field is missing, triggering two rule violations
- [ ] Fixture content is realistic: a research question about (e.g.) renewable energy adoption trends, with plausible hypotheses, citations, and summaries - not lorem ipsum. A reviewer reading the trace should understand what the agent pipeline is doing.
- [ ] `tests/fixtures/conftest.py` loads both fixtures as pytest fixtures `clean_trace` and `degraded_trace`

### Technical Notes
- Fixtures are the demo's "data foundation". Sloppy fixtures (nonsense text, empty fields) undermine every downstream signal. Invest time here; reviewers may open the JSON file.
- Keep fixtures small enough to read in one screen (~50 lines each) but rich enough to trigger every rule type on at least one boundary.
- Consider but defer: a fixture generator script that derives degraded traces from a clean base by applying named degradations. Useful for scaling tests; not MVP.

### Testing Requirements
- Unit tests: each fixture loads as valid JSON and conforms to the expected schema (a `TraceFixture` Pydantic model in the test module)
- Integration test in `tests/integration/test_fixtures.py`:
  - Running the evaluator on `clean_trace` produces no violations
  - Running the evaluator on `degraded_trace` produces the expected two violations at the summariser → writer boundary

### Out of Scope
- Fixture generator script
- More than 2 fixtures (one clean, one degraded is sufficient for demo; more dilutes focus)

### Definition of Done
- Fixtures committed, tests pass, manual review of content confirms realism

---

## PRC-018: Demo contract files (YAML) aligned with fixtures

**Epic:** E5. Demo Pipeline & Fixtures
**Type:** feat
**Priority:** P0
**Effort:** S (3h)
**Sprint:** 2
**Dependencies:** PRC-007
**Co-designed with:** PRC-017 (contracts and fixtures must be authored together; pick up both tickets at once and merge in a single PR to prevent shape drift)

### Context
The contracts used in the demo must match the fixture payload shapes exactly. Mismatched fixtures + contracts is a common source of confusing demo failures. Co-designing them as one ticket prevents drift.

**Co-design note:** PRC-017 and PRC-018 were originally structured with PRC-018 depending on PRC-017. In practice, neither ticket can be completed without the other being simultaneously adjusted. Treat as a single logical work unit; the dependency on PRC-007 (YAML loader) remains the only hard blocker.

### Acceptance Criteria
- [ ] `examples/contracts/researcher_to_summariser.yaml`: requires `hypothesis`, `citations`; preserves `primary_source`, `author`; min_fidelity `0.75`; forbids dropping `uncertainty_bounds`; mode `block`
- [ ] `examples/contracts/summariser_to_writer.yaml`: requires `summary`, `key_entities`; preserves `primary_source`; min_fidelity `0.70`; forbids dropping `uncertainty_bounds`; mode `block`
- [ ] Both files load successfully via `load_contract()`
- [ ] Contract names match exactly the `contract_name` values in the fixture `handoff_metadata`
- [ ] When the clean fixture is evaluated against these contracts, zero violations occur
- [ ] When the degraded fixture is evaluated, exactly the expected violations occur (PRC-017 defines which)

### Technical Notes
- Keep the contract files identical in structure so a developer reading both understands the pattern quickly.
- Add comments in the YAML explaining each field's purpose; YAML comments are lost on round-trip with `pyyaml` but useful for humans reading the file on disk.

### Testing Requirements
- Unit: each contract file loads correctly
- Integration (combined with PRC-017): end-to-end evaluation produces expected violation pattern

### Out of Scope
- A third "edge case" contract (scope creep; two is enough)

### Definition of Done
- Files committed, end-to-end round-trip verified

---

## PRC-019: Demo runner script `examples/demo.py`

**Epic:** E5. Demo Pipeline & Fixtures
**Type:** feat
**Priority:** P0
**Effort:** M (6h)
**Sprint:** 2
**Dependencies:** PRC-014, PRC-015, PRC-017, PRC-018

### Context
The demo runner is the single command a reviewer types to see Precept work. It must run in under 30 seconds on a fresh clone with no API keys, produce clear console output showing each handoff and its contract outcome, and write a JSON trace file that the observatory (PRC-022) renders. If the demo is flaky or slow, the MVP is not shippable.

### Acceptance Criteria
- [ ] `examples/demo.py` is a single runnable Python file, executable via `python examples/demo.py [--trace clean|degraded] [--output path]`
- [ ] Default invocation (no args) runs the degraded trace through the evaluator and writes output to `examples/output/demo_trace.json`
- [ ] Console output shows:
  - Banner with Precept version and trace name
  - For each handoff: source agent → target agent, contract name, pass/fail indicator, score, top violation reason if failed
  - Final summary: total handoffs, passed, failed, time taken
  - Pointer to the observatory: "Open `docs/index.html` and drop `examples/output/demo_trace.json` to view details"
- [ ] **Exit codes follow Unix convention**: `0` on successful run (demo completed end-to-end, regardless of whether the trace contained violations - a degraded trace producing violations IS a successful demo run); `2` on actual runtime error (contract not loadable, fixture missing, unexpected exception). Violations are communicated via stdout summary and the output JSON, not exit code. Rationale: a reviewer running `python examples/demo.py` and seeing exit code `1` will assume the script crashed.
- [ ] Final summary line includes an explicit indicator: "DEMO COMPLETED (N violations detected)" on exit 0 with violations, "DEMO COMPLETED (no violations)" on clean trace, "DEMO FAILED: <reason>" on exit 2
- [ ] No network calls other than the one-time sentence-transformer model download (which caches to `~/.cache/huggingface/`)
- [ ] Deterministic: running the same trace twice produces byte-identical output JSON

### Technical Notes
- Use `argparse`, not `click` or `typer`. One fewer dependency. The demo is tiny.
- Output JSON must be human-readable: `json.dump(..., indent=2, sort_keys=True)`.
- Do NOT wire this into a real LangGraph pipeline at v0. The demo reads fixtures and calls the evaluator directly - it is the contract engine demo, not the LangGraph runtime demo. LangGraph integration tests (PRC-014) cover that path. Per Q9 answer, this separation is deliberate.
- Exit code rationale documented in the script's docstring so future contributors don't "fix" it back to 0-or-1 based on violation count.

### Testing Requirements
- Unit tests in `tests/integration/test_demo.py`:
  - Run the demo script via `subprocess`, assert exit code 0 for both clean and degraded traces
  - Parse output JSON, verify it contains expected violation events for the degraded trace
  - Verify byte-identical output on repeat runs
  - Introduce an intentional runtime error (e.g., delete the fixture just before run); assert exit code 2
- Manual: run on fresh clone, time the full invocation (target < 30s including first-run model download)

### Out of Scope
- Interactive demo (TUI, web app)
- Live LLM pipeline demo (Phase 2, after stabilising the core)
- CLI subcommands beyond trace selection

### Definition of Done
- Demo runs in under 30s on CI, exit-code convention verified (0 on success regardless of violations, 2 on runtime error), output JSON valid, reviewer can interpret result without looking at exit codes

---

# Sprint 3: Telemetry Exporters + Observatory

---

## PRC-020: OpenTelemetry GenAI exporter (`gen_ai.evaluation.result`)

**Epic:** E6. Telemetry Exporters
**Type:** feat
**Priority:** P1
**Effort:** L (8-10h)
**Sprint:** 3
**Dependencies:** PRC-013 (for `Exporter` ABC and `ViolationEvent.to_compact_dict()`)

### Context
OTel GenAI semantic conventions (as of April 2026, status: Development / experimental) define `gen_ai.evaluation.result` as the canonical event for scoring/evaluation outcomes, attached to an `invoke_agent` span. Aligning Precept's output with this spec means every major observability vendor (Datadog, Grafana, Honeycomb, etc.) can consume Precept events without custom integration. This is a high-leverage cheap win and per Q12 is the primary export format.

### Acceptance Criteria
- [ ] `src/precept/exporters/otel.py` defines `OTelExporter(Exporter)` class inheriting from the ABC in `precept.exporters.base`
- [ ] Class attribute: `name = "otel"`
- [ ] Constructor: takes an optional OTel `Tracer` and `EventLogger`; falls back to globally configured defaults
- [ ] Imports of `opentelemetry.sdk.*` are done at import-time inside the module, guarded by try/except: if import fails, the module-level `OTelExporter` becomes a stub class that raises a clear `ImportError` on instantiation with message: `"OTelExporter requires the 'otel' extra. Install via: pip install precept[otel]"`. This import-guard pattern means `import precept.exporters` does not fail for users without the extra.
- [ ] Method `export(event: ViolationEvent) -> None` emits:
  - A `gen_ai.evaluation.result` event with attributes built from `event.to_compact_dict()` (ensuring the 4KiB ceiling is pre-applied). Required attributes: `gen_ai.evaluation.name` (= `contract_name`), `gen_ai.evaluation.score.value` (= `event.score_result.overall_score`), `gen_ai.evaluation.score.label` (= `"passed"` or `"failed"`), `gen_ai.evaluation.explanation` (violation reason or empty), plus Precept-specific attributes under namespace `precept.*`: `precept.contract.version`, `precept.mode`, `precept.event.id`
  - If `to_compact_dict()` returned with `precept.payload_truncated: True`, this flag propagates as an OTel attribute so downstream tooling can surface the truncation
  - Event is attached to the current active span if one exists; otherwise recorded with a synthetic `invoke_agent` span
- [ ] Follows OTel semantic conventions stability opt-in pattern: respects `OTEL_SEMCONV_STABILITY_OPT_IN` env var; by default emits the v1.36+ convention names
- [ ] Does NOT capture full payload content as default (OTel guidance: content is opt-in via `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=True`)
- [ ] Resilient per `Exporter` ABC contract: OTel SDK not configured → logs debug message, does not raise; individual attribute-emit failures caught and logged
- [ ] Per-attribute size check: OTel has a soft limit of ~4 KiB per attribute across major backends. Any attribute exceeding this is individually truncated with a suffix `"...[truncated]"` before emission. This is a second line of defence on top of the event-level ceiling in PRC-013.

### Technical Notes
- OTel GenAI is experimental. Document the schema version Precept emits (e.g., "Aligned with opentelemetry-semantic-conventions v1.37.x"). If the spec changes post-MVP, version-bump Precept's emitted schema explicitly, do not silently migrate.
- Reference [OTel GenAI semantic conventions spec](https://opentelemetry.io/docs/specs/semconv/gen-ai/) in the module docstring.
- Import-guard pattern is the key to PRC-026's promise that `from precept import ...` works for users without the OTel extra. The import of `OTelExporter` from `precept.exporters` must never fail at base-install time; only instantiation does.
- Attribute size enforcement has two tiers: (1) event-level in `ViolationEvent.to_compact_dict()` ensures the total payload stays under ~4 KiB; (2) per-attribute enforcement here catches any single attribute that grew too large even within a compliant total (e.g., one very long `gen_ai.evaluation.explanation`). Redundant but cheap.

### Testing Requirements
- Unit tests in `tests/unit/exporters/test_otel.py`:
  - Event is emitted with correct attribute keys and types
  - Attributes match the OTel GenAI spec for evaluation events
  - Exporter works when no tracer is configured (no raise)
  - Content capture is off by default, on when env var set
  - `precept.payload_truncated` attribute appears on event when truncation occurred upstream
  - Synthetically large single attribute (e.g., 10 KiB explanation string) is truncated to under 4 KiB with suffix
  - Module-level import of `precept.exporters.otel` does not fail when `opentelemetry.sdk` is not installed (simulate via `sys.modules` patching in test)
  - Instantiation of `OTelExporter` without the SDK installed raises `ImportError` with the documented install-hint message
- Integration test with `opentelemetry-sdk` `InMemorySpanExporter`: run demo, verify events captured match expected shape

### Out of Scope
- Native integrations with specific vendors (Datadog, etc.) - OTel standardisation is the integration surface
- Trace propagation across supervisor handoffs (interesting Phase 2 work for end-to-end agent tracing)

### Definition of Done
- Tests pass, event shape manually verified against a real OTel collector, import-guard pattern confirmed working on a base install without the `otel` extra

---

## PRC-021: Plain JSON exporter (backup / file writer)

**Epic:** E6. Telemetry Exporters
**Type:** feat
**Priority:** P1
**Effort:** S (3h)
**Sprint:** 3
**Dependencies:** PRC-013 (for `Exporter` ABC)

### Context
Not every deployment has OTel configured. A plain JSON exporter writes events to a file or stream, consumable by the observatory (PRC-022) and by any log-based analysis tool. Per Q12, this is the backup / optionality layer.

### Acceptance Criteria
- [ ] `src/precept/exporters/json_exporter.py` defines `JSONFileExporter(Exporter)` and `JSONStreamExporter(Exporter)` classes inheriting from the ABC in `precept.exporters.base`
- [ ] Class attributes: `name = "json_file"` and `name = "json_stream"` respectively
- [ ] `JSONFileExporter(path: str | Path, mode: Literal["append", "overwrite"] = "append")`: writes newline-delimited JSON (one event per line, JSONL format)
- [ ] `JSONStreamExporter(stream: IO[str])`: writes JSONL to any writable text stream (stdout, StringIO, etc.)
- [ ] Both exporters serialise `ViolationEvent` via `event.model_dump(mode='json')` and add a `schema_version` field at top level of each event (note: different from the internal `to_compact_dict()` used by OTel - JSON exporter writes full event, not the size-ceiled version, because file storage has no per-event size limit)
- [ ] `JSONFileExporter` creates parent directory if missing
- [ ] Thread-safe (events from concurrent evaluators do not interleave within a line; use `threading.Lock`)
- [ ] Per `Exporter` ABC contract: transport failures (disk full, permission denied) are logged and swallowed; never raised back to the evaluator

### Technical Notes
- JSONL (one JSON object per line) is the right format: streamable, greppable, tool-friendly (`jq`, `duckdb`, `pandas.read_json(lines=True)`).
- Include `schema_version` from day one; migrating log files in Phase 2 without a version field is painful.
- Flush after every write. Buffering improves throughput but costs data on crash; observability events should survive crashes.
- JSON exporter intentionally uses full `model_dump()` output (not `to_compact_dict()`). File storage is not size-constrained; a full event is more useful for post-hoc analysis. OTel is where size ceilings matter.

### Testing Requirements
- Unit tests in `tests/unit/exporters/test_json.py`:
  - Events write correctly, one per line, parseable as JSONL
  - Parent directory created if missing
  - Concurrent writes from threads do not corrupt file
  - `overwrite` mode truncates existing file; `append` mode extends
  - Transport failure (patched OSError on write) is logged and swallowed; evaluator not impacted

### Out of Scope
- JSON-over-HTTP exporter (Phase 2)
- Compression (gzip rotation)

### Definition of Done
- Tests pass, file output validated with `jq`, inherits from `Exporter` ABC, swallows failures per contract

---

## PRC-022: Static HTML observatory (single-page viewer)

**Epic:** E7. Static Observatory
**Type:** feat
**Priority:** P1
**Effort:** L (10-12h)
**Sprint:** 3
**Dependencies:** PRC-017, PRC-018, PRC-019, PRC-021

### Context
The observatory is the VC-legible visual artefact. A single HTML file that loads a JSON trace and renders: the pipeline topology (supervisor → specialists), each handoff with pass/fail, detailed violation info on click, and the "impact" summary. Per Q11, static. Per the overall MVP logic, this is the demo's visual payload and the README's primary link target.

### Acceptance Criteria
- [ ] `docs/index.html` is a single file; no build step, no npm install
- [ ] Uses only CDN-hosted libraries: a small CSS framework (e.g., Tailwind CDN or raw CSS), a tiny JS library for interactivity if needed (vanilla JS is preferred - keeps the footprint negligible)
- [ ] Default view: loads `examples/output/demo_trace.json` relative to the HTML file (useful when served from GitHub Pages)
- [ ] File upload UI: drag-and-drop a local `*.json` trace file to render without uploading anywhere
- [ ] Rendered view includes:
  - Header: trace name, total handoffs, passed/failed count, timestamp
  - Pipeline diagram: horizontal chain of agent boxes with arrows between (SVG or CSS flexbox)
  - Arrows are colour-coded: green for passing handoff, red for failed, yellow for warn-mode-failed
  - Click on an arrow → modal/detail panel showing: source payload summary, target payload summary, contract requirements, rule results (each rule pass/fail with reason), embedding scores per field, impact summary
  - Footer: Precept version, link to repo
- [ ] Responsive: renders on a 1280x720 display (laptop) and on a typical mobile viewport
- [ ] No analytics, no tracking, no external requests beyond the CDN libraries

### Technical Notes
- The temptation is to reach for React, Vue, D3. Resist. This is a single-page renderer of a fixed-shape JSON file. Vanilla JS + CSS keeps the file under 50KB and trivially auditable.
- Accessibility: include ARIA labels on interactive elements; semantic HTML (nav, main, section); reasonable colour contrast. Accelerator reviewers using accessibility tools should not hit obvious failures.
- Defer until needed: time-series view, multi-trace comparison, search. For v0, one trace, one view.

### Testing Requirements
- Manual cross-browser: Chrome, Firefox, Safari (latest stable)
- Manual accessibility: run axe-core or Lighthouse; no critical failures
- Snapshot test (Playwright or Selenium, added to CI or run locally): load `docs/index.html` with `demo_trace.json`, assert the rendered DOM contains the expected handoff rows

### Out of Scope
- Dark mode (can be trivially added via CSS media query but skip if time-constrained)
- Multi-trace timeline
- Real-time streaming (that's a hosted app, not a static observatory)

### Definition of Done
- File opens in any browser, renders both fixtures correctly, visual review by Gian passes

---

## PRC-023: GitHub Pages deployment of observatory and docs

**Epic:** E7. Static Observatory
**Type:** infra
**Priority:** P1
**Effort:** S (2-3h)
**Sprint:** 3
**Dependencies:** PRC-022

### Context
The observatory needs a public URL so the README can link to it. GitHub Pages is free, fast, and requires no additional infrastructure. A single workflow publishes `docs/` to Pages on merges to `main`.

### Acceptance Criteria
- [ ] `.github/workflows/pages.yml` publishes the `docs/` directory to GitHub Pages on pushes to `main`
- [ ] Uses official `actions/deploy-pages@v4` (or latest stable as of 2026)
- [ ] Custom 404 page (`docs/404.html`) with link back to the repo
- [ ] Repo settings: Pages enabled, source set to the `gh-pages` branch or workflow-driven deployment
- [ ] README links to the published Pages URL
- [ ] The published site loads `demo_trace.json` from the same directory (relative path, works regardless of custom domain)

### Technical Notes
- Workflow should have `concurrency: group: pages` to prevent overlapping deploys.
- If a custom domain is desired later (`precept.dev` etc.), document the CNAME + DNS steps in `docs/architecture.md` but do not purchase a domain during MVP.

### Testing Requirements
- Deploy to Pages, verify URL loads, verify `/demo_trace.json` loads from the Pages URL

### Out of Scope
- Custom domain purchase (can wait)
- Preview deploys for PRs (Phase 2)

### Definition of Done
- Observatory URL live, linked from README

---

# Sprint 4: Documentation + Release

---

## PRC-024: README with positioning, quickstart, competitive contrast, and A2A roadmap note

**Epic:** E8. Documentation & Release
**Type:** docs
**Priority:** P0
**Effort:** L (8-10h)
**Sprint:** 4
**Dependencies:** PRC-019, PRC-022, PRC-023

### Context
The README is the single most important artefact for reviewer impression. It must answer in under 30 seconds of scanning: what is this, why do I care, how do I try it, where does it fit. Per Q1 the headline is "handoff integrity contracts". Per Q15 the README explicitly contrasts against adjacent tools. Per Q13 the README mentions A2A as a Phase 2 roadmap item. Per overall decisions, the scorer is presented as an embedding-based proxy with a research-validated scorer coming from the dissertation.

### Acceptance Criteria
- [ ] Title and one-line positioning: "Precept - handoff integrity contracts for multi-agent pipelines"
- [ ] Hero section (above the fold): one-paragraph summary, a 3-line code snippet showing decorator usage, and a link to the live observatory URL (PRC-023)
- [ ] "Why Precept" section (~150 words): the problem (boundary information loss in multi-agent pipelines), the gap (output-observability and action-governance tools do not check inter-agent information fidelity at inputs), the approach (declarative contracts + scored evaluation)
- [ ] Quickstart section: pip install, first contract (YAML), first evaluation snippet (Python), link to the demo
- [ ] "How it compares" section (per Q15 decision, explicit contrast):
  - Langfuse / LangSmith / Arize Phoenix: observability on agent execution traces. Precept contracts the information that crosses handoffs, independent of whether it is traced.
  - Guardrails AI / Pydantic AI: schema validation on a single LLM output. Precept evaluates agent-to-agent payloads, not single-call outputs.
  - Microsoft Agent Governance Toolkit: policy governance on agent actions and outputs. Precept operates on inter-agent information integrity; the two address different risk surfaces.
  - Behavioural-contract tools (agentcontract/spec, relari-ai/agent-contracts): contract agent behaviour. Precept contracts the information that must persist between agents.
  - A one-paragraph note on A2A: "Precept v0 targets LangGraph. The Agent-to-Agent protocol (A2A v1.0, April 2026) is the emerging cross-vendor inter-agent standard; mapping Precept contracts to A2A `Message`/`Part`/`Artifact` concepts is tracked as a Phase 2 work stream (see issues PRC-031 to PRC-033)."
- [ ] "Scorer status" section (short, honest): "v0 uses an embedding-similarity proxy scorer. This produces directionally useful scores but is not a mutual-information-theoretic measurement. A research-validated calibrated scorer is the deliverable of an MSc dissertation (Apr-Aug 2026); integration is tracked as Phase 2 (PRC-034 to PRC-036)."
- [ ] Roadmap section: brief Phase 1 (MVP) / Phase 2 (deferred) summary with links to issue numbers or milestone
- [ ] Footer: licence (MIT), contact, link to CONTRIBUTING.md, badge row (CI, PyPI version once published, licence)
- [ ] No claims the tool does not support; no vapourware. Every capability mentioned in README must be verifiable by a reader running the demo.

### Technical Notes
- Write the README in a way that scans well: short paragraphs, bold the first sentence of each section, use code fences with syntax highlighting.
- The "how it compares" section is defensive positioning; a reviewer who has seen Langfuse will conflate without it. Do not caricature competitors; factual contrast wins credibility.
- Do not try to be funny. Technical reviewers find jokes in READMEs irritating at best.

### Testing Requirements
- Markdown lint (via `markdownlint-cli` or similar) passes
- Every code snippet in the README must execute without modification (run as integration test in `tests/integration/test_readme_snippets.py` using `pytest-examples` or manual extraction)
- Every internal link works; every external link returns HTTP 200

### Out of Scope
- Screenshots of the observatory (nice to have; add if time)
- Architecture diagrams (belong in `docs/architecture.md`, linked from README)

### Definition of Done
- README merged, all code snippets verified executable, all links valid

---

## PRC-025: Architecture document and contract reference

**Epic:** E8. Documentation & Release
**Type:** docs
**Priority:** P1
**Effort:** M (6h)
**Sprint:** 4
**Dependencies:** PRC-005, PRC-006, PRC-011

### Context
Beyond the README's marketing surface, serious readers (prospective contributors, enterprise evaluators, technical accelerator reviewers) want a deeper architecture document and a complete reference for the contract DSL. These live under `docs/`.

### Acceptance Criteria
- [ ] `docs/architecture.md` covers:
  - High-level diagram (mermaid or ASCII) showing the IR + multiple-frontends + evaluator + exporters pattern
  - Component responsibilities: contract module, scoring module, evaluator, integration layer, exporters, observatory
  - Data flow for a single handoff evaluation (step-by-step)
  - Extension points: new frontend (add a parser producing IR), new scorer (subclass `Scorer`), new integration (wrap framework-specific handoff creation), new exporter (consume `ViolationEvent`)
  - Known limitations of v0 (fail-open on missing contract, proxy scorer accuracy caveats, substring entity matching)
- [ ] `docs/contract_reference.md` is the authoritative reference for the YAML contract DSL:
  - Every field with type, default, constraints, example
  - Full examples of each mode (block, warn)
  - Migration notes for future schema versions (placeholder, populated as schemas evolve)
- [ ] `docs/competitive_landscape.md`: expanded version of the README "how it compares" section, with more depth, citations, and a "positioning" framing suitable for accelerator and investor conversations

### Technical Notes
- Architecture doc should be readable end-to-end in 10 minutes. Diagrams pay off here.
- Contract reference should be usable as a lookup table; headings and anchors for every field.

### Testing Requirements
- Markdown lint passes
- Diagrams render correctly on GitHub

### Out of Scope
- API reference for Python (auto-generated from docstrings by `mkdocs` / `sphinx` - Phase 2)

### Definition of Done
- Docs merged, linked from README, contract reference matches PRC-006 schema exactly

---

## PRC-026: Public API surface and `__init__.py` exports

**Epic:** E8. Documentation & Release
**Type:** feat
**Priority:** P0
**Effort:** S (3h)
**Sprint:** 4
**Dependencies:** PRC-006, PRC-008, PRC-013, PRC-014

### Context
Before v0.1.0 ships, lock down what is public API (committed to semantic versioning) and what is internal. A sloppy public surface becomes a migration burden the moment users show up. Python lacks a hard distinction, so convention is the tool: `__all__` in top-level `__init__.py`, plus an explicit `_` prefix on internal modules. Additionally, the OTel exporter is an optional dependency and MUST NOT be importable from the top-level `precept` namespace, because that would cause `from precept import OTelExporter` to fail for users who haven't installed `precept[otel]`.

### Acceptance Criteria
- [ ] `src/precept/__init__.py` defines `__all__` containing exactly: `HandoffContract`, `ContractFields`, `ViolationEvent`, `ScoreResult`, `FieldScore`, `RuleResult`, `HandoffPayload`, `Scorer`, `EmbeddingProxy`, `Evaluator`, `Exporter`, `NoOpExporter`, `MultiExporter`, `handoff_contract`, `load_contract`, `load_contract_from_string`, `ContractRegistry`, `default_registry`, `HandoffBlockedError`, `ContractValidationError`, `__version__`
- [ ] `precept.integrations.langgraph` exports: `create_precept_handoff_tool`, `evaluate_handoff`, `extract_payload`
- [ ] `precept.exporters` exports: `Exporter`, `NoOpExporter`, `MultiExporter`, `JSONFileExporter`, `JSONStreamExporter` - but **NOT** `OTelExporter`. Users who want OTel explicitly import via `from precept.exporters.otel import OTelExporter`. This ensures base-install users never trigger the ImportError surface.
- [ ] `precept.exporters.__init__` MUST NOT contain `from .otel import *` or equivalent; the `otel` module is imported only on explicit request
- [ ] Internal modules documented in `docs/architecture.md` with explicit "not public API" warning
- [ ] Every public class / function has a docstring; mypy --strict clean; linter clean
- [ ] API surface review: a "fake user" walkthrough documented in `docs/api_surface_review.md`: list every public entry point and state the semantic versioning commitment (semver major = breaking change to these; semver minor = additive)
- [ ] Import-surface smoke test: on a fresh venv with ONLY `pip install precept` (no extras), verify that `import precept`, `from precept import Evaluator`, `from precept.exporters import JSONFileExporter` all succeed WITHOUT raising `ImportError`. Verify that `from precept.exporters.otel import OTelExporter` raises `ImportError` with the documented install-hint message.

### Technical Notes
- Restraint is expensive upfront but saves migration pain. Every class in `__all__` is a semver commitment.
- If in doubt, do NOT export. Internal now, public later is easy. Public now, internal later is a breaking change.
- The OTelExporter exclusion from top-level exports is the resolution of a real bug: the earlier draft listed it in `__all__`, which would have caused `from precept import *` and similar wildcard-import patterns to trip the OTel import-guard surface on base installs. Users who want OTel type-check their imports explicitly.
- `Exporter` ABC is in `__all__` because users writing custom exporters need it. `NoOpExporter` and `MultiExporter` are in `__all__` because composing exporters is a normal configuration action.

### Testing Requirements
- Unit test in `tests/unit/test_api_surface.py`:
  - Every name in `__all__` is importable from `precept`
  - `from precept import *` imports only names in `__all__`
  - No module beginning with `_` is reachable from public API
  - `OTelExporter` is NOT in `__all__` (explicit negative assertion - regression test)
  - `from precept.exporters.otel import OTelExporter` raises clear `ImportError` when `opentelemetry.sdk` is not installed (simulate via `sys.modules` patching)
- Fresh-environment smoke test (runs in CI):
  - Fresh venv, `pip install precept` (no extras), run: `python -c "import precept; from precept import Evaluator, EmbeddingProxy; from precept.exporters import JSONFileExporter"` - must exit 0
  - Same venv, run: `python -c "from precept.exporters.otel import OTelExporter"` - must exit non-zero with ImportError
  - Fresh venv, `pip install precept[otel]`, run the OTel import - must exit 0

### Out of Scope
- API stability guarantee doc (implicit in README + semver discipline)

### Definition of Done
- Tests pass, `__all__` reviewed, surface documented, import-surface smoke test passes on fresh venv

---

## PRC-027: Release checklist, CHANGELOG, PyPI publish workflow

**Epic:** E8. Documentation & Release
**Type:** infra
**Priority:** P0
**Effort:** M (4-5h - reduced because PRC-004a pre-configured the OIDC surface)
**Sprint:** 4
**Dependencies:** PRC-004a (OIDC publishers already configured), all MVP issues

### Context
v0.1.0 release is the finish line. Shipping requires: bumping version, updating CHANGELOG, tagging, building distributions, publishing to PyPI, verifying the published package installs and runs the demo on a fresh environment. Automation reduces the chance of human error in what should be a repeatable process. PRC-004a already configured the PyPI and TestPyPI OIDC trusted publishers in Sprint 0, so this ticket focuses purely on the release workflow authoring and the first real release.

### Acceptance Criteria
- [ ] `.github/workflows/release.yml` triggered on tag push matching `v*.*.*`:
  - Verifies tag version matches `pyproject.toml` version
  - Runs full CI (lint, type, test)
  - Builds sdist and wheel via `python -m build`
  - Publishes to PyPI using the OIDC trusted publisher (already configured per PRC-004a). Uses the `pypi` GitHub environment (with reviewer protection gate).
  - Creates a GitHub Release with CHANGELOG contents for the tagged version
- [ ] `.github/workflows/release-testpypi.yml` with `workflow_dispatch` trigger (manual): publishes to TestPyPI using the `testpypi` GitHub environment. Used for dry-runs before tagging.
- [ ] `docs/release_process.md` extends PRC-004a's documentation with: the pre-release checklist (CHANGELOG updated, version bumped, all MVP tickets closed, demo runs cleanly on fresh environment, observatory URL works), the dry-run procedure via `release-testpypi.yml`, the tag-and-release procedure, and the rollback plan (yank on PyPI, revert commits, hotfix patch version)
- [ ] `CHANGELOG.md` has a `[0.1.0]` section enumerating all shipped features at MVP boundary, linked to issue numbers
- [ ] Fresh-environment smoke test: a documented procedure (also runnable as a CI job on release) that: creates a new venv, `pip install precept==0.1.0`, downloads and runs the demo, verifies output
- [ ] Import-surface smoke test from PRC-026 runs as part of release verification on both fresh base install AND fresh `[otel]` install

### Technical Notes
- Trusted publishing OIDC is already set up (PRC-004a). This ticket only authors the workflow that uses it. Zero-to-release time should be under 30 minutes of human effort on day 10.
- Do NOT include test data, examples, or fixtures in the published wheel (configure `MANIFEST.in` or pyproject `[tool.setuptools]` excludes). Users do not need them; keeps the wheel small.
- Sign releases with `sigstore` if time permits (Phase 2 nice-to-have).
- Rollback plan is non-optional documentation. At the first security advisory against Precept (inevitable at some scale), having the rollback runbook already written saves hours of panic.

### Testing Requirements
- Dry-run release to TestPyPI via `workflow_dispatch` before tagging v0.1.0
- Fresh-environment smoke test passes on Linux and macOS, both with and without `[otel]` extra
- Import-surface smoke test (PRC-026) confirms base install does not trigger OTel ImportError

### Out of Scope
- conda-forge package (community-maintained; Phase 2)
- Signed releases (Phase 2)
- Automated version bumping (manual for v0; consider `release-please` in v0.2)

### Definition of Done
- v0.1.0 published to PyPI, installable via `pip install precept`, fresh smoke test passes on base AND `[otel]` installs, GitHub Release created, observatory URL live, rollback runbook committed

---

# Phase 2: Deferred Work Streams

> Not scheduled. Labelled and scoped so they can be picked up as coherent epics post-MVP.

---

## PRC-028: Research folder literature map and dissertation plan scaffolding

**Epic:** E9. Phase 2 - Research Scaffolding
**Type:** research
**Priority:** P2
**Effort:** L (multi-day; dissertation-aligned)
**Sprint:** Phase 2
**Dependencies:** MVP shipped

### Context
Per decision on Q14, the `/Research` folder is scaffolded now (committed but as a skeleton pointer) and populated in Phase 2 as dissertation work progresses. The research folder is an external signal of research-company seriousness, particularly for EWOR-style reviewers.

### Acceptance Criteria
- [ ] `Research/README.md` pointer with sections: Research questions, Anchor publications, Testbed plan, Experiment configs, Expected outputs
- [ ] `Research/literature_map.md`: annotated bibliography of Cemri et al. (2025), Lin et al. (NeurIPS 2023), Hill et al. (NeurIPS 2025 workshop), Chen et al. (2024), Kraskov et al. (2004), Belghazi et al. (2018), Song and Ermon (2020), Poole et al. (2019), Balestriero and LeCun (2025)
- [ ] `Research/testbed_plan.md`: Melting Pot environment selection, SAC/PPO configurations, five information conditions, seed strategy
- [ ] `Research/experiment_configs/`: YAML configs for each of the five information conditions, checked in early as placeholders

### Technical Notes
- This ticket is dissertation-aligned work. Treat as a separate research track running in parallel with Precept engineering; do not pull engineers into it.
- The literature map must be accurate enough to withstand technical review; sloppy citations undermine the credibility signal.

### Testing Requirements
- Review by Gian and (if available) Prof Treleaven for technical accuracy

### Out of Scope
- Running experiments (dissertation scope; not software backlog)

### Definition of Done
- Scaffolding committed, literature map technically sound

---

## PRC-029: MARL testbed skeleton (Melting Pot, PettingZoo, SB3)

**Epic:** E9. Phase 2 - Research Scaffolding
**Type:** research
**Priority:** P2
**Effort:** XL (requires dedicated research sprint)
**Sprint:** Phase 2
**Dependencies:** PRC-028

### Context
The dissertation's Exp 1 requires a working MARL testbed: Melting Pot environment, PettingZoo wrapper, SB3 SAC/PPO agents, configurable observation function for the five information conditions. This skeleton lives in `Research/code/` so it is publicly visible but clearly marked as research infrastructure, not product.

### Acceptance Criteria
- [ ] `Research/code/testbed/` contains: environment registration for one Melting Pot scenario, PettingZoo wrapper, SAC and PPO config files, observation-function abstraction for five conditions, seed management
- [ ] Minimal "hello world" run: single seed, single condition, short training, logs episode returns
- [ ] README in `Research/code/` explains how to reproduce the run

### Technical Notes
- This is real research infrastructure with real compute implications. Budget accordingly.
- Do NOT commit training outputs / logs / checkpoints. Use `.gitignore` for the `outputs/` directory.

### Testing Requirements
- Single-seed "hello world" run succeeds on a Linux environment with GPU

### Out of Scope
- Full experiment sweep (that is the dissertation itself)

### Definition of Done
- Hello-world run reproducible by a fresh checkout

---

## PRC-030: Upgrade `preserved_entities_rule` to NER-based matching

**Epic:** E9. Phase 2 - Research Scaffolding
**Type:** feat
**Priority:** P2
**Effort:** M
**Sprint:** Phase 2
**Dependencies:** PRC-012 shipped

### Context
The v0 `preserved_entities_rule` uses case-insensitive substring matching. This has well-known failure modes (false positives on common substrings, missed morphological variants). Phase 2 upgrade: use a lightweight NER model (spaCy `en_core_web_sm` or similar) to extract entities from source and check presence in target.

### Acceptance Criteria
- [ ] Opt-in via a `method` parameter on `preserved_entities_rule`: `method: Literal["substring", "ner"] = "substring"`
- [ ] NER method requires `precept[ner]` extra which installs spaCy
- [ ] NER method produces entity extractions with type tags (PERSON, ORG, LOC); contract can optionally filter by type
- [ ] Calibration study comparing substring and NER methods on demo fixtures

### Out of Scope
- Custom NER model training

---

## PRC-031: A2A protocol mapping study

**Epic:** E10. Phase 2 - A2A Compatibility
**Type:** research
**Priority:** P2
**Effort:** L
**Sprint:** Phase 2
**Dependencies:** MVP shipped

### Context
A2A v1.0 (April 2026) is the emerging inter-agent standard. Before building anything, a mapping study establishes how Precept's `HandoffContract` IR relates to A2A's `Message`/`Part`/`Artifact`/`Task` primitives and where contracts would attach (on the Agent Card, on a Message, on a Task).

### Acceptance Criteria
- [ ] `docs/research/a2a_mapping.md`: formal mapping from every Precept IR field to A2A structures; identification of gaps (fields in Precept that have no A2A equivalent; fields in A2A that might inform future Precept additions)
- [ ] Sketch of Agent Card extension: how an A2A-compliant agent would declare which Precept contracts it expects/honours
- [ ] Decision on whether Precept contracts should live alongside the Agent Card (static, capability-level) or inside individual Task messages (dynamic, per-invocation), or both

### Out of Scope
- Implementation

### Definition of Done
- Mapping doc reviewed, decisions recorded as ADR

---

## PRC-032: A2A Agent Card extension for Precept contracts

**Epic:** E10. Phase 2 - A2A Compatibility
**Type:** feat
**Priority:** P2
**Effort:** L
**Sprint:** Phase 2
**Dependencies:** PRC-031

### Context
Implementation of the decision from PRC-031: a formal A2A Agent Card extension describing which Precept contracts an agent honours. Agents advertising the extension can be discovered as "contract-aware" by other agents in an A2A network.

### Acceptance Criteria
- [ ] A2A extension spec file under `docs/specs/a2a-precept-extension.md`
- [ ] `src/precept/integrations/a2a/` module providing helpers to generate Precept-compatible Agent Cards
- [ ] Example A2A agent in `examples/a2a/` using the extension
- [ ] Compatibility verified against the A2A v1.x spec

### Out of Scope
- Submitting the extension to the A2A standards process (that is a separate org-level effort)

---

## PRC-033: A2A inter-agent contract enforcement adapter

**Epic:** E10. Phase 2 - A2A Compatibility
**Type:** feat
**Priority:** P2
**Effort:** XL
**Sprint:** Phase 2
**Dependencies:** PRC-032

### Context
Runtime enforcement for A2A: a middleware that intercepts `SendMessage` calls, evaluates the outgoing Message against the contract declared in the destination Agent Card, and can block or warn per mode.

### Out of Scope for MVP
- All implementation

---

## PRC-034: Calibrated scorer interface finalisation (post-dissertation)

**Epic:** E11. Phase 2 - Calibrated Scorer Integration
**Type:** feat
**Priority:** P2
**Effort:** L
**Sprint:** Phase 2 (post Aug 2026)
**Dependencies:** Dissertation complete; MVP shipped

### Context
The dissertation reviews four MI estimation methods: KSG, Gaussian closed-form, InfoNCE, MINE. The calibrated scorer integration depends on which method(s) the dissertation validates as useful and with what calibration bounds.

### Acceptance Criteria
- [ ] `src/precept/scoring/calibrated.py` implements `CalibratedScorer(Scorer)` wrapping the dissertation's validated method(s)
- [ ] Calibration metadata available via `scorer.calibration_info()`: method name, bound type (upper/lower), bound tightness conditions, training data description
- [ ] Published calibration study reference in docstring and docs

### Out of Scope
- Choosing the method (that is dissertation work)

---

## PRC-035: Dual-track scorer plumbing (proxy online, calibrated offline)

**Epic:** E11. Phase 2 - Calibrated Scorer Integration
**Type:** feat
**Priority:** P2
**Effort:** L
**Sprint:** Phase 2
**Dependencies:** PRC-034

### Context
Production operation: the EmbeddingProxy runs synchronously (gates handoffs in real-time), the CalibratedScorer runs asynchronously on recorded traces (for audit and calibration). This is the dual-track architecture referenced in the original Precept positioning.

### Out of Scope for MVP
- All implementation

---

## PRC-036: Scorer benchmarking and calibration harness

**Epic:** E11. Phase 2 - Calibrated Scorer Integration
**Type:** feat
**Priority:** P2
**Effort:** L
**Sprint:** Phase 2
**Dependencies:** PRC-034

### Context
Systematic benchmarking of proxy vs calibrated scores across the five information conditions. Produces the calibration curves that justify the proxy's use in production.

### Out of Scope for MVP
- All implementation

---

# Critical Risks and Mitigations (MVP Scope)

| Risk | Severity | Likelihood | Mitigation | Owner |
|---|---|---|---|---|
| `langgraph_supervisor` API instability (issue #205 context) | High | Medium | Pin to `langgraph>=0.5,<0.7`, cite the known workaround in PRC-014, add integration smoke test that runs on every dep bump, AND provide the pure `evaluate_handoff()` hook as a framework-API-independent fallback | PRC-014 |
| Users on `Command(goto=...)` pattern find tool wrapper useless | Medium | High | PRC-014 now provides `evaluate_handoff()` pure function alongside the tool wrapper - both integration surfaces ship at v0 | PRC-014 |
| `sentence-transformers` first-run model download on restricted networks | Medium | Medium | Constructor-time loading means failure at instantiation, not at first handoff. Document the download in README; allow `model_name` override to a smaller model; pre-download into CI cache | PRC-011 |
| Async event loop blocking in `EmbeddingProxy.score()` | High | Medium (LangGraph is async-capable) | Constructor-time model load removes the multi-second cold-start spike; PRC-014's `evaluate_handoff()` auto-dispatches to `asyncio.to_thread` when called from inside a running loop; documented in PRC-011 | PRC-011, PRC-014 |
| OTel GenAI spec still experimental; attribute names may change | Medium | Medium | Pin to a specific spec version in module docstring; gate via `OTEL_SEMCONV_STABILITY_OPT_IN`; commit to emit-then-migrate rather than silent migration | PRC-020 |
| OTel payload exceeds backend attribute size limits (4 KiB typical) | High | Medium | Two-tier enforcement: event-level ceiling in `ViolationEvent.to_compact_dict()` (PRC-013) + per-attribute check in OTel exporter (PRC-020); `precept.payload_truncated` flag surfaces when truncation occurred | PRC-013, PRC-020 |
| `from precept import OTelExporter` fails on base install (no `[otel]` extra) | Medium | High if miswired | PRC-026 explicitly excludes `OTelExporter` from top-level `__all__` and `precept.exporters.__init__`; import-surface smoke test runs in CI on fresh venv | PRC-026 |
| Secret leakage via full state serialisation | High | Medium | PRC-016 rewritten to extract ONLY contracted fields; uncontracted state (which may contain secrets injected by users) is never read; regression test enforces this | PRC-016 |
| Proxy scorer producing embarrassingly bad scores on demo | High | Low | Hand-tune demo fixtures and thresholds during PRC-017/PRC-018; manual scorer tuning before release; score thresholds in YAML are adjustable | PRC-017, PRC-018 |
| README overclaiming MI rigour | High | Low if disciplined | PRC-024 explicit "Scorer status" section; every claim must be verifiable by running the demo; peer review before release | PRC-024 |
| Demo flakiness on CI due to model download time | Medium | Medium | Cache model in CI; allow model override to smaller model for test speed; generous timeouts; constructor-time load means fail-fast on network issues | PRC-003, PRC-019 |
| Day-10 release blocked by missing OIDC publisher setup | High | Was High, now Low | PRC-004a front-loads PyPI + TestPyPI OIDC configuration to Sprint 0; release workflow in PRC-027 simply consumes the pre-configured surface | PRC-004a |
| Demo exit code (1 on violations) misread as crash by Unix-convention reviewers | Medium | High | PRC-019 updated: always exit 0 on successful run regardless of violations; exit 2 reserved for actual runtime errors; final stdout line explicitly states outcome | PRC-019 |
| Circular dependency `HandoffBlockedError` ↔ impact templates | High | Was High, now N/A | `HandoffBlockedError` class moved to PRC-013 with default-empty `impact_summary`; PRC-015 is the independent populator; no circular reference | PRC-013, PRC-015 |
| Scope creep during build | High | High | Hard stop at end of Sprint 4 OR when release exit criteria all green, whichever later. Timeline may extend; quality bar does not move. | Gian |

---

# Release Exit Criteria (v0.1.0)

The release ships only when ALL of the following are verified:

1. **All P0 issues closed.** No "mostly done" on a P0 ticket.
2. **CI green on `main` for 24h** (no flakes).
3. **Demo runs in under 30s** on a fresh Linux environment and a fresh macOS environment, no API keys required, observatory renders the output, exit code 0 on both clean and degraded traces.
4. **README code snippets execute** (tested in `tests/integration/test_readme_snippets.py`).
5. **`pip install precept==0.1.0`** from TestPyPI then from real PyPI succeeds on Python 3.10, 3.11, 3.12 on Linux x86_64 and macOS ARM64.
6. **Base-install import surface works**: on `pip install precept` (no extras), `import precept` and all top-level `__all__` entries are importable without triggering ImportError; `from precept.exporters.otel import OTelExporter` raises the documented ImportError with install hint.
7. **Extras-install import surface works**: on `pip install precept[otel]`, `from precept.exporters.otel import OTelExporter` succeeds and the exporter is instantiable.
8. **Async-safety smoke test**: `evaluate_handoff()` called from inside an asyncio coroutine does not block the event loop measurably (regression test gate).
9. **Secret-leakage regression test** (PRC-016) passes: contracted-field extractor never reads uncontracted state, including state containing secret-like values.
10. **Coverage ≥ 80%** on `src/precept/contract/` and `src/precept/scoring/`.
11. **`mypy --strict` clean** across `src/precept/`.
12. **No `bandit` HIGH or MEDIUM findings** on the MVP scope.
13. **Observatory URL loads** and renders both demo traces.
14. **CHANGELOG entries** for all shipped features link to issue numbers.
15. **Rollback runbook** committed to `docs/release_process.md` (non-optional).
16. **Gian manually verifies** the demo as a "fake reviewer" in under 5 minutes with zero prior context on the repo.

Any single criterion failing defers release by at least 24h. Timeline is not a release gate; quality is.
