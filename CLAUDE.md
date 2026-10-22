# Strandbeest simulator

A static web page for Al's "Evolving Machines" course (Year 11/12, Tue 27 to Thu 29 October 2026):
a four-bar mode, a Jansen leg playground, and a GA that evolves whole Strandbeests. Python runs in
the browser through PyScript; there is no backend.

Read before working:

- [docs/brief.md](docs/brief.md): Al's requirements, geometry and measured reference cases. Al's
  words; do not edit it. Corrections and interpretations go in decisions.md.
- [docs/decisions.md](docs/decisions.md): an answer to every open design question. Build to it.
- [docs/superpowers/plans/2026-10-22-strandbeest-sim.md](docs/superpowers/plans/2026-10-22-strandbeest-sim.md):
  the build plan, task by task, with interfaces and tests.
- [docs/scoping.html](docs/scoping.html): measurements, components C1–C14, risks.
- `docs/spikes/`: throwaway code from scoping, for reference only.

## Who decides

Al makes the design decisions. Answers in decisions.md marked provisional are Claude's calls standing
in for his; he confirms or changes them. When working without him (the overnight build), do not stop
to ask: make the call, keep it easy to change (a named constant or a setting), and add a line under
"Calls made while building". Anything only Al can answer goes under "Questions for Al" with the
answer you built on. When he is present, ask him rather than choosing.

## Layout

- `site/`: everything served, as plain static files with no build step.
  - `site/beest/`: the model (geometry, measures, fitness, GA, templates). Standard library only, so
    it runs the same under CPython and Pyodide; no `js`, `pyscript` or numpy imports.
  - `site/app/`: browser glue (PyScript, canvas drawing, the GA worker).
  - `site/vendor/`: PyScript and Pyodide, fetched by `scripts/vendor.py`; gitignored.
- `scripts/`: `vendor.py`, `serve.py`, `survey_limits.py`, `cloud_setup.sh`.
- `tests/`: pytest under CPython; `tests/e2e/` drives the page in Chromium (marked `e2e`).

## Commands

```bash
uv sync                      # Python 3.14 and the dev dependencies
uv run pytest -m "not e2e"   # model tests
uv run scripts/vendor.py     # fetch the pinned runtime from the npm registry
uv run scripts/serve.py      # serve site/ at http://127.0.0.1:8000 with the isolation headers
uv run pytest -m e2e         # browser tests; need the runtime and a Chromium
```

## Cloud sessions

- `scripts/cloud_setup.sh` runs at session start and says whether Chromium could be installed.
  Playwright's download hosts are outside the default network allowlist; when it fails, the e2e
  tests still run in CI.
- jsDelivr is outside the allowlist too, which is one reason the runtime comes from npm.
- `gh pr` and `gh issue` are blocked (the proxy refuses GraphQL); `gh api` works. With
  `R=repos/Babissimo/strandbeest-sim`:
  - open a PR: `gh api $R/pulls -f title="…" -f head=<branch> -f base=<base branch> -F body=@body.md`
  - checks on a commit: `gh api $R/commits/<sha>/check-runs --jq '.check_runs[] | "\(.name) \(.status) \(.conclusion)"'`,
    polled every minute until every run has completed
  - a failed job's log: `gh api $R/actions/jobs/<job id>/logs`
  - the latest comment on a PR: `gh api $R/issues/<n>/comments --jq '.[-1].body'`

## Code

- Python 3.14, type hints, frozen dataclasses for results. Names from the slides
  (`random_genes, leg_from, fitness, best, select, crossover, mutate, clamp, POP_SIZE, GENERATIONS,
  ELITE, RATE`) stay exactly as they are.
- Test first. Tests travel in the same commit as the code they cover. Browser tests read numbers
  from `data-*` attributes rather than pixels.
- Comments speak from inside the code about how it works now. Never mention the conversation, the
  request, the reviewer or that a line is new. Keep them short and beside the line they govern; state
  the constraint, not the argument for it. No leftover deliberation ("option A"), and no notes about
  fixed bugs; if a fix would break were the code changed back, state that as a standing constraint.
  Prefer no comment to a misleading one.

## Writing

Applies to docs, commit messages, PR text and the page's own copy.

- British spelling and an understated tone. No em-dashes (commas, colons or brackets instead; en-dashes
  in numeric ranges are fine). No "it's not just X, it's Y" and similar flourishes.
- Say each thing once and refer back to it. Concise, but never at the cost of a needed detail.
- Describe how things work now. When a problem is fixed, delete the passage about it rather than
  rewriting it as history.
- Page copy is for 16 and 17 year olds: plain words, mm for lengths, the beest walking left.

## Git and pull requests

- Never commit to `main`. Each plan task is its own branch and PR, stacked on the previous task's.
- Each commit has one purpose, and its message body says why. A branch's history never undoes itself:
  fold corrections into the commit they correct (`git commit --fixup <sha>` then
  `git rebase --autosquash`; interactive rebase is unavailable), and push with
  `--force-with-lease`. Do not rewrite commits a reviewer has commented on line by line.
- Stage the paths you changed, not `git add -A`.
- Before opening a PR: the tests pass, and a review comes back with nothing worth acting on. Use the
  `/code-review` skill if it is available, otherwise a fresh subagent given the diff and asked for
  correctness bugs; fix, review again, repeat. The PR body says why the change exists and which
  decisions.md entries it relies on.
- After opening it, follow CI until it is green, fix real failures, report flakes rather than
  re-running quietly, and read any comment a bot leaves.
