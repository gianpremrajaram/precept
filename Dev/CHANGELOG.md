# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial repository scaffolding: PEP 621 `pyproject.toml`, `src/precept/` package layout, `__version__` sourced via `importlib.metadata`, `test`, `docs`, and `dev` optional-dependency groups, and a root `.gitignore` covering Python, IDE, and OS artefacts (PRC-001).
- Continuous integration pipeline: `.github/workflows/ci.yml` with `lint` (ruff check + format), `typecheck` (mypy --strict), `security` (bandit), and `test` (pytest with coverage) jobs; test job matrixes across Python 3.10 / 3.11 / 3.12 on `ubuntu-latest`, other jobs pin to 3.12; per-job `working-directory: Dev`; coverage uploaded as a job artefact (PRC-003).
- Tool configuration in `pyproject.toml`: `[tool.ruff]`, `[tool.mypy]` (strict), `[tool.pytest.ini_options]`, and `[tool.coverage]` so CI commands stay thin and behaviour lives with the package config (PRC-003).
- CI status badge at the top of `README.md` (PRC-003).
- Smoke test `Dev/tests/test_smoke.py` verifying the installed package exposes a non-empty `__version__` (PRC-003).
- `CONTRIBUTING.md` at repo root: concise external-facing guide (<150 lines) covering dev setup, branch naming (`feat/`, `fix/`, `docs/`, `infra/`, `test/`, `research/`), Conventional Commits, PR flow, and pre-commit install commands; links out to `CLAUDE.md`, `ISSUES.md`, and `DEPENDENCIES.md` (PRC-002).
- `.github/PULL_REQUEST_TEMPLATE.md` with Summary / Linked issue / Testing / Checklist sections (PRC-002).
- `.github/ISSUE_TEMPLATE/bug_report.md` and `.github/ISSUE_TEMPLATE/feature_request.md` (PRC-002).
- LICENSE copyright year verified as 2026 (PRC-002).
- `.pre-commit-config.yaml` at repo root: file-hygiene (`trailing-whitespace`, `end-of-file-fixer`, `check-yaml`, `check-toml`, `check-merge-conflict`, `detect-private-key`) and `ruff` + `ruff-format` on commit; `mypy --strict` on pre-push to keep the commit loop fast. Ruff is pointed at `Dev/pyproject.toml` via `--config` for reliable discovery from repo-root invocation. Hook scope is repo-wide (PRC-004).
- ADR 0001 (`docs/adr/0001-contract-ir.md`) documenting the single-Pydantic-IR, multiple-frontends architecture with Mermaid + ASCII diagrams, non-goals (no runtime codegen, no dynamic schema extension, opaque version semantics), and explicit empty-contract (scaffold / observe-only) semantics; ADR index at `docs/adr/README.md`; linked from `README.md` and `CONTRIBUTING.md` (PRC-005).
- `precept.errors` module with `ContractValidationError` and structured `ContractValidationIssue` (Pydantic) carrying `field_path`, `message`, and optional `yaml_mark`; `ContractValidationError.from_pydantic` classmethod wraps `pydantic.ValidationError` uniformly (PRC-006, shared home for future `HandoffBlockedError` in PRC-013).
- `precept.contract.schema` with `HandoffContract` and `ContractFields` Pydantic v2 models; `extra="forbid"`, `name` regex (`^[a-z][a-z0-9_-]*$`), `mode: Literal["block", "warn"]`, bounded `min_fidelity` required when `preserved_entities` is non-empty, `required_fields`/`forbidden_drops` overlap rejection, list-duplicate rejection; `HandoffContract.__init__` wraps `pydantic.ValidationError` into `ContractValidationError`. Empty contracts (all three rule lists empty) are permitted as a deliberate scaffold mode per ADR 0001 (PRC-006).
- Shared Hypothesis strategies at `Dev/tests/unit/contract/strategies.py` (`valid_contract_names`, `valid_min_fidelity`, `valid_field_names`) reusable by PRC-008 and PRC-012 (PRC-006).
- Unit tests at `Dev/tests/unit/contract/test_schema.py` covering 38 cases including the required-when-preserved, overlap, duplicate, and property-based paths (PRC-006).
- `precept.contract.yaml_loader` with `load_contract(str | Path) -> HandoffContract` and `load_contract_from_string(str) -> HandoffContract`; uses `yaml.safe_load` exclusively, surfaces `(line, column)` on syntax errors via `ContractValidationIssue.yaml_mark`, rejects empty / non-mapping / unknown-key YAML with actionable messages; supports YAML anchors and aliases natively (PRC-007).
- Example contract YAML files at repo root: `examples/contracts/researcher_to_summariser.yaml` (blocking, fidelity 0.75) and `examples/contracts/summariser_to_writer.yaml` (warn, fidelity 0.70, mode defaulted) (PRC-007).
- Unit and integration tests for the YAML loader (`tests/unit/contract/test_yaml_loader.py`, `tests/integration/test_yaml_loader_integration.py`) covering example-file round-trip, anchor/alias resolution, malformed YAML with line/column, semantic round-trip, and contract distinctness (PRC-007).
- Runtime dependencies `pydantic>=2.5,<3` and `pyyaml>=6.0,<7` in `Dev/pyproject.toml`; dev additions `pip-tools>=7.4,<8` and `types-PyYAML>=6.0,<7` for lockfile generation and strict-mode type checking (PRC-006, PRC-007).
- `Dev/requirements-dev.lock` generated via `pip-compile --extra dev` for reproducible dev environments; regenerate on any dependency change per CLAUDE.md.
- Three follow-up tickets in `ISSUES.md`: PRC-006a (JSON Schema export helper), PRC-007a (YAML loader error enrichment with line/column on schema violations), PRC-007b (`examples/contracts/README.md`); all P2, post-MVP.

### Deferred
- `CODE_OF_CONDUCT.md` body and reporting-contact email: tracked as new ticket **PRC-002a** (pre-public-release gate). Committing a real contact address to a public git history is irreversible, so this is parked until a public contact alias or GitHub private-reporting flow is chosen. PRC-002's DoD item referring to the CoC is explicitly deferred to PRC-002a in `ISSUES.md`.
