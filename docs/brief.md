# Brief: the Evolving Machines simulator

Al's requirements, as handed over on 22 Oct 2026. This file is the source of truth for what was
decided. Open questions and their provisional answers live in [decisions.md](decisions.md); the
scoping work, measurements and risks are in [scoping.html](scoping.html).

## The course

"Evolving Machines" is a 3-day course for 6 Year 11/12 students (3 pairs), Tuesday 27 to Thursday
29 October 2026. Students evolve a Strandbeest (Theo Jansen) with a genetic algorithm, build it from
lolly sticks and race it. The simulator is hosted on Al's website (babissimo.net, see §7).

## 1. Decided

- **Frontend only**, Python in the browser via **PyScript**. No backend.
- **Three modes:**
  1. **Four-bar linkage:** sliders for the lengths, animated, with a jam warning and a trace of the
     coupler point's path.
  2. **Jansen leg playground:** sliders for the lengths, animated, with a jam warning and the foot
     path traced.
  3. **Strandbeest GA:** a parameters panel, an in-browser code editor and an **arena**. The arena
     is a **2D physics simulation of a whole beest's cross-section**.
- **The simulator measures whole beests,** not single legs: mirrored leg pairs, several crank throws
  and a body.
- **Two routes for students.** The code route edits `fitness` and `mutate`. The settings route
  changes population, mutation rate, mutation size, generations, fitness weights, **scaling** (the
  normalisation options below), and which genes may mutate.
- **Genes:** the 13 lengths (independent, see §2), plus leg count and crank phase. Changing the
  layout or topology is a stretch goal only.
- **Students choose** which ingredients go into the fitness, their weights, and **how ingredients
  are normalised.** Three options:
  1. Dividing by Jansen's value (Jansen = 1).
  2. Fixed limits for each ingredient.
  3. Each generation's own min/max.

  Students also flip ingredients where lower is better (1 − normalised).
- **Units** are set by lolly sticks. Lengths are in mm, hole to hole, capped at about 104 mm, with
  holes at least 5 mm from a stick's end.

## 2. Geometry (checked)

The holy numbers: a=38, b=41.5, c=39.3, d=40.1, e=55.8, f=39.4, g=36.7, h=65.7, i=49, j=50,
k=61.9, l=7.8, m=15.

- The crank axle O is at the origin. The crank tip C is on a circle of radius m:
  C = (m cos θ, m sin θ).
- The fixed pivot is G = (−a, −l).
- `circ(P, r1, Q, r2)` means the two intersections of circles of radius r1 about P and r2 about Q.
- Joint positions:
  - J2 = the max-y point of circ(C, j, G, b)
  - J3 = the min-x point of circ(G, d, J2, e)
  - J4 = the min-y point of circ(C, k, G, c)
  - J5 = the min-x point of circ(J3, f, J4, g)
  - Foot F = the min-y point of circ(J4, i, J5, h)
- A jam is any crank angle where a pair of circles doesn't intersect.
- The top triangle is G–J2–J3 (sides b, d, e). The bottom triangle is J4–J5–F (sides g, i, h).
- All 13 lengths are independent genes. Two sides of a triangle do not fix the third; the third
  sets the angle.
- **Size is a hidden degree of freedom.** Scaling every length scales the stride, so the stick cap
  is what stops evolution growing everything.
- **Mirrored leg:** the mirrored foot at crank angle θ is (−Fx, Fy) of the original at π−θ.
- **Throws:** pairs on throws at phases φ. The standard layout is 3 throws at 120°, carrying 6 legs.
- **Direction:** with θ increasing (counter-clockwise, y up), the foot moves +x along the ground, so
  the beest walks −x. The slides show travel to the left.
- **Four-bar mode** uses the same circle check, and Grashof's rule (S + L ≤ P + Q) predicts a full
  rotation.

## 3. Measured test cases

These are pinned in `tests/test_reference.py`.

**Single Jansen foot.** "Down" means within a tolerance of the foot's lowest point. Step height is
22.5 at every tolerance; the others depend on it:

| Counts as down within | Time down | Stride |
|---|---|---|
| 0.5 | 0.37 | 50.2 |
| 1 | 0.43 | 57.4 |
| 2 | 0.52 | 64.9 |
| 4 | 0.65 | 67.9 |

**Whole beest, level-body kinematic model.** At each crank angle the lowest foot carries the body,
and there's no slipping:

- **Body bob** = the range of the lowest foot's y over a turn.
- **Distance per turn** = the summed x travel of the supporting foot. The next foot takes over when
  it becomes the lowest.

| Beest | Body bob | Distance per turn |
|---|---|---|
| 1 pair | 2.19 | 125.9 |
| 2 pairs at 180° | 1.44 | 135.3 |
| 3 pairs at 120° | 0.08 | 141.1 |

This model ignores tipping. In 2D, a beest needs feet in front of and behind its centre of mass.
The 1-pair beest would really fall over.

These distances were summed over finely sampled angles with the takeover step left out, which
undercounts slightly; the continuous values are 125.96, 135.59 and 141.83 (see decisions.md, D3).

**Crossover.** Parents were working legs close to Jansen's, 300 pairs per row, and a child counts as
jammed if it fails at any of 180 crank angles:

| Parents within… of Jansen | Child jams: each length from one parent | Child jams: each length a random point between the parents |
|---|---|---|
| ±10% | 25% | 12% |
| ±25% | 35% | 13% |

**Four-bar.** Of about 480 random crank-rockers that fit on lolly sticks, **none** traced a figure of
eight when the tracing point was on a straight coupler. About 30% did with an offset point.

## 4. What the slides promise

Match these, or list the slide changes Al needs to make.

- **Day 1, Tue 13:30, four-bar mode:** make it turn fully, make it jam, find a figure of eight
  (needs an offset tracing point), find a nearly straight line, pick lengths to build.
- **Day 1, Tue 15:15, playground:** a jam warning, and **stride shown as a number** for "Beat Jansen
  by hand". A slide explains that the sim shows the foot relative to the body, with a
  direction-of-travel arrow; the sim shows that arrow too.
- **Day 2, Wed 09:00:** run **random search, hill climbing and the GA** for the same time each and
  compare, twice. These are presets of the GA settings: hill climbing = population 1, keep the best,
  mutation only; random search = fresh random genes each generation.
- **Day 2, Wed 10:45:**
  - Evolve a beest, with a graph of best and average score per generation.
  - Ingredients: stride or distance, step height, flatness, time down, plus a **jams flag** (a
    jammed leg scores 0).
  - The normalisation ("scaling") options in §1.
  - The winner must turn fully and fit on sticks.
  - **Print the leg template at full size, 1:1 mm**, to drill from.
- **Day 3:** the races are distance in 10 crank turns, stepping over a row of pencils in as few turns
  as possible, and crossing a towel. Comparing arena results with the real races is a planned
  extension.
- **Names used in the slide code:** `random_genes, leg_from, fitness, best, select` (tournament of 3),
  `crossover` (uniform), `mutate, clamp, POP_SIZE, GENERATIONS, ELITE, RATE`. The example
  `fitness(leg)` reads `leg.jams`, `leg.stride` and `leg.step_height`. The example `mutate` adds
  `random.gauss(0, 3)` with probability `rate`, then clamps.

## 5. Al's priority order

- By Tuesday 13:30: four-bar and playground.
- By Wednesday 09:00: GA, search presets, scaling, template printing.
- Nice to have: arena races, topology, and extensions such as repeated runs and the
  arena-versus-reality comparison.

## 6. Build window

Friday 23, Saturday 24 and Monday 26 October (Al is busy on Sunday). The first build runs
unattended overnight on Thursday 22 October; Al answers questions and course-corrects on Friday.

## 7. Hosting

babissimo.net is a Quarto site in `Babissimo/babissimo.github.io`. Each project there is its own
repo on its own subdomain (DNS at Cloudflare) with a card in that repo's `projects/projects.yml`.
Two deploy patterns exist: `Babissimo/ratchet`'s `site/` is a Cloudflare Worker serving static files
(wrangler, a custom domain, a `CLOUDFLARE_API_TOKEN` secret), and `Babissimo/torus-chess` is GitHub
Pages with a CNAME. The subdomain and host are not decided yet (decisions.md, Q12); nothing deploys
until they are.
