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

### Deferred
- `CODE_OF_CONDUCT.md` body and reporting-contact email: tracked as new ticket **PRC-002a** (pre-public-release gate). Committing a real contact address to a public git history is irreversible, so this is parked until a public contact alias or GitHub private-reporting flow is chosen. PRC-002's DoD item referring to the CoC is explicitly deferred to PRC-002a in `ISSUES.md`.
