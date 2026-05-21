# Contributing to jetbot

Thanks for your interest in contributing! This project follows a standard
open-source workflow: **all changes land on `main` via pull request**.
Direct pushes to `main` are not allowed.

## Workflow

1. **Fork** the repository (or create a feature branch if you have write
   access).
2. Create a topic branch from `main`:
   ```bash
   git checkout -b feat/<short-description>
   # or fix/<...>, docs/<...>, chore/<...>, refactor/<...>
   ```
3. Make your changes, including tests.
4. Run the full local CI pipeline before committing:
   ```bash
   bash scripts/local_ci.sh
   ```
   The git pre-commit hook (`.git/hooks/pre-commit`, if installed) also runs
   these checks automatically.
5. Commit using concise, imperative messages
   (e.g. `add validator for balance check`).
6. Push your branch and open a pull request against `main`.
7. Wait for CI to pass and for at least one review approval before merging.
   Use **Squash and merge** by default.

## Branch protection (maintainers)

`main` is protected with the following rules (configure via GitHub
Settings → Branches → Branch protection rules):

- Require a pull request before merging
- Require approvals: **1** (at least)
- Dismiss stale pull request approvals when new commits are pushed
- Require status checks to pass before merging:
  - `lint-and-test`
- Require branches to be up to date before merging
- Require linear history
- Do not allow bypassing the above settings
- Restrict who can push to matching branches: **no one** (force only PRs)

See [`docs/BRANCH_PROTECTION.md`](docs/BRANCH_PROTECTION.md) for the exact
GitHub CLI commands.

## Coding style

- Python 3.12+, 4-space indentation, type hints on public functions.
- Use `snake_case` for functions/variables and `PascalCase` for classes.
- Run `make fmt` (ruff format) and `make lint` (ruff check) before pushing.
- Type-check with `make typecheck` (mypy).

## Tests

- Use `pytest`; place tests under `tests/` named `test_<area>_<behavior>.py`.
- Prefer deterministic tests with the mock LLM (`LLM_DEFAULT_MODEL=mock:mock`
  is forced in `tests/conftest.py`).
- All tests must complete within the 60s timeout.
- Run with `make test` or `python -m pytest`.

## Web UI development

The Vue 3 + Vite SPA lives under [`web/`](web/). The dev server proxies
`/v1` to the FastAPI backend on `:8000`, so run both:

```bash
make dev              # terminal 1 — backend
make web-install      # one-time
make web-dev          # terminal 2 — SPA on http://localhost:5173
```

Before pushing any change under `web/`, run:

```bash
make web-lint         # eslint + vue-tsc type check
make web-build        # production build into web/dist/
```

The `web-build` GitHub Actions job runs these in CI for every PR.

## Reporting issues

Please use the [issue templates](.github/ISSUE_TEMPLATE/) and include:

- A clear description and reproduction steps
- Expected vs. actual behavior
- Environment (OS, Python version, relevant `.env` flags)
- Logs (with secrets redacted)

## Security

Do **not** open public issues for security vulnerabilities. See
[`SECURITY.md`](SECURITY.md) for the responsible disclosure process.

## License

By contributing, you agree that your contributions will be licensed under the
MIT License (see [`LICENSE`](LICENSE)).
