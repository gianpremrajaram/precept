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
