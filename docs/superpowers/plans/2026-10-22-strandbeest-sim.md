# Strandbeest Simulator Implementation Plan

> **For agentic workers:** if the superpowers skills are available, use
> superpowers:executing-plans (or superpowers:subagent-driven-development) to work through this plan
> task by task; otherwise follow the tasks in order yourself. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** A static web page, Python in the browser through PyScript, with a four-bar mode, a Jansen
leg playground and an Evolve mode that runs a GA over whole beests, ready for Al's course on
Tuesday 27 October 2026.

**Architecture:** `site/` is plain static files. `site/beest/` is a pure-Python package (standard
library only) holding all geometry, measures, fitness and GA logic; it runs unchanged under CPython
(pytest) and Pyodide. `site/app/` is the browser glue (PyScript, canvas drawing, the GA worker).
The runtime is vendored from npm into `site/vendor/`, so the page talks to no other host.

**Tech Stack:** PyScript 0.7.31, Pyodide 314.0.2 (Python 3.14), CPython 3.14 for tests, pytest,
Playwright for browser tests, uv. pymunk 7.3.1 for the stretch arena only.

**Spec:** [docs/brief.md](../../brief.md) (Al's requirements), [docs/decisions.md](../../decisions.md)
(provisional answers to every open question; build to them), [docs/scoping.html](../../scoping.html)
(measurements, components C1–C14, risks).

## Global Constraints

- Versions pinned exactly: `@pyscript/core` 0.7.31, `pyodide` 314.0.2, pymunk 7.3.1 (arena only).
- At runtime the page requests nothing from any host but its own.
- `site/beest/` imports only the standard library: no `js`, no `pyscript`, no numpy (decisions Q20).
- Lengths are hole-to-hole mm everywhere in the interface; Jansen units appear only in reference
  tests. `MM_PER_UNIT = 1.2` (Q8).
- Every "Set in" name in decisions.md exists under that name and is the single place to change it.
- Student-facing names match the slides: `random_genes, leg_from, fitness, best, select, crossover,
  mutate, clamp, POP_SIZE, GENERATIONS, ELITE, RATE` (brief §4, decisions S6).
- Interface copy is British English, plain enough for Year 11/12, with no em-dashes.
- Each mode mirrors its state onto `data-*` attributes of its root element (`data-jammed`,
  `data-grashof`, `data-stride`, `data-status`, …) so browser tests read numbers, not pixels.
- Beests walk −x: travel arrows point left (brief §2).

## Review Focus

1. A leg that jams part-way round: the playground draws it up to the jam and says where, with no
   console error. Test in Task 4.
2. A population where every beest jams or scores the same: the GA carries on, the graph draws, and
   no division by zero occurs in normalisation. Test in Task 5.
3. Student code that fails: a syntax error, an exception, a `fitness` returning `None` or NaN, an
   endless loop. Each gives a plain message with an editor line number, and Stop always recovers.
   Tests in Task 7.
4. Slider extremes: every length at its bound, `l` negative, equal four-bar lengths (a change
   point). Nothing divides by zero; jams are reported, not raised. Tests in Tasks 1 and 3.
5. A template that does not fit one A4 page: it continues on further pages and nothing is clipped.
   Test in Task 8.

## Working rules for the overnight run

- Do not ask questions. Where the plan and decisions.md leave a choice, make it, keep it easy to
  change, and log it in decisions.md under "Calls made while building". Put anything only Al can
  answer under "Questions for Al", with the provisional answer you built on.
- One task is one branch and one pull request, stacked: task N's branch starts from task N−1's, and
  its PR targets task N−1's branch. The first task's branch starts from `main` if
  `setup/cloud-brief` has been merged, otherwise from `setup/cloud-brief`.
- Before opening each PR: the whole test suite passes, the code-review pass in CLAUDE.md comes back
  clean, and the PR body lists the decisions it relies on. After opening it, follow CI to green and
  read any bot comment. In a cloud session `gh pr` is blocked, so open PRs and read checks with the
  `gh api` recipes in CLAUDE.md.
- If a task is blocked (for example no headless browser in the environment), record why in
  decisions.md, keep the browser tests in the repo for CI to run, and move to the next task. CI on
  GitHub Actions can always install Chromium, so the e2e job there is the backstop.

---

### Task 0: Check the environment

No PR of its own; findings go into Task 1's PR as `B` lines in decisions.md.

- [ ] **Step 1:** `uv sync` then `uv run pytest`. Expected: the reference tests are collected and
      skipped (no `beest` package yet).
- [ ] **Step 2:** `uv run playwright install chromium` (add `--with-deps` if system libraries are
      missing). Record whether a headless Chromium runs.
- [ ] **Step 3:** `npm view pyodide@314.0.2 dist.tarball` and `npm view @pyscript/core@0.7.31
      dist.tarball` resolve. Record whether the npm registry is reachable.

### Task 1: Geometry core (C2)

PR title: "Model Jansen legs and four-bar linkages in pure Python".

**Files:**
- Create: `site/beest/__init__.py`, `site/beest/geometry.py`, `site/beest/measures.py`
- Modify: `tests/test_reference.py` (remove the `importorskip` guard once the package exists)
- Test: `tests/test_geometry.py`, `tests/test_measures.py`

**Interfaces (produces):**
- `geometry.py`: `Point = tuple[float, float]`; `HOLY: dict[str, float]` (brief §2, Jansen units);
  `LENGTH_NAMES = tuple("abcdefghijklm")`; `ANGLES = 180`; `DRAW_ANGLES = 360`;
  `JAM_MARGIN_MM = 0.0`.
- `circ(p: Point, r1: float, q: Point, r2: float) -> tuple[Point, Point] | None`
- `circle_margin(p, r1, q, r2) -> float`: `min(r1 + r2 - D, D - abs(r1 - r2))`; negative when the
  circles miss.
- `rule_joints(lengths: dict[str, float], theta: float) -> dict[str, Point] | None`: Al's selection
  rule exactly as brief §2; keys `O C G J2 J3 J4 J5 F`.
- `LegTrace` (frozen dataclass): `angles: list[float]`, `joints: list[dict[str, Point]]` (one per
  angle reached), `jammed: bool`, `jam_angle: float | None` (radians), `jam_reason: str | None`
  (plain words naming the two links, e.g. "k and c cannot meet at 212°", or "the leg does not come
  back to where it started"), `closest_to_jam: float` (mm), `rule_disagreements: int`, and a `foot`
  property (`list[Point]`).
- `trace_leg(lengths: dict[str, float], n: int = ANGLES, margin: float = JAM_MARGIN_MM) -> LegTrace`:
  continuity tracking per decisions Q14 (rule at θ = 0, then the intersection nearest each joint's
  last position; closure within 0.5 mm; a pair of circles closer than `margin` to failing counts as
  failing).
- `grashof_class(ground, crank, coupler, rocker) -> str`: one of `"crank-rocker"`, `"rocker-crank"`
  (the rocker is shortest, so the driven crank only rocks), `"double-crank"`, `"double-rocker"`,
  `"change point"`, `"non-Grashof"`.
- `FourBarTrace` (frozen dataclass): `angles`, `crank_tip`, `coupler_joint`, `tracer` (lists of
  `Point`), `jammed`, `jam_angle`, `grashof`, `figure_eight: bool`.
- `trace_four_bar(ground, crank, coupler, rocker, along=0.0, offset=0.0, n=ANGLES) -> FourBarTrace`:
  layout per decisions S4; the tracer sits `along` mm from the crank–coupler joint towards the rocker
  joint and `offset` mm to its left.
- `self_intersects(path: list[Point]) -> bool`: closed polyline, adjacent segments excluded.
- `measures.py`: `FootMeasures(step_height, time_down, stride)`;
  `foot_measures(foot: list[Point], tol: float) -> FootMeasures` (stride is the x extent of samples
  within `tol` of the lowest point; time down is their fraction);
  `mirrored(foot) -> list[Point]` (n even; element t is (−x, y) of `foot[(n // 2 - t) % n]`);
  `beest_feet(foot, phases_deg: list[float]) -> list[list[Point]]` (per angle, every foot: original
  then mirror for each phase);
  `BeestMeasures(bob, distance)`; `beest_measures(foot, phases_deg) -> BeestMeasures` (distance per
  decisions S2: each step's travel is the x travel of the foot lowest at the start of the step).

- [ ] **Step 1:** Remove the guard from `tests/test_reference.py`; run `uv run pytest
      tests/test_reference.py -v`. Expected: FAIL (missing functions).
- [ ] **Step 2:** Write `tests/test_geometry.py` with:
  - `test_circ_tangent`: `circ((0,0),1,(2,0),1)` gives two points both within 1e-9 of `(1, 0)`.
  - `test_circ_apart_and_concentric`: `circ((0,0),1,(3,0),1)` and `circ((0,0),1,(0,0),2)` are `None`.
  - `test_margin_sign`: positive for crossing circles, negative for `((0,0),1,(3,0),1)`.
  - `test_jams_part_way`: `trace_leg({**HOLY, "m": 16.5})` (Jansen's crank 10% longer) is jammed at
    182° ± 2°, its `jam_reason` names f and g, and `joints` holds the 91 angles before the jam.
  - `test_extreme_lengths_never_raise`: every length at 10 and at 104 (and `l` at −30 and 30, in
    turn) returns a `LegTrace` without raising.
  - `test_grashof_classes`: (40, 15, 40, 35) → crank-rocker; (15, 40, 35, 40) → double-crank;
    (40, 30, 20, 25) → non-Grashof; (40, 20, 40, 20) → change point; (40, 35, 15, 40) → double-rocker;
    (40, 35, 40, 15) → rocker-crank.
  - `test_four_bar_jams_iff_not_rotatable`: crank-rocker (40, 15, 40, 35) and double-crank
    (15, 40, 35, 40) do not jam; non-Grashof (40, 30, 20, 25), double-rocker (40, 35, 15, 40) and
    rocker-crank (40, 35, 40, 15) do; the change point (40, 20, 40, 20) returns without raising.
  - `test_figure_eight_survey`: with `random.Random(1)`, draw lengths uniformly in 15–104 until 200
    crank-rockers; with `along` uniform in [0, coupler] and `offset = 0`, none is a figure of eight;
    with `offset` uniform in ±coupler, at least 10% are (brief §3 found 0% and about 30%; a check
    during setup found 0 of 200 and 56 of 200). Keep crank-rockers whose crank is the shortest link.
  - `test_known_figure_eight`: `trace_four_bar(59.5, 44.0, 92.6, 95.1, along=18.6, offset=-31.9)`
    has `figure_eight` true.
- [ ] **Step 3:** Write `tests/test_measures.py` with `test_mirror_identity` (mirrored foot at θ
      equals (−Fx, Fy) of the trace at π − θ, n = 360) and `test_distance_converges` (3 pairs at
      120°: 180 angles within 0.5% of 720).
- [ ] **Step 4:** Implement `geometry.py` and `measures.py`. Run `uv run pytest -v`. Expected: PASS.
- [ ] **Step 5:** Commit, push, open the PR (with Task 0's findings in decisions.md).

### Task 2: Page shell and runtime (C1, C11)

PR title: "Serve a PyScript page with three modes from vendored files".

**Files:**
- Create: `scripts/vendor.py`, `scripts/serve.py`, `site/index.html`, `site/pyscript.toml`,
  `site/style.css`, `site/_headers`, `site/app/__init__.py`, `site/app/main.py`
- Test: `tests/e2e/conftest.py`, `tests/e2e/test_shell.py`
- Modify: `.github/workflows/ci.yml` (add an `e2e` job: vendor, install Chromium, run
  `uv run pytest tests/e2e`)

**Interfaces (produces):**
- `scripts/vendor.py`: downloads the two npm tarballs from registry.npmjs.org, checks each against
  the registry's `dist.integrity`, and extracts `@pyscript/core`'s `dist/` to
  `site/vendor/pyscript/` and Pyodide's runtime files (`pyodide.mjs`, `pyodide.asm.mjs`,
  `pyodide.asm.wasm`, `python_stdlib.zip`, `pyodide-lock.json`) to `site/vendor/pyodide/`.
  Idempotent; versions as module constants.
- `scripts/serve.py`: serves `site/` on `127.0.0.1:8000` (`--port` to change) with
  `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Embedder-Policy: require-corp` and
  `Cache-Control: no-store`. `site/_headers` sends the same two isolation headers on Cloudflare.
- `site/pyscript.toml`: `interpreter` points at `./vendor/pyodide/pyodide.mjs`; `[files]` maps every
  `beest/*.py` and `app/*.py`.
- Page: tabs Four-bar, Leg, Evolve, routed by `#fourbar`, `#leg`, `#evolve`; a status line whose
  `data-status` becomes `ready` once Python has started.
- `tests/e2e/conftest.py`: a session fixture that runs `scripts/serve.py` on a free port and yields
  its base URL; e2e tests are marked `e2e`.

- [ ] **Step 1:** Write `test_page_starts_python` (`data-status="ready"` within 60 s, and every
      request the page makes goes to the server's own origin) and `test_tabs_switch` (each hash
      shows its section only). Run them. Expected: FAIL.
- [ ] **Step 2:** Implement the scripts and page. `uv run scripts/vendor.py && uv run pytest
      tests/e2e -v`. Expected: PASS.
- [ ] **Step 3:** Commit, push, open the PR.

### Task 3: Renderer and four-bar mode (C3, C4)

PR title: "Animate four-bar linkages".

**Files:**
- Create: `site/app/draw.py`, `site/app/fourbar_mode.py`
- Modify: `site/index.html`, `site/style.css`, `site/pyscript.toml`
- Test: `tests/e2e/test_fourbar.py`

**Interfaces (produces):** `draw.py` gives `View` (fits a world bounding box in mm to a canvas,
y up) with `stick(p, q, colour)`, `hole(p)`, `path(points, closed)`, `band(y0, y1)`,
`arrow(p, direction, label)` and `clear()`. Task 4 and Task 6 reuse it.

Behaviour: sliders for ground, crank, coupler, rocker (10–104 mm), `along` and `offset` (decisions
Q7); play, pause and speed; the Grashof class in words; a jam warning naming the angle; the tracer's
path; a "figure of eight" badge.

- [ ] **Step 1:** Write `test_default_turns_fully` (no jam warning, `data-grashof="crank-rocker"`),
      `test_jam_warning` (set 40, 30, 20, 25 → warning visible, `data-jammed="true"`),
      `test_figure_eight_badge` (59.5, 44.0, 92.6, 95.1 with along 18.6 and offset −31.9 → badge
      shows) and
      `test_change_point_lengths` (40, 20, 40, 20 renders with no console error). Expected: FAIL.
- [ ] **Step 2:** Implement. Expected: PASS. Commit, push, open the PR.

### Task 4: Leg playground (C5)

PR title: "Animate a Jansen leg and show its stride".

**Files:** create `site/app/leg_mode.py`; modify `site/index.html`, `site/style.css`,
`site/pyscript.toml`; test `tests/e2e/test_leg.py`.

Behaviour: 13 sliders in mm starting at Jansen × `MM_PER_UNIT`, with bounds from decisions Q16;
a down-tolerance slider (Q4); "Reset to Jansen"; the leg drawn with the body fixed and a
direction-of-travel arrow pointing left; the foot path and the shaded down band; stride, step height,
time down and closest-to-jam as numbers; a jam warning in plain words from `LegTrace.jam_reason`.

- [ ] **Step 1:** Write `test_shows_jansen_stride` (`data-stride` equals
      `foot_measures(trace_leg(jansen_mm).foot, 1.0).stride` within 0.05),
      `test_partial_jam_draws` (set m to 19.8 mm, Jansen's 16.5 units × 1.2: the warning names f and g,
      the canvas has drawn the leg up to 182°, no console errors) and `test_reset_restores_jansen`.
      Expected: FAIL.
- [ ] **Step 2:** Implement. Expected: PASS. Commit, push, open the PR.

### Task 5: Leg, fitness and GA engine (C6, C7)

PR title: "Score and evolve beests in pure Python".

**Files:**
- Create: `site/beest/leg.py`, `site/beest/fitness.py`, `site/beest/ga.py`,
  `site/beest/student_default.py`, `scripts/survey_limits.py`, `site/beest/limits.json`
- Test: `tests/test_leg.py`, `tests/test_fitness.py`, `tests/test_ga.py`

**Interfaces (produces):**
- `leg.py`: `MM_PER_UNIT = 1.2`, `DOWN_TOLERANCE_MM = 1.0`,
  `LENGTH_BOUNDS: dict[str, tuple[float, float]]`, `PAIRS_BOUNDS = (1, 4)`, `RANDOM_SPREAD = 0.3`
  (decisions Q4, Q8, Q16, S7). `Layout(pairs: int = 3, phases: tuple[float, ...] = (0, 120, 240))`.
  `jansen_lengths() -> list[float]` (a–m in mm). `Leg` (frozen dataclass): `genes: list[float]`,
  `layout: Layout`, `jams: bool`, `jam_reason: str | None`, `stride`, `step_height`, `time_down`,
  `distance`, `bob`, `flatness` (= `bob`), `closest_to_jam`, `fits: bool`, `tips: bool | None`
  (filled by Task 9), `normalised: dict[str, float]` (filled by the engine), `trace: LegTrace`.
  Jammed legs carry 0.0 for every measure.
  `leg_from(genes: list[float], layout: Layout = Layout(), tol=DOWN_TOLERANCE_MM, n=ANGLES) -> Leg`
  (the list's 13 values map onto `LENGTH_NAMES` in order).
- `fitness.py`: `INGREDIENTS: dict[str, bool]` (name → higher is better: distance, stride,
  step_height, time_down True; flatness False). `FitnessSettings(weights, normalisation, flip,
  limits)` with `normalisation` in `"jansen" | "limits" | "generation"` and defaults from decisions
  S3. `normalise(legs: list[Leg], settings, jansen: Leg) -> None` fills each `leg.normalised`
  (generation mode: all-equal values give 0.5; limits mode clips to 0–1).
  `settings_fitness(settings) -> Callable[[Leg], float]` (weighted mean of the normalised,
  flipped-where-set ingredients; jammed → 0).
- `ga.py`: `POP_SIZE = 30`, `GENERATIONS = 40`, `ELITE = 2`, `RATE = 0.2`, `MUTATION_SIZE = 3.0`,
  `TOURNAMENT = 3`. `random_genes() -> list[float]`, `clamp(genes) -> list[float]`,
  `mutate(genes, rate) -> list[float]` (gauss(0, `MUTATION_SIZE`) per length with probability `rate`,
  then clamp; uses the module-level `random`, seeded per run), `crossover(a, b, kind="uniform")`
  (`"uniform" | "blend" | "triangles" | "none"`), `select(population, scores) -> list[float]`
  (tournament of 3), `best(population, scores) -> tuple[list[float], float]`.
  `RunSettings(preset="ga" | "hill" | "random", pop, generations, budget: int | None, elite, rate,
  size, crossover, mask: set[str], layout_mutates: bool, seed: int, fitness: FitnessSettings)`.
  `Report(generation, evaluations, best_score, mean_score, best_genes, best_layout, best_values)`.
  `run(settings, fitness_fn, mutate_fn, on_generation: Callable[[Report], bool]) -> Report`:
  normalises each generation before scoring; stops when `on_generation` returns False or the
  budget is spent; hill = population 1, keep the better of parent and child, mutation only;
  random = fresh `random_genes()` each generation, best kept for the report.
- `student_default.py`: `SOURCE: str`, the starting editor text defining `fitness(leg)` and
  `mutate(genes, rate)` in the slides' style (brief §4, decisions S5).
- `scripts/survey_limits.py`: writes `limits.json` per decisions Q5 (seed 1).

- [ ] **Step 1:** Write the tests: `test_jansen_leg` (not jammed, fits, distance within 0.5% of
      141.83 × 1.2, bob within 0.03 of 0.08 × 1.2), `test_jammed_leg_measures_zero`,
      `test_jansen_normalises_to_one`, `test_generation_mode_all_equal` (every leg equal → 0.5, no
      error), `test_flip`, `test_limits_clip`, `test_mutate_rate_zero_is_identity`,
      `test_mutate_clamps` (size 1000 keeps every length in bounds), `test_crossover_kinds`,
      `test_tournament_prefers_better` (seeded, over 1,000 draws), `test_run_repeats_with_seed`,
      `test_budget_counts_evaluations`, `test_hill_and_random_presets`,
      `test_ga_improves` (seeded: best after 20 generations beats generation 0),
      `test_all_jammed_population_runs` (a fitness returning 0 for everyone completes),
      `test_student_default_runs` (exec `SOURCE`, run 3 generations with its functions).
      Expected: FAIL.
- [ ] **Step 2:** Implement, run `scripts/survey_limits.py`, run the suite. Expected: PASS. Check a
      default run scores 1,200 beests in under 5 s on CPython. Commit, push, open the PR.

### Task 6: Evolve mode (C6–C8 in the browser)

PR title: "Run evolution in the browser with presets and a progress graph".

**Files:** create `site/app/evolve_mode.py`, `site/app/ga_worker.py`, `site/app/graph.py`; modify
`site/index.html`, `site/style.css`, `site/pyscript.toml`; test `tests/e2e/test_evolve.py`.

Behaviour: a settings panel (preset, population, generations or evaluation budget, elite, rate,
mutation size, crossover, gene mask, layout mutation, ingredient weights, flips, normalisation,
down tolerance, seed); Run and Stop; the GA runs in a PyScript worker and reports each generation;
the graph plots best and average score (x = evaluations, runs overlaid until cleared, labelled
"relative to this generation" under that normalisation), with a second view of the best beest's raw
ingredients (decisions Q17, Q18); the best beest drawn whole and animated; winner checks (turns
fully, fits on sticks) shown as ticks or crosses.

- [ ] **Step 1:** Write `test_default_run_completes` (graph holds `GENERATIONS` points, winner checks
      shown), `test_stop_halts_run` (Stop mid-run; `data-status` back to `ready` within 10 s),
      `test_presets_overlay` (random, hill, GA at one budget → three series) and
      `test_seed_repeats` (two runs with seed 7 report the same best score). Expected: FAIL.
- [ ] **Step 2:** Implement. If PyScript's worker needs the isolation headers, Task 2's server and
      `_headers` already send them. Expected: PASS. Commit, push, open the PR.

### Task 7: Code route (C9)

PR title: "Let students edit fitness and mutate".

**Files:** create `site/app/editor.py` (and `site/app/editor.js` only if CodeMirror needs JS
glue); modify `site/app/evolve_mode.py`, `site/app/ga_worker.py`, `site/index.html`; test
`tests/e2e/test_code_route.py`.

Behaviour per decisions Q9: one editor starting from `student_default.SOURCE`; Run uses the editor's
`fitness` and `mutate`; errors halt the run and show the message with editor line numbers; Stop
terminates the worker and starts a fresh one; the text persists in browser storage; "Reset to
starting code" restores `SOURCE`.

- [ ] **Step 1:** Write `test_syntax_error_names_line`, `test_exception_shows_traceback`,
      `test_fitness_returning_none_or_nan` (plain message, run halted), `test_endless_loop_stop`
      (`while True: pass` inside `fitness`; Stop; a normal run then completes) and
      `test_code_survives_reload`. Expected: FAIL.
- [ ] **Step 2:** Implement. Expected: PASS. Commit, push, open the PR.

### Task 8: Templates (C10)

PR title: "Print legs and four-bars at 1:1".

**Files:** create `site/beest/template.py`; modify `site/app/evolve_mode.py`,
`site/app/fourbar_mode.py`, `site/style.css` (print stylesheet); test `tests/test_template.py`,
`tests/e2e/test_print.py`.

**Interfaces (produces):** `leg_template_svg(genes: list[float], layout: Layout) -> list[str]` and
`four_bar_template_svg(ground, crank, coupler, rocker) -> list[str]`: one SVG per A4 page, each with
`width="210mm" height="297mm" viewBox="0 0 210 297"`, content per decisions Q19.

- [ ] **Step 1:** Write `test_sticks_true_length` (each stick's hole centres are its length apart in
      viewBox units), `test_end_margins` (5 mm), `test_calibration_bar` (100 units),
      `test_counts_follow_pairs`, `test_overflow_continues_on_next_page` (14 sticks of 104 mm: every
      element inside its page's viewBox, more than one page) and, in e2e, `test_print_media` (with
      print media emulated, only the template is visible). Expected: FAIL.
- [ ] **Step 2:** Implement. Expected: PASS. Commit, push, open the PR.

### Task 9 (should): Tipping check (C12)

PR title: "Flag beests that would tip over".

`measures.tips(feet: list[list[Point]], tol: float, com_x: float = 0.0) -> bool`: at each angle the
supporting feet are those within `tol` of that angle's lowest foot; the beest tips if `com_x` lies
outside their x range at any angle. `leg_from` fills `Leg.tips`; `fitness.py` gains an `upright`
ingredient (1 when it stays up). Tests: Jansen with 1 pair tips, with 3 pairs at 120° does not
(tol 1 mm at Jansen units × `MM_PER_UNIT`).

### Task 10 (stretch): Arena (C13)

PR title: "Walk evolved beests in a physics arena". Start from `docs/spikes/pymunk_beest.py`.
`site/beest/arena.py` builds a pymunk beest from genes and layout per decisions Q2, steps at 600
steps per turn, and reports distance per turn and whether it tipped. Vendor pymunk 7.3.1's
`cp314 pyemscripten_2026_0_wasm32` wheel and Pyodide's cffi wheel. CPython tests (pymunk installed
as a dev dependency): Jansen 3 pairs walks −x at 138–148 mm per turn × `MM_PER_UNIT`; 1 pair tips.
An Arena tab draws it live.

### Task 11 (stretch): Races (C14)

Pencils and towel per decisions Q2; races: distance in 10 turns, turns to cross the pencils, turns
to cross the towel.

### Task 12: Morning handover

- [ ] Bring decisions.md up to date: every call, every question for Al (most important first),
      every slide edit.
- [ ] End the session with a message for Al: what is done (each PR with its link and CI state),
      what is not, how to run it locally (`uv run scripts/vendor.py`, then
      `uv run scripts/serve.py`, then open http://127.0.0.1:8000), and the questions.
