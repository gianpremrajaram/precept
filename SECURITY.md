# Security Policy

Precept is a research-preview project (v0). It is not yet recommended for production use, and the operating threat model assumes the framework is run in trusted research and development environments.

## Reporting a vulnerability

Please use GitHub's [private vulnerability reporting](https://github.com/gianpremrajaram/precept/security/advisories/new) rather than opening a public issue. Reports are reviewed by the maintainer on a best-effort basis; please allow up to fourteen days for an initial response.

If private vulnerability reporting is unavailable, email `gianpremr@gmail.com` with the prefix `[precept-security]` in the subject line. Encrypted reports welcome on request.

## Scope

In scope: the `precept` Python package, the example contracts under `examples/`, and the CI workflows under `.github/workflows/`.

Out of scope: vulnerabilities in upstream dependencies (`pydantic`, `sentence-transformers`, `langgraph`, `opentelemetry-*`, `pyyaml`, `numpy`). Please report those to their respective projects.

## Supported versions

Pre-1.0, only the `main` branch is supported. Patch fixes are not backported, and there is no tagged release on PyPI yet. Once a tagged release exists, support narrows to the most recent minor version on PyPI.

## Disclosure preferences

Coordinated disclosure preferred. The maintainer will acknowledge receipt within fourteen days, agree a disclosure timeline with the reporter, and credit the reporter in the fix advisory unless anonymity is requested.
