# Branch protection setup

`main` is the only long-lived branch. All changes must arrive via pull
request — direct pushes are blocked. This document records the canonical
GitHub configuration so it can be re-applied or audited.

## GitHub UI

Repository → **Settings** → **Branches** → **Branch protection rules** →
**Add rule** for the pattern `main`:

- [x] Require a pull request before merging
  - [x] Require approvals: **1**
  - [x] Dismiss stale pull request approvals when new commits are pushed
  - [x] Require review from Code Owners
- [x] Require status checks to pass before merging
  - [x] Require branches to be up to date before merging
  - Required checks:
    - `lint-and-test`
- [x] Require conversation resolution before merging
- [x] Require linear history
- [x] Do not allow bypassing the above settings
- [x] Restrict who can push to matching branches → leave the list **empty**
      (so only PR merges land on `main`)
- [ ] Allow force pushes — **off**
- [ ] Allow deletions — **off**

Also under **Settings → General → Pull Requests**:

- [x] Allow squash merging (default)
- [ ] Allow merge commits — off
- [ ] Allow rebase merging — off
- [x] Always suggest updating pull request branches
- [x] Automatically delete head branches

## GitHub CLI equivalent

```bash
gh api -X PUT \
  repos/magic-alt/jetbot/branches/main/protection \
  -F required_status_checks.strict=true \
  -F 'required_status_checks.contexts[]=lint-and-test' \
  -F enforce_admins=true \
  -F required_pull_request_reviews.required_approving_review_count=1 \
  -F required_pull_request_reviews.dismiss_stale_reviews=true \
  -F required_pull_request_reviews.require_code_owner_reviews=true \
  -F required_linear_history=true \
  -F allow_force_pushes=false \
  -F allow_deletions=false \
  -F required_conversation_resolution=true \
  -F restrictions= # empty restrictions block all direct pushes
```

> Note: The `restrictions` block must be sent as an empty object/array to
> mean "nobody may push directly". Adjust per the GitHub REST API docs if
> running this through a tool that requires a different JSON shape.

## Local pre-commit hook

To mirror CI locally on every commit, install the helper hook:

```bash
cp scripts/git-hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

(See `scripts/git-hooks/pre-commit`.)
