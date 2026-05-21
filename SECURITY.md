# Security Policy

## Reporting a vulnerability

If you discover a security vulnerability, please **do not** open a public
GitHub issue. Instead, report it privately via GitHub's
[Private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
feature on this repository, or email the maintainers.

Please include:

- A description of the vulnerability and its potential impact
- Steps to reproduce
- Affected versions/commits
- Any suggested mitigations

We aim to acknowledge reports within 5 business days.

## Scope

In scope:

- The API service (`src/api/`)
- The LangGraph pipeline (`src/agent/`)
- PDF parsing and extraction (`src/pdf/`)
- Storage backends (`src/storage/`)

Out of scope:

- Issues caused by misconfiguration of optional dependencies you supplied
  (e.g. third-party LLM providers, market data vendors)
- Vulnerabilities in upstream dependencies (please report to that project,
  and let us know so we can pin/upgrade)

## Disclosure

We will coordinate a fix and public disclosure with you. Credit will be given
unless you prefer to remain anonymous.
