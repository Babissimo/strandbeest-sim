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
`docs/spikes/pymunk_beest.py`, which already walks. The crank keeps its speed whatever the load and
never stalls. Confirmed by Al.

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

### Q12 Hosting: changed
Al's answer: Cloudflare, as for his Ratchet site, at strandbeests.babissimo.net. `site/` is plain
static files with no build step and a `_headers` file; `deploy/` holds the Worker that serves it,
and `.github/workflows/deploy.yml` deploys it from `main` once the repository has a
`CLOUDFLARE_API_TOKEN` secret (B96–B98). A card in `projects/projects.yml` of
`Babissimo/babissimo.github.io` links to it from babissimo.net's projects page. The repo is
`Babissimo/strandbeest-sim` (private) until Al names it. Changed by Al.

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

### Q19 Template: changed
Students will not print templates, but the template stays in the simulator. It is A4 portrait at
1:1 mm. Each stick is drawn on its own at true length with hole centres marked, 5 mm end margins,
its letter, its hole-to-hole length and how many to cut for the chosen number of pairs. The chassis
holes (O, G, and the mirrored G) form a separate drilling diagram. A 100 mm calibration bar says
"check with a ruler". Printed through a print stylesheet, with an SVG download too. The four-bar
mode prints its four sticks the same way. Changed by Al.

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
  and flatness (weight 1, flipped), every other ingredient at weight 0, under the fixed limits (Q5)
  (`DEFAULT_WEIGHTS`, `FitnessSettings.normalisation`). On seeds 1 to 5 the default GA's winners
  step 12–81 mm, bob 0.5–1.1 mm and travel 174–230 mm a turn in the model, and all five walk in the
  arena without falling (136–230 mm a turn; Jansen 171), where every default that keeps step
  height at 0.5 has winners that fall. Changed by Al (Claude's recommendation at his request,
  checked in the arena).
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
  wrong way and scores a negative distance (clipping at 0 would hide which way it went). Confirmed
  by Al.
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
  takes to start. Sections are `#fourbar-mode`, `#leg-mode`, `#evolve-mode` and `#arena-mode`, so a
  `#leg` link does not scroll the page; an unknown hash shows the four-bar.
- **B12 Page layout.** Each mode's section is the root for its `data-*` attributes and holds `.intro`
  and a `.workspace` of `.controls` beside `.stage`, stacking below 800 px wide.
- **B13 Start-up failure.** If PyScript fails to load or the main script stops before Python is
  ready, the status line says "Python could not start. Try reloading the page." (PyScript would
  otherwise only log it).
- **B14 Vendoring.** `scripts/vendor.py` takes the runtime only from registry.npmjs.org (checked
  against the registry's sha512), pymunk only from PyPI (checked against PyPI's sha256), and cffi,
  pycparser and micropip only from Pyodide's GitHub release (each checked against the sha256 in
  `pyodide-lock.json`, B74). It skips anything already vendored at its pinned version, so cloud
  sessions can rerun it offline. It keeps all of PyScript's `dist/` (source maps included) and the
  five Pyodide files in the plan, which proved to be all the page needs, and saves the four wheels
  beside `pyodide.mjs`.
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

- **B25 Evaluations** are fitness calls. The GA and random search score every beest each generation,
  elites included as in the slides' loop; hill climbing scores only the child. Under per-generation
  normalisation, hill climbing's parent and random search's best so far are scored again beside the
  newcomers, since scores compare only within one normalisation.
- **B26 Budget.** A set `budget` replaces `generations` and is never exceeded (the last generation
  is cut short). `generations` counts generation 0, so 40 generations give 40 reports and 1,200
  evaluations. `BUDGET = 1500` is the default for comparing searches (Q17).
- **B27 Jammed legs** take no part in a generation's lowest and highest, and normalise to 0 in every
  mode (a jammed leg's 0 mm bob would otherwise look perfect once flipped). All-equal values, or a
  single working leg, give 0.5.
- **B28 `leg.normalised`** holds values before flipping (Jansen's own leg gives 1 under Jansen
  normalisation); the settings fitness applies the flip, so a student writes
  `1 - leg.normalised[...]`.
- **B29 Weights** must be 0 or more (flip an ingredient instead); all weights 0 scores 0.
- **B30 Limits.** Reversed limits are swapped; equal limits give 0 below, 0.5 at and 1 above.
- **B31 Jansen's reference leg** uses jam margin 0 whatever the run's margin, since a margin above
  1.43 mm jams Jansen's own leg.
- **B32 Gene mask.** Lengths left out of the mask hold the starting leg's value in every beest
  (Jansen's, or the design's under the Leg tab start, B90; generation 0 draws only the masked-in
  lengths) and are restored from the first parent after crossover and mutation.
- **B33 Layouts.** Every beest starts on the standard layout and only mutation changes it, so random
  search never varies layouts; a child takes a random parent's layout. With probability `RATE` the
  number of pairs moves by ±1 (throws evenly spaced again); otherwise each throw after the first
  moves by `gauss(0, 15)` degrees with probability `RATE`, as a length does (`PHASE_SIZE`).
- **B34 Tournament** entrants are drawn with replacement, so populations under 3 work; ties go to
  the first drawn. The GA refuses `elite >= pop`.
- **B35 Hill climbing** keeps the child on a tie, so a jammed start can drift.
- **B36 The report's best** is the beest the search keeps (the GA's best this generation, hill
  climbing's parent, random search's best so far); it also carries `best_jams` and `best_fits` for
  the winner checks, and the run's best beside it (B85).
- **B37 Scores** must be finite real numbers; True and False are refused as slips
  (`return leg.jams`). `mutate` must return 13 finite numbers; the engine does not clamp them, and
  `fits` shows when they break the stick bounds.
- **B38 Student code** runs as its own module, "student", compiled as `<editor>`, with nothing
  injected: `SOURCE` imports `random` and `clamp` itself. `fitness` gets copies, so it cannot change
  a cached beest.
- **B39 Caching.** `leg_from` results are cached for one generation only (a traced leg is about
  200 KB).
- **B40 Test import mode.** pytest imports test files in importlib mode (`addopts` in
  `pyproject.toml`), since the plan puts a `test_leg.py` in both `tests/` and `tests/e2e/` and the
  default mode cannot collect two test files with one name.

- **B41 Worker start.** The GA worker starts the first time Evolve is on screen, so a four-bar
  lesson never loads a second Python, and counts as failed after 90 s (`WORKER_START_S`). It also
  answers a start-up check, because PyScript reports a worker ready even when its script raised.
- **B42 Fresh workers.** Stop, a worker whose call fails, and every run of editor code each get a
  fresh worker (editor code may have changed the engine's modules); settings runs reuse it.
- **B43 Errors.** Settings errors show beside Run and editor-code errors under the editor (B52), both
  in `data-error` and without a console log; faults in the simulator itself also go to the console,
  so browser tests fail on them.
- **B44 Settings panel.** Search, stop after, population, mutation rate and size, and seed are on
  show; Fitness (normalisation, weights, flips, fixed limits) and "More settings" (elite, crossover,
  gene mask, layout, down tolerance, jam margin) sit in closed sections. Ingredient lists come from
  `fitness.INGREDIENTS`. The form keeps mutation rate within 0–1 and down tolerance within the leg
  playground's bounds (B24); every other limit shows the engine's own message.
- **B45 Presets.** Hill climbing shows population 1, elite 0 and crossover none (`HILL_SETTINGS`)
  and starts from "Random, turning fully" (`HILL_START`, B88), which the student can change; it
  gives the GA's values back when left, keeping a start chosen meanwhile. Choosing hill or random
  switches "Stop after" to 1,500 evaluations, and the GA keeps that, so all three compare on one
  budget. Settings a preset ignores are greyed out. Changed by Al (hill climbing starts from the
  first beest that turns fully).
- **B46 Fixed limits** show to 4 significant figures; a box left as shown sends the exact surveyed
  value.
- **B47 Graph.** It keeps the last 8 runs (`MAX_SERIES`, one per colour); best is solid, average
  dashed, x is "Evaluations (beests scored)". "Relative to this generation" labels the axis when
  every run on the graph uses it, otherwise the legend marks those runs. Hovering shows each run's
  numbers. The ingredients view has one small panel per ingredient, each on its own scale.
- **B48 Best beests panel** shows two beests side by side: the engine's best of the latest
  generation and the best of the whole run so far (B85), each labelled with the run and its
  generation, with its own numbers and winner checks. When they are the same beest the run's column
  says so instead of drawing it twice (B86). Each is drawn with the body still and the ground
  moving, the 0° pair dark and in front, the arrow pointing left, turned by one crank (B87); they
  redraw at most every 250 ms during a run. `data-generation` counts from 0. Changed by Al.
- **B49 Throw placement.** `measures.throw_steps` places the crank throws for both the scoring and
  the drawing, so they agree.

- **B50 Editor.** PyScript's own CodeMirror (the `codemirror` export of `vendor/pyscript/core.js`)
  with line numbers, Python highlighting, 4-space indents and Tab to indent (Esc then Tab leaves
  the editor). It loads with the page, about 450 KB from the vendored folder, so nothing more is
  vendored.
- **B51 Route.** "Score and mutate with: the settings / my code". On the code route the weights,
  flips and mutation size are greyed out and not sent; normalisation and fixed limits stay in use
  because they fill `leg.normalised`, and the mutation rate reaches the student's `mutate` as
  `rate`. The route is remembered in browser storage, and code runs say "your code" in the legend.
- **B52 Errors in the editor's code** show under the editor, with the line marked and scrolled into
  view while the editor still holds the code that ran, and the traceback (quoting the editor's
  lines) in a closed section. Generations already scored stay on the graph, labelled "(ended by an
  error in your code)".
- **B53 Storage.** The editor's text is saved in browser storage after each edit; the slide code
  itself is never stored, so a changed `SOURCE` reaches students after a reload. If storage is
  blocked or full, the editor starts from the slide code and says the browser is not keeping it.
- **B54 Reset to slide code** asks first only when the text differs from the slide code.
- **B55 Help.** A closed "What your code can use" section lists `leg`'s attributes with units,
  `leg.normalised` (before flipping), `leg.genes` and `mutate`'s arguments.

- **B56 Stick counts.** Sticks b to k are made 2 per pair (one per leg) and the crank m 1 per pair,
  since both legs of a pair share a crank tip (`STICKS_PER_PAIR`). Confirmed by Al.
- **B57 Triangles.** The triangles b–d–e and g–i–h print as three separate sticks each; every label
  names the joints at its holes ("G to J2", `LEG_STICK_ENDS`) in place of a drawing of the
  assembled leg.
- **B58 Template page.** 10 mm margins; each stick is a 10 mm wide outline with rounded ends, each
  hole a 3 mm circle with a 6 mm cross, the label above the stick and its letter also on it when it
  fits. Two sticks drawn 90 mm wide or less share a row, the chassis comes last, and a row that
  would cross the bottom margin starts a new page.
- **B59 Calibration bar** on every page, with 10 mm ticks, "This bar should be 100 mm long: check it
  with a ruler before you drill." and the page number, since pages are separated at the drill.
- **B60 Chassis diagram** at 1:1, labelled "O (crank axle)", "G" and "G (mirrored leg)" (each label
  pointing away from the other pivot), with a caption giving a and l. When it is wider than the
  page (a about 70 mm or more) it is turned a quarter turn and says so. It gives no count of
  chassis pieces: the chassis is made of bamboo skewers and lolly sticks (Al), and nothing more is
  drawn for it. Confirmed by Al.
- **B61 Unprintable input** raises ValueError rather than being clipped or shrunk: a stick over
  180 mm, a chassis too big even when turned, a length that is not a positive finite number, or
  other than 13 genes. Anything within the gene bounds prints.
- **B62 Copy.** Labels say "make 6" rather than "cut 6", since sticks need not be cut short.
- **B63 Print route.** The pages go into a print-only container and the print stylesheet shows only
  that, one SVG per A4 sheet at 210 × 297 mm, unscaled, under
  `@page { size: A4 portrait; margin: 0 }`. The container is cleared after printing and whenever a
  print starts that no button asked for, so Ctrl+P prints the page itself (with 12 mm padding on
  every sheet).
- **B64 Download SVG** saves one standalone A4 SVG per page in one click
  (`strandbeest-leg-template.svg`, or `…-page-1-of-3.svg` for longer templates). Jansen's beest and
  each of 500 random beests fit on one page.
- **B65 Evolve's template** is the best beest of the whole run so far (B85), with its number of
  pairs, and the panel says so; its buttons stay disabled until a run has a best. A beest that jams
  or does not fit can still be printed, since the winner checks already say so. The four-bar's
  "Print the sticks" and "Download SVG" sit below its playback controls. Changed by Al.
- **B66 Template fonts** list Arimo and Liberation Sans (Arial's widths) before `sans-serif`, since
  text is placed by estimated Arial widths.

- **B67 Tipping.** At each crank angle the supporting feet are those within the down tolerance of
  that angle's lowest foot (one setting for "down", Q4), and the beest tips if its centre of mass
  lies outside their x range; a foot exactly under the centre of mass holds it up. The centre of
  mass sits over the crank axle (`CENTRE_OF_MASS_X_MM = 0`). At 1 mm Jansen's beest tips on 1 pair
  and stays up on 2 pairs at 180° (above 0.65 mm) and 3 at 120° (above 0.28 mm). This check stays
  as `leg.tips` and the `upright` ingredient, a quick check that is stricter than the arena (B95);
  whether a beest falls over is judged by the arena's 30° rule (B70), which Evolve's winner checks
  run (B94). Changed by Al.
- **B68 A jammed leg** has `tips` None (its foot path stops short, so there is nothing to check) and
  `upright` 0.
- **B69 `upright` limits** are fixed at 0 and 1 rather than percentiles, since only 5.4% of random
  working legs stay up. Under Jansen normalisation `upright` divides by Jansen's own value, which is
  0 at tolerances of 0.28 mm or less, so it then scores 0 for every beest (the slider's 0.5 mm
  minimum stays clear of this). Its default weight is 0 (S3).

- **B70 Arena tipping.** A beest has tipped once its chassis leans more than 30° from level
  (`TIP_ANGLE_DEG`) or its chassis box touches the ground, checked at every step from the start.
  Jansen's beest on 1 pair tips 0.27 turns in. Confirmed by Al.
- **B71 Arena body.** The chassis is a 30 g box round O and both G pivots with a 5 mm margin
  (`CHASSIS_MARGIN_MM`); each triangle (b d e, g h i) is one rigid body of three 1 g sticks; the
  crank is 1 g per throw; feet are circles of 2 mm radius; the parts pass through each other but
  all touch the ground; friction is 1.0 (`FRICTION`). Over 10 turns Jansen's beest walks 170.2 mm
  a turn on 2 pairs, 170.8 on 3 and 179.1 on 4 (the kinematic model gives 162.7 and 170.2 for 2 and
  3).
- **B72 Arena start.** The lowest point starts 0.5 mm above the ground and the beest stands for
  300 steps with the crank held (`DROP_MM`, `SETTLE_STEPS`). Travel is measured at the axle from
  the moment the crank starts, and turns are motor steps ÷ 600, since the crank speed is constant
  (Q2). The solver makes 30 passes a step (`SOLVER_ITERATIONS`); at 10, distance shifts about 2%.
- **B73 Arena pose.** Legs start from the tracked trace at 180 angles, as `leg_from` uses, so the
  arena and the GA agree on which legs jam; a jammed leg is refused with the GA's plain reason.
- **B74 Pyodide's wheels.** The cffi and pycparser wheels that match `pyodide-lock.json` exist only
  in Pyodide's GitHub release tarball (PyPI has no cffi for this platform, and jsDelivr is
  blocked), so `vendor.py` streams that tarball and stops after about 170 MB, about 18 s the first
  time (B14).
- **B75 Arena tab loading.** pymunk loads the first time the tab opens, with "Loading the physics
  engine…"; if it fails a plain message appears, the other tabs keep working, and opening the tab
  again tries again.
- **B76 Arena beest.** Jansen's leg, the Leg tab's current leg, or the best beest of Evolve's whole
  run so far (B85; handed over each time Evolve shows its bests, after its own panel, and the
  arena's hint says so; an error there is logged and Evolve carries on), on 1–4 pairs with even
  phases; an evolved layout keeps its phases while Pairs is its own number. Opening the tab stands
  up a changed leg or best unless the beest on show has started; otherwise, and whenever a best
  arrives while the tab is on show, the arena keeps the old one and says to press Reset, so
  Evolve's generations never rebuild it or stop a walk. A best other than the one on show (in
  lengths or layout) brings its own number of pairs, unless Pairs or the race was changed. A beest
  that fails to build for any reason but a jam gets a plain message, and the fault is logged.
  Changed by Al (the run's best in place of the latest generation's).
- **B77 Arena timing.** The crank runs in real time at one turn a second; a slow frame advances at
  most 0.1 s (`MAX_FRAME_S`), so a slow device runs slower rather than jumping. Pyodide manages
  17,000–20,000 steps a second for 3 pairs, so a 60 fps frame of 10 steps takes under 1 ms.
  Distance per turn shows once a whole turn is done.
- **B78 Arena view** follows the axle, with distance markers every 100 mm; the other pairs are
  drawn faint behind the phase-0 pair, and the chassis turns red once the beest has tipped.

- **B79 Courses** start 20 mm ahead of the beest's frontmost part and run towards −x
  (`RUN_UP_MM`). Confirmed by Al.
- **B80 Pencils.** 8 pencils (`PENCIL_COUNT`) with friction 0.3 (`PENCIL_FRICTION`), as painted
  wood. At friction 1.0 a caught foot lets the constant-speed crank lever Jansen's 3-pair beest over
  backwards, in all 20 runs tried. Confirmed by Al.
- **B81 Towel.** 500 mm long (`TOWEL_LENGTH_MM`) with friction 1.5; its surface is a smooth cosine
  2 mm high every 10 mm (steepest slope 32°), because half-round bumps tipped Jansen's 3-pair beest
  in 6 of 20 runs, while on the smooth surface 3 and 4 pairs finished 50 runs of 50. Confirmed by
  Al.
- **B82 Finishing.** A beest is across once every foot is past the last pencil or the towel's far
  end, checked every 10 physics steps (`CHECK_STEPS`). The distance race lasts 10 turns on flat
  ground; the others give up after 20 turns (`MAX_RACE_TURNS`). Touching a pencil or the towel with
  the chassis counts as falling over. Confirmed by Al.
- **B83 Races run in real time** in the page: about 4 s for the pencils, 4.5 s for the towel and
  10 s for distance. Jansen's beest falls over in every race on 1 pair, and on the pencils and the
  towel on 2; on 3 pairs it crosses the pencils in 3.85 turns and the towel in 4.25, in the browser
  as under CPython.

- **B84 Paused start.** Every animation starts paused with the crank at 0° and the traced path
  drawn; a change while paused redraws the still frame where the crank stopped, rather than at 0°.
  The arena mirrors `data-playing` as well, so every tab reports it the same way.
- **B85 The run's best** is the highest-scoring of the generations' best beests, a tie going to the
  later one, so elite copies, hill climbing's parent and random search's best so far are always the
  run's best too. It keeps the generation it first led while the same beest stays best. Under
  per-generation normalisation scores do not compare across generations, so the latest best stands
  for the run, and the panel says why.
- **B86 Same beest.** The two bests count as one beest when their lengths and layout are equal; the
  run's column then shows a sentence in place of a second drawing and numbers (`data-same-best`).
  Both columns keep their place, so nothing jumps when a run's bests part or meet again.
- **B87 One crank in Evolve.** The two best beests share one Play button, speed and crank angle, so
  they turn in step. A jammed beest there turns as far as the jam and waits until the crank comes
  round again, rather than swinging back as in the four-bar and leg tabs (B19).
- **B88 Start from.** Evolve's "Start from" (`RunSettings.start`, `STARTS`) is "Random beests" (S7,
  the default), "Random, turning fully", "Jansen and mutants" or "Leg tab design". Each random beest
  of the turning start is drawn again until it turns fully, at most 500 times (`START_TRIES`); the
  run then stops with a plain message beside Run, as for a refused setting. The legs built to check
  are the ones scored, and checking is not an evaluation.
- **B89 Random search** makes every generation's newcomers the way the run starts: random, random
  until they turn, or mutated copies of Jansen's leg or the design, so it samples around the
  starting leg when one is chosen. The starting leg itself is scored only in generation 0.
- **B90 Mutant starts.** The first beest is the leg itself (Jansen's, or the Leg tab's lengths in
  `start_genes`, clamped) and the rest are the engine's `mutate` of it at the run's rate and size,
  on the code route too; lengths outside the mask keep the leg's. The rate and size boxes stay in
  use for these starts under random search and on the code route, but not for hill climbing, which
  starts from the leg itself.
- **B91 Design check.** When the start is the Leg tab design, Evolve traces it at the GA's angles
  and the panel's jam margin when the start or the margin is chosen, when the tab is shown and
  when Run is pressed, and warns in words if it jams (`data-design-jams`); the run still goes
  ahead.
- **B92 The whole generation.** Below the best beests a grid shows every beest the generation
  tried (the GA's population, hill climbing's parent and child, random search's newcomers), best
  first with its score, all at one scale so their sizes compare. They turn with the best beests'
  crank and Play button, traced at 90 angles a turn (`POPULATION_ANGLES`, or the GA's 180 when the
  two samplings disagree on a jam); a beest that jams is grey, still at 0° and labelled "jams".
- **B93 Grid timing.** Each report carries the generation's lengths to 0.01 mm
  (`POPULATION_DECIMALS`), about 5 KB for 30 beests. The page traces about 4 ms of beests a frame
  (`TRACE_BUDGET_S`), takes a new generation at most once a second during a run
  (`POPULATION_EVERY_S`) and always the last, and turns each leg position into canvas path data
  once per layout. In a default run in the cloud session frames stay at 16.7 ms median and 33 ms at
  the 95th percentile (16.7 ms without the grid).
- **B94 Arena winner check.** Once a run ends (finished, stopped, or ended by an error after some
  generations), its best walks on flat ground for `ARENA_TURNS` (10) on the page, about 8 ms of
  physics a frame (`ARENA_BUDGET_S`), and stops as soon as it falls over. The check reads
  "Checking that it walks in the arena…", then a tick with its mm a turn, or a cross saying when it
  fell or that it stays up without walking forwards, towards −x (`data-run-winner-walks`,
  `data-run-arena-distance`). A beest the arena cannot stand up gets the arena's reason, and a new
  run ends a check under way. The physics engine loads once for this and the Arena tab
  (`app/physics.py`); if it cannot load, the check says so plainly and the other checks stand.
- **B95 Upright** is labelled "Upright (quick check)", and the fitness panel and the code route's
  help say it is stricter than the arena. Its weight stays 0 by default.
- **B96 Hosting.** `deploy/wrangler.jsonc` serves `site/` from a Worker with no script, named
  `strandbeest-sim`, on the custom domain strandbeests.babissimo.net with workers.dev and preview
  URLs off, as Ratchet's site is (Q12). Wrangler 4.148.0, Ratchet's version, is pinned in
  `deploy/package.json` and its lockfile. The configuration sits beside `site/` rather than in it,
  so it is not served. Files keep Cloudflare's default caching (browsers check for a newer copy on
  each visit), so a deploy shows at once.
- **B97 Deploy workflow.** `.github/workflows/deploy.yml` deploys on pushes to `main` that touch
  `site/`, `deploy/`, `scripts/vendor.py` or the workflow, and when run by hand; pull requests, and
  runs by hand from other branches, get a dry run, which fails on a file over 25 MiB. It does not
  wait for CI, as Ratchet's does not, since `main` changes only through checked pull requests. It
  holds the token, so its actions are pinned to commits and it uses no caches; the account id is
  written in it, as in Ratchet's (an identifier, not a credential). A deploy uploads 97 files,
  19 MB in all, the largest Pyodide's 9.6 MB wasm, against 20,000 files a version on the free plan.
- **B98 Types and headers.** Cloudflare sends no Content-Type for `.py` and `.whl`, so `site/_headers`
  gives them `text/plain; charset=utf-8` and `application/octet-stream`, as `scripts/serve.py`
  does, and `tests/test_headers.py` keeps the two in step, isolation headers included. Every other
  type the page loads comes from Cloudflare's table. Under `wrangler dev` every response, 404s
  included, carries both isolation headers, and the whole browser suite passes against it.
  `site/.assetsignore` keeps `__pycache__` out of a deploy made from a machine that has run the
  tests.

## Questions for Al

Most important first, each with what it blocks and the provisional answer the build went ahead with.

- **Fixed limits below Jansen.** Jansen is above the 95th percentile on stride (66 against 33 mm)
  and time down, and below the 5th on bob, so under the limits normalisation anything as good as
  Jansen clips to 1. Distance spans −358 to 174 mm because 55% of random working legs walk the wrong
  way. Under the default fitness (S3) distance saturates at the survey's 95th percentile, 174 mm a
  turn, so a winner gains nothing from walking further. Blocks nothing. Built on Q5 as written.
- **Runs on one graph.** The graph keeps the last 8 runs (B47), a ninth taking the oldest's place.
  Is that enough for a lesson's comparisons? Blocks nothing. Built on 8.

## Slide edits for Al

Append any place where the simulator and the slides now differ.

- "Scaling" on the slides is called normalisation in the simulator (Q8).
- The student code imports `clamp` from `beest.ga`, where the slides' code may assume it is already
  defined (B38).
- A `fitness` that returns True or False is refused with a message (B37).
- Hill climbing keeps the child on a tie (B35).
- Tracebacks from the editor's code name the file `<editor>`.
- On the code route the slide's `mutate` uses its own `gauss(0, 3)`, so the panel's mutation size
  does not apply.
- Students can read `leg.tips` and `leg.upright`, and there is a sixth ingredient, `upright`
  (B67, B69).
- The settings route's default fitness is distance and flatness under the fixed limits (S3); the
  slides' example `fitness`, the code route's starting text, still scores stride and step height.
