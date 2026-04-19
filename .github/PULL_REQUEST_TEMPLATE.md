## Summary

<!-- 1-3 sentences. What does this PR do, and why? -->

## Linked issue

<!-- e.g., Closes PRC-011 / Refs PRC-011 -->

## Testing

<!-- How did you verify this works? Include commands, screenshots, or manual-test notes. -->

- [ ] New tests added or existing tests updated
- [ ] `pytest` passes locally (run from `Dev/`)
- [ ] `ruff check .` and `ruff format --check .` clean
- [ ] `mypy --strict src/precept` clean
- [ ] `bandit -r src/precept -ll` clean

## Checklist

- [ ] PR scope matches the linked ticket's Acceptance Criteria (no scope creep)
- [ ] `Dev/CHANGELOG.md` updated under `[Unreleased]` (for user-visible changes)
- [ ] Any scope-creep ideas captured as follow-up issues, not merged into this PR
- [ ] Public-API additions reviewed against `CLAUDE.md` and `ISSUES.md` (PRC-026) where relevant
