# FloodRoute

India-only product that predicts which roads become unusable in heavy rain and continuously reroutes citizens and emergency vehicles. Planning docs live in `docs/`; research notes in `docs/research/`.

## Working agreements

- Ponytail skill (`.claude/skills/ponytail/SKILL.md`) is on at level `ultra` for the main agent and every subagent. It governs code and dependency choices: delete before adding, stdlib and native first, one runnable check per non-trivial logic.
- Ponytail does not shorten requested documents. PRD, TRD, plans and research reports keep the depth the task asks for.
- Never simplify away validation at trust boundaries, safety logic, security, accessibility, or anything explicitly requested. Road-closure and routing logic is safety-critical.
- Do not put em-dashes in user-facing copy or design docs (taste-skill rule).
- Tag research claims as verified (with URL) or unverified. Do not invent endpoints, numbers or citations.

## Dev commands (backend)

- Python 3.11 venv at `apps/api/.venv` (shared, already installed editable). Do not run `uv sync` or recreate it.
- Tests: `cd apps/api && .venv/bin/pytest tests/<area>`. Lint: `.venv/bin/ruff check floodroute tests`.
- Dependencies are pinned in `apps/api/pyproject.toml`: fastapi, uvicorn, psycopg, httpx (dev: pytest, ruff). Stdlib first. Adding a dependency needs a one-line justification in your report.
- Node 22 and pnpm exist for `packages/ui` and the clients.

## Parallel work rules

- Each agent owns specific paths and writes only there. Read anything. Need a change elsewhere? Say so in your report.
- Agents do not run state-changing git commands. The main session commits.
- Nothing outward-facing: no emails, sign-ups, registrations or publishing. Drafts only.
- Scratch and large files go in the session scratchpad, never in the repo. Never commit `*.pbf` or raw downloads.
