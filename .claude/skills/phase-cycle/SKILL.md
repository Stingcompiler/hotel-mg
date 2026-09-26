---
name: phase-cycle
description: The standing delivery loop for this repo. Use for every build task in Sky Towers — when continuing the build, starting the next phase item from the spec, or after finishing one. Decide and execute your own recommendations, push, check CI, merge into main, then continue with the next phase item.
---

# Phase cycle — execute, push, check, merge, continue

Standing instruction from the owner of this repo (2026-09-26):
**"Always execute your recommendation, then push, check, merge, and continue building the rest."**

This overrides the habit of stopping to ask. Do not ask the user to choose between options; pick the option you would recommend, execute it, and record it. Stop and ask only when blocked on something only the user can provide (credentials, a Windows machine, a real business fact that cannot be reasonably assumed and would be costly to change later) — and even then, continue with other work that is not blocked.

## Loop

1. **Pick the next item.** Follow the build order in `docs/spec/SkyTowers-System-Build-Spec.md` §12 (Track B: B0 → B1 → B2 → B3 → B4 → API freeze, then Track F). Check `docs/decisions.md` for what is done. One phase item (or a coherent slice of one) per branch.
2. **Decide.** Where the spec or design is silent or inconsistent, choose the recommended option. Append the decision to `docs/decisions.md`; design questions also go to `docs/design-gaps.md` with the fallback used.
3. **Build** on a branch named `<phase>-<slug>` (e.g. `b1-rooms`) from the latest `main`. Follow `CLAUDE.md` rules: `rules.py` pure and fully tested, one service per use case in one transaction, Arabic `detail` errors, money in minor units.
4. **Check locally** from `server/`:
   ```
   ruff check . && ruff format --check .
   python manage.py makemigrations --check --dry-run
   python manage.py spectacular --validate --fail-on-warn --file openapi.yml
   python -m pytest
   ```
5. **Commit and push** the branch: `git push -u origin <branch>` (retry network failures with backoff 2s/4s/8s/16s).
6. **Check CI** for the pushed commit: `build/ci-status.sh $(git rev-parse HEAD)` (run it in the background; it polls every 30 s). If it fails, find the cause, fix, push, check again. Never merge red. Job logs are usually not downloadable from a cloud session (blob storage is blocked); failing tests are published as annotations instead: `gh api repos/Stingcompiler/hotel-mg/actions/runs/<run>/jobs --jq '.jobs[]|"\(.id) \(.name) \(.conclusion)"'`, then `gh api repos/Stingcompiler/hotel-mg/check-runs/<job id>/annotations`.
7. **Open a PR and merge it** (GitHub REST via `gh api`; GraphQL — `gh pr create/merge` — is blocked in cloud sessions):
   ```
   gh api repos/Stingcompiler/hotel-mg/pulls -f title="<phase>: <summary>" -f head=<branch> -f base=main -F body=@pr.md
   gh api -X PUT repos/Stingcompiler/hotel-mg/pulls/<n>/merge -f merge_method=merge
   ```
   The PR body lists the phase gate, what was built, and how it was verified, and ends with the session attribution lines. Merge only after step 6 is green. Then `git fetch origin main` and start the next branch from it.
8. **Report** to the user in a few lines: what was built, the decisions taken, CI result, what is next.
9. **Continue** with the next item — go back to step 1 without waiting for the user.

## Limits

- Track W items (Windows service, PyInstaller, NSIS, WebView2 printing, power-cut test) cannot be verified in a Linux cloud session: write and lint them, rely on the `windows-latest` CI job, and list what still needs a real Windows PC.
- `design-package/` is read-only.
- No custom React code before the API freeze (§12).
- `gh` is installed with `apt-get install -y gh` if missing (a fresh container won't have it). Only `gh api` REST calls work; the token comes from the environment.
