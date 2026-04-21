# Contributing to Precept

Thanks for your interest. Precept is under active early-stage development; drive-by contributions are welcome, but non-trivial changes should be discussed in an issue first.

> Precept is a Python SDK that lets developers declare **handoff integrity contracts** for multi-agent pipelines and emit violation events via OpenTelemetry GenAI semantic conventions. The v0 scorer is an embedding-similarity proxy; the calibrated scorer (an MSc dissertation deliverable) lands in Phase 2.

For deeper architecture, scope, and rationale, see [`CLAUDE.md`](CLAUDE.md) (operating manual), [`ISSUES.md`](ISSUES.md) (canonical backlog), and [`DEPENDENCIES.md`](DEPENDENCIES.md) (critical path and risk register).

---

## Project layout

The Python package lives in `Dev/`. The repo root holds planning files, the CI workflow, and the pre-commit config.

```
precept/
├── CLAUDE.md                  # operating manual
├── ISSUES.md                  # canonical backlog (PRC-XXX tickets)
├── DEPENDENCIES.md            # critical path + risk register
├── .github/workflows/ci.yml
├── .pre-commit-config.yaml
├── LICENSE
└── Dev/
    ├── pyproject.toml
    ├── CHANGELOG.md
    ├── src/precept/
    └── tests/
```

All `pip`, `pytest`, `ruff`, and `mypy` commands below run from inside `Dev/`.

---

## Development setup

Requires Python >= 3.10.

```bash
git clone https://github.com/gianpremrajaram/precept.git
cd precept/Dev
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
cd ..
pre-commit install                          # commit-stage hooks
pre-commit install --hook-type pre-push     # mypy on pre-push
```

## Running checks locally

Run from inside `Dev/`:

```bash
ruff check .                   # lint
ruff format --check .          # formatting check (drop --check to autoformat)
mypy --strict src/precept      # strict types
bandit -r src/precept -ll      # security scan
pytest --cov=src/precept       # tests with coverage
```

Pre-commit runs ruff and the file-hygiene hooks on every commit; `mypy` runs on `git push` so the commit loop stays fast.

---

## Branching

Use `<type>/PRC-XXX-short-slug`. Ticket IDs come from `ISSUES.md`.

| Type        | Use for |
|-------------|---------|
| `feat`      | New user-visible feature |
| `fix`       | Bug fix |
| `docs`      | Documentation-only changes |
| `infra`     | Tooling, CI, packaging, release |
| `test`      | Tests only, no behaviour change |
| `research`  | Dissertation / calibration work in `Research/` |

Example: `feat/PRC-011-embedding-proxy`.

---

## Commit messages

[Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<scope>): <subject>

[optional body]

[optional footer: Refs PRC-XXX, BREAKING CHANGE: ...]
```

Examples:

```
feat(scoring): add EmbeddingProxy v0 with constructor-time model load (PRC-011)
fix(contract): reject negative threshold in schema (PRC-008)
docs: document fail-open behaviour in evaluate_handoff (PRC-024)
```

---

## Pull requests

1. Branch from `main` using the naming convention above.
2. Keep PR scope to a single ticket. If you find unrelated issues, open follow-ups rather than widening the PR.
3. Run the local checks (or just `pre-commit run --all-files && pre-commit run --hook-stage pre-push --all-files`) before opening.
4. Fill out [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md): Summary, Linked issue, Testing, Checklist.
5. Update [`Dev/CHANGELOG.md`](Dev/CHANGELOG.md) under `[Unreleased]` for any user-visible change.

---

## Scope discipline

If you spot an unrelated issue mid-ticket, capture it as a follow-up — don't roll it into the current PR. For architectural questions on P0 items (see `DEPENDENCIES.md` §1), open a draft PR with the question pinned at the top, or raise an issue.

---

## Code of Conduct

A formal Code of Conduct will be adopted before the first public release (tracked as **PRC-002a**). Until then, be respectful in issues, PRs, and discussions.
