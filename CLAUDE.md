# FloodRoute

India-only product that predicts which roads become unusable in heavy rain and continuously reroutes citizens and emergency vehicles. Planning docs live in `docs/`; research notes in `docs/research/`.

## Working agreements

- Ponytail skill (`.claude/skills/ponytail/SKILL.md`) is on at level `ultra` for the main agent and every subagent. It governs code and dependency choices: delete before adding, stdlib and native first, one runnable check per non-trivial logic.
- Ponytail does not shorten requested documents. PRD, TRD, plans and research reports keep the depth the task asks for.
- Never simplify away validation at trust boundaries, safety logic, security, accessibility, or anything explicitly requested. Road-closure and routing logic is safety-critical.
- Do not put em-dashes in user-facing copy or design docs (taste-skill rule).
- Tag research claims as verified (with URL) or unverified. Do not invent endpoints, numbers or citations.
