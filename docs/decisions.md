# Decisions

Al makes the design decisions on this project. The first build runs overnight without him, so every
open question from the scoping (Q1–Q21 in [scoping.html](scoping.html) §5) has a **provisional**
answer below. Build to these, keep each one easy to change (a named constant or a setting, given
under "Set in"), and expect Al to overrule some of them on Friday.

Status values: **provisional** (Claude's call, awaiting Al), **confirmed** (Al agreed), **changed**
(Al chose differently; the entry says what).

## Answers to the scoping questions

### Q1 Where scores come from: provisional
The whole-beest kinematic model scores evolution. A tipping check (C12) is measured as `leg.tips` and
offered as an ingredient. The arena (stretch) tests and races evolved beests and never scores them.

### Q2 Arena contents: provisional, stretch
Flat ground first. Pencils are fixed circles 7.5 mm in diameter at 40 mm spacing. The towel is ground
with friction 1.5 and 2 mm bumps every 10 mm. Chassis 30 g, each stick 1 g, constant-speed crank at
one turn per second, 600 physics steps per turn. Draw every leg, the phase-0 pair darker. Start from
`docs/spikes/pymunk_beest.py`, which already walks.

### Q3 Physics library: confirmed by measurement
pymunk 7.3.1 (WebAssembly wheel from PyPI, cffi from Pyodide). Arena only.

### Q4 "Down" tolerance: provisional
Default 1 mm; a slider from 0.5 to 4 mm in the playground and a GA setting; drawn as a shaded band
above the foot path's lowest point. Set in: `DOWN_TOLERANCE_MM`.

### Q5 Fixed limits for normalisation 2: provisional
The 5th and 95th percentiles of each ingredient over 2,000 random working legs (each length uniform
within ±25% of Jansen's, standard layout), computed by `scripts/survey_limits.py` with a fixed seed
into `site/beest/limits.json`. Editable in the settings panel.

### Q6 Default crossover: provisional
Uniform: each length from one parent, as on the slides. A setting offers blend (a random point
between the parents for each length), triangles (b, d, e travel together, as do g, i, h) and none.

### Q7 Four-bar tracing point: provisional
Always available as `along` (mm from the crank–coupler joint, along the coupler) and `offset` (mm at
right angles to it; 0 is a straight coupler, the default). A badge says when the traced curve
crosses itself (a figure of eight).

### Q8 Scale and units: provisional
Genes are hole-to-hole lengths in mm. Jansen's reference leg is the holy numbers × 1.2 mm per Jansen
unit, so its longest stick (h) is 78.8 mm, leaving 32% headroom under the 104 mm cap. Set in:
`MM_PER_UNIT = 1.2`. In the interface, "normalisation" names the three ingredient options (with
"scaling" in brackets where the slides' word helps) and "scale" means mm per Jansen unit.

### Q9 Code route: provisional
One editor holding `fitness` and `mutate`, starting from the slide code, with Python highlighting
and line numbers (PyScript's bundled CodeMirror if it can be driven directly, else CodeMirror from
npm). The GA runs in a PyScript worker. Run sends the editor's text to the worker; Stop terminates the
worker and starts a fresh one, so an endless loop is always recoverable. An exception halts the run
and shows the traceback with line numbers that match the editor. The text is kept in browser storage,
with "Reset to slide code". If the worker needs cross-origin isolation, the dev server and
`site/_headers` send `Cross-Origin-Opener-Policy: same-origin` and
`Cross-Origin-Embedder-Policy: require-corp`.

### Q10 Self-hosted runtime: provisional
Yes. `scripts/vendor.py` downloads pinned PyScript and Pyodide from the npm registry into
`site/vendor/` (gitignored), and the page loads nothing from any other host. The arena's wheels are
vendored the same way when the arena is built.

### Q11 Priority order: provisional
As the brief's §5, in the order of the plan's tasks.

### Q12 Hosting: provisional
Nothing deploys yet. `site/` is plain static files with no build step, so either host in the brief's
§7 can serve it; it includes a `_headers` file for Cloudflare. The repo is `Babissimo/strandbeest-sim`
(private) until Al names it.

### Q13 Devices: provisional
Unknown. Target current Chrome, Edge, Safari and Firefox on laptops. Size the default GA settings so a
default run finishes within 20 s on a machine four times slower than Al's Mac, where scoring one
beest at 180 angles took 2.9 ms in the browser.

### Q14 Branch switches and jams: provisional
Each joint takes Al's rule (max-y, min-x and so on) at θ = 0, then at each later angle the
intersection nearest its previous position, as a built leg would. A leg is jammed if any pair of
circles fails to meet at any sampled angle, or if the tracked leg does not come back to its starting
position after one turn (within 0.5 mm). There is no near-jam margin by default; `leg.closest_to_jam`
(mm) is measured and shown, and a margin setting defaults to 0. Jansen's own leg comes within 1.19 mm.
Set in: `JAM_MARGIN_MM = 0`.

### Q15 What `fitness` receives: provisional
`fitness(leg)` keeps the slides' name. `leg` describes the whole beest built from that leg design.
Its attributes are listed in the plan (`Leg` in task 3). "Flatness" is the body bob (lower is better,
so flipped by default); `leg.bob` is the same number under its plain name. `stride` is the single
foot's stride within the down tolerance; `distance` is the whole beest's travel per crank turn.

### Q16 Genes beyond the lengths: provisional
`pairs` (whole number, 1–4) and `phases` (one throw angle per pair in degrees, the first fixed at 0).
Stick lengths b–k and m lie in 10–104 mm; the frame offsets lie in a: 10–104 mm and l: −30–30 mm.
By default all 13 lengths may mutate and the layout stays at 3 throws at 120°. When the layout may
mutate, `pairs` changes by ±1 with probability `RATE` (resetting the phases to even spacing) and each
phase moves by `random.gauss(0, 15)` degrees. Students' `mutate` sees only the lengths.
Set in: `LENGTH_BOUNDS`, `PAIRS_BOUNDS`, the gene mask in settings.

### Q17 Comparing searches: provisional
Budgets are counted in fitness evaluations (default 1,500 each), the graph's x-axis is evaluations,
runs overlay on one graph until cleared, and each run shows its seed. A seed box lets a pair repeat a
run exactly.

### Q18 Graph under normalisation: provisional
The graph plots best and average score per generation. Under per-generation normalisation it is
labelled "relative to this generation". A second view plots the best beest's raw ingredients per
generation. Flipped scores under normalisation 1 can go negative and are shown as they are.

### Q19 Template: provisional
A4 portrait at 1:1 mm. Each stick is drawn on its own at true length with hole centres marked, 5 mm
end margins, its letter, its hole-to-hole length and how many to cut for the chosen number of pairs.
The chassis holes (O, G, and the mirrored G) form a separate drilling diagram. A 100 mm calibration
bar says "check with a ruler". Printed through a print stylesheet, with an SVG download too. The
four-bar mode prints its four sticks the same way.

### Q20 numpy: provisional
No. The core is pure Python, readable by students and with nothing to download.

### Q21 Drawing: provisional
Python draws through the canvas 2D API; the graph is drawn the same way. No chart library.

## Other calls made during setup

- **S1 Angles.** Scoring and jam checks use 180 crank angles; drawing uses 360. Set in: `ANGLES`.
- **S2 Distance per turn.** Each step's body travel is the x travel of the foot that supports at the
  start of that step. This converges by 90 angles (125.96, 135.59, 141.83 for 1, 2 and 3 pairs).
  Leaving out the takeover step, as the brief's reference figures did, undercounts by up to 10% at
  180 angles (127.9 for 3 pairs).
- **S3 GA defaults.** `POP_SIZE = 30`, `GENERATIONS = 40`, `ELITE = 2`, `RATE = 0.2` per length,
  mutation size 3 mm, tournament of 3. Default fitness: jams score 0, otherwise distance (weight 1)
  and step height (weight 0.5), normalised by Jansen's values.
- **S4 Four-bar layout.** Crank pivot at the origin, rocker pivot at (ground, 0). The coupler joint
  takes the max-y intersection at θ = 0, then continuity as in Q14.
- **S5 Slide code.** The build has the slide names but not the slide code. The starting `fitness`
  and `mutate` are written from the brief's §4; Al compares them with the slides on Friday.
- **S6 Student-facing genes.** The functions students see (`random_genes`, `mutate`, `crossover`,
  `clamp`, `leg_from`) take and return a plain list of 13 lengths in the order a–m, as GA slides
  usually show. The layout genes (`pairs`, `phases`) travel beside the list inside the engine.
- **S7 Random genes.** `random_genes()` draws each length uniformly within ±30% of Jansen's, then
  clamps. Set in: `RANDOM_SPREAD = 0.3`.

## Calls made while building

Append one line per call that a reviewer could disagree with: `B<n> <what was decided> (why)`.

- **B1 Environment.** In the cloud session `uv sync` and the model tests work and the npm registry
  is reachable. Playwright cannot download its Chromium, but the image's own Chromium 141 at
  `/opt/pw-browsers/chromium` launches, so the browser tests run in the session as well as in CI.
- **B2 Angles reached.** `LegTrace.angles` and `FourBarTrace.angles` hold only the angles reached,
  so they pair one to one with the joints (the plan left open whether they list every sample).
- **B3 Closing angle.** A leg or four-bar that fails at the extra angle 2π, or comes back more than
  0.5 mm away, is jammed with `jam_angle` None and the reason "the leg does not come back to where
  it started" (it has no single angle to name). 1 in 4,000 random legs within ±30% does this.
- **B4 Closest to jam of a jammed leg** is the margin of the pair that failed, so it is negative when
  the circles miss (a measure of how far off the leg is).
- **B5 Phases** are rounded to the nearest sampled crank angle (2° at 180 angles) when feet are
  combined into a beest (interpolating would cost time for a difference far below the stride).
- **B6 Distance is signed.** A beest whose supporting foot moves −x relative to the body walks the
  wrong way and scores a negative distance (clipping at 0 would hide which way it went).
- **B7 Unassemblable four-bars.** A four-bar that cannot be put together at θ = 0 jams at 0° with
  nothing traced; so does the all-equal rhombus, whose crank tip sits on the rocker pivot there
  (starting elsewhere would hide that the linkage can flip either way).
- **B8 Change point tolerance.** Lengths within 1e-6 mm of S + L = P + Q count as a change point
  (slider values such as 20.1 + 40.1 and 30.1 + 30.1 differ in floating point).
- **B9 Figure of eight.** A crossing counts only if both loops it makes have a roundness
  (4π × area / perimeter²) of at least 0.02 (`FIGURE_EIGHT_MIN_ROUNDNESS`). A tracer on or beside
  the coupler joint doubles back along one arc, and sampling then makes thin false crossings: in a
  survey of 300 crank-rockers these slivers stayed below 0.011, while every real loop was above 0.03.
- **B10 Tied feet.** When two feet are equally low, the one lower at the next angle carries the body,
  so the order in which throws are listed does not change the distance.
- **B11 Tabs.** A few lines of inline script route the tabs, so they work during the seconds Python
  takes to start. Sections are `#fourbar-mode`, `#leg-mode` and `#evolve-mode`, so a `#leg` link does
  not scroll the page; an unknown hash shows the four-bar.
- **B12 Page layout.** Each mode's section is the root for its `data-*` attributes and holds `.intro`
  and a `.workspace` of `.controls` beside `.stage`, stacking below 800 px wide.
- **B13 Start-up failure.** If PyScript fails to load or the main script stops before Python is
  ready, the status line says "Python could not start. Try reloading the page." (PyScript would
  otherwise only log it).
- **B14 Vendoring.** `scripts/vendor.py` accepts tarballs only from registry.npmjs.org, verifies
  them, and skips a package already vendored at the pinned version, so cloud sessions can rerun it
  offline. It keeps all of PyScript's `dist/` (source maps included) and the five Pyodide files in
  the plan, which proved to be all the page needs.
- **B15 Dev server.** `scripts/serve.py` also takes `--directory` (for its own unit test) and serves
  `.toml` as `application/toml` and `.py` as `text/plain`.
- **B16 Extra checks.** Tests beyond the plan: a start-up error is shown, `pyscript.toml` maps every
  file in `beest/` and every `.py` in `app/` (hidden files aside), and unit tests for the server and
  the vendoring. A browser test fails if its page logs an error, unless it is marked
  `page_errors_expected`. CI keeps a Playwright trace of each failed browser test and stops the
  browser job after 20 minutes.

- **B17 Four-bar defaults.** Ground 60, crank 20, coupler 60 and rocker 50 mm, with the tracing point
  30 mm along and 0 sideways: a crank-rocker with an oval path (`DEFAULT_LENGTHS`, `DEFAULT_ALONG`,
  `DEFAULT_OFFSET` in `app/fourbar_mode.py`).
- **B18 Tracing point reach.** Along runs from −1 to 2 coupler lengths and sideways ±1 coupler length
  (`ALONG_SPAN`, `OFFSET_SPAN`); positive sideways is to the left of the coupler, looking from the
  crank end.
- **B19 Jammed animation.** A jammed linkage swings between 0° and its last angle before the jam,
  since the trace runs forwards only. One that jams at 0° is drawn still, and the four-bar then
  shows the coupler's and rocker's circles that fail to meet.
- **B20 Number boxes.** Every slider has a number box; typed values keep two decimals and are clamped
  to the bounds when the box is left. Sliders step 0.1 mm and speed runs 1–60 turns a minute
  (default 15). The keyboard moves through the number boxes rather than the sliders, and jam
  warnings are announced to screen readers.

- **B21 Two traces in the playground.** The numbers, down band and stride come from a trace at `ANGLES`,
  as the GA scores, and the drawing from one at `DRAW_ANGLES`; a leg counts as jammed if either
  jams (about 1 random leg in 2,000–7,000 jams at one sampling only). Jansen's stride shows as
  65.7 mm (66.1 at 360 angles).
- **B22 A jammed leg** shows "jams" in place of every measure and leaves the `data-*` measures empty;
  the warning names the jam from the trace on screen.
- **B23 Jansen beside the leg.** The playground shows Jansen's own measures at the current tolerance
  next to the leg's, for "Beat Jansen by hand". "Reset to Jansen" leaves the tolerance alone.
- **B24 Tolerance slider** bounds are `TOLERANCE_BOUNDS = (0.5, 4.0)` in `app/leg_mode.py`.

## Questions for Al

Append questions here as they arise, most important first, each with what it blocks and the
provisional answer the build went ahead with.

## Slide edits for Al

Append any place where the simulator and the slides now differ.

- "Scaling" on the slides is called normalisation in the simulator (Q8).
