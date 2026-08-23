---
description: Convene the EGW//OCC realism board — four research agents audit the sim in parallel and each return at least 3 ranked suggestions.
---

Convene the realism board.

Spawn all four project agents **in parallel, in the background** —
`ops-realism`, `rostering-systems`, `occ-interface`, `gameplay-design`.
Each reads `.claude/agents/_SHARED_BRIEF.md` and follows its own remit.

Focus for this run: $ARGUMENTS
(If that is empty, tell each agent to pick the area with the weakest coverage,
biased toward whatever the current session has been touching — check
`.claude/SESSION_SUMMARY.md` and `git status`.)

Give every agent these instructions verbatim in its prompt:

- Read `.claude/agents/_SHARED_BRIEF.md` first, then your own agent file.
- Read `docs/research/REALISM_BOARD_LOG.md` and do **not** re-propose anything
  already logged as accepted, rejected, or built. Superseding a logged item
  with a better version is fine — say so explicitly.
- Return **at least 3** suggestions, ranked best-first, in the exact format
  given by the output contract in the brief.
- Every claimed gap needs a `file:line` citation; every factual claim about
  the real world needs a source URL.

When all four report back:

1. Merge the reports. Collapse duplicates — more than one agent landing on the
   same gap independently is a strong signal, so say when that happens rather
   than hiding it.
2. Rank the merged set by value-to-effort, not by which agent found it.
3. Present the ranked list to the user with each agent's top pick called out.
4. Append the full merged set to `docs/research/REALISM_BOARD_LOG.md` with the
   date and the run's focus, so the next board meeting doesn't repeat itself.
5. Do **not** start implementing anything. The board advises; the user decides.
