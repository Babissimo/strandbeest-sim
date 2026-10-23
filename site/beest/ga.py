"""The genetic algorithm with the names from the slides, and its two rivals: hill climbing and
random search.

Genes are a plain list of 13 lengths in mm, a to m. Inside `run` each beest's layout (how many
pairs, at which throw angles) travels beside its genes.
"""
from __future__ import annotations

import functools
import math
import random
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field, replace
from numbers import Real

from .fitness import FitnessSettings, ingredient_values, normalise, settings_fitness
from .geometry import JAM_MARGIN_MM, LENGTH_NAMES
from .leg import (DOWN_TOLERANCE_MM, LENGTH_BOUNDS, PAIRS_BOUNDS, RANDOM_SPREAD, Layout, Leg,
                  jansen_lengths, leg_from)

POP_SIZE = 30
GENERATIONS = 40
ELITE = 2
RATE = 0.2
MUTATION_SIZE = 3.0
TOURNAMENT = 3
# The evaluations each search gets when searches are compared.
BUDGET = 1500
# How far a throw angle moves when it mutates, in degrees.
PHASE_SIZE = 15.0
PRESETS = ("ga", "hill", "random")
CROSSOVERS = ("uniform", "blend", "triangles", "none")
# How a run makes its first beests: "random" draws each length within RANDOM_SPREAD of Jansen's;
# "turning" draws again until the beest turns fully; "jansen" and "design" take Jansen's leg or
# RunSettings.start_genes, then mutated copies of it.
STARTS = ("random", "turning", "jansen", "design")
LEG_STARTS = frozenset({"jansen", "design"})
# A beest that turns fully is drawn at most this many times before the run gives up.
START_TRIES = 500
# Under "triangles" crossover each triangle's three sides come from the same parent.
TRIANGLES = ("bde", "ghi")
# A report's plain form gives the generation's lengths to this many decimals (0.01 mm), finer than
# any drawing of them shows, so it stays small.
POPULATION_DECIMALS = 2


def random_genes() -> list[float]:
    """Each length drawn evenly within RANDOM_SPREAD of Jansen's, then clamped."""
    return clamp([random.uniform(x * (1 - RANDOM_SPREAD), x * (1 + RANDOM_SPREAD))
                  for x in jansen_lengths()])


def clamp(genes: list[float]) -> list[float]:
    """Each length moved back inside LENGTH_BOUNDS if it has strayed outside."""
    return [min(max(x, LENGTH_BOUNDS[name][0]), LENGTH_BOUNDS[name][1])
            for name, x in zip(LENGTH_NAMES, genes)]


def mutate(genes: list[float], rate: float, size: float = MUTATION_SIZE) -> list[float]:
    """Each length, with probability `rate`, nudged by random.gauss(0, size) mm; then clamped."""
    child = []
    for length in genes:
        if random.random() < rate:
            length = length + random.gauss(0, size)
        child.append(length)
    return clamp(child)


def crossover(a: list[float], b: list[float], kind: str = "uniform") -> list[float]:
    """A new child from two parents' genes.

    "uniform": each length from one parent or the other. "blend": each length a random point
    between the parents'. "triangles": as uniform, but b, d, e come from one parent together, and
    so do g, h, i. "none": a copy of the first parent.
    """
    if kind == "uniform":
        return [random.choice((x, y)) for x, y in zip(a, b)]
    if kind == "blend":
        return [x + random.random() * (y - x) for x, y in zip(a, b)]
    if kind == "triangles":
        child = []
        chosen: dict[str, list[float]] = {}
        for k, name in enumerate(LENGTH_NAMES):
            team = next((t for t in TRIANGLES if name in t), name)
            if team not in chosen:
                chosen[team] = random.choice((a, b))
            child.append(chosen[team][k])
        return child
    if kind == "none":
        return list(a)
    raise ValueError(f"crossover must be one of {', '.join(CROSSOVERS)}, not {kind!r}")


def tournament(scores: list[float]) -> int:
    """Draw TOURNAMENT beests at random (the same one may come up twice); the best one's place."""
    entrants = [random.randrange(len(scores)) for _ in range(TOURNAMENT)]
    return max(entrants, key=lambda k: scores[k])


def select[T](population: list[T], scores: list[float]) -> T:
    """A parent chosen by tournament."""
    return population[tournament(scores)]


def best[T](population: list[T], scores: list[float]) -> tuple[T, float]:
    """The highest scorer and its score (the first of several that tie)."""
    k = max(range(len(scores)), key=lambda k: scores[k])
    return population[k], scores[k]


def mutate_layout(layout: Layout, rate: float) -> Layout:
    """With probability `rate` the number of pairs moves by one, and the throws are spread evenly.

    Otherwise each throw after the first, with probability `rate`, moves by
    random.gauss(0, PHASE_SIZE) degrees.
    """
    if random.random() < rate:
        pairs = min(max(layout.pairs + random.choice((-1, 1)), PAIRS_BOUNDS[0]), PAIRS_BOUNDS[1])
        if pairs != layout.pairs:
            return Layout(pairs)
    phases = [layout.phases[0]]
    for phase in layout.phases[1:]:
        if random.random() < rate:
            # A tiny negative angle wraps to exactly 360.0 in floating point.
            phase = (phase + random.gauss(0, PHASE_SIZE)) % 360 % 360
        phases.append(phase)
    return Layout(layout.pairs, tuple(phases))


@dataclass(frozen=True)
class RunSettings:
    """Everything one run needs besides the fitness and mutate functions.

    preset: "ga"; "hill" (hill climbing: one parent, keep the better of parent and child, mutation
    only; pop, elite and crossover do not apply); or "random" (random search: fresh random genes
    every generation, keeping the best so far; elite, rate, size, crossover and layout_mutates do
    not apply). Under "generation" normalisation hill climbing's parent and random search's best
    so far are scored again beside each generation's newcomers.
    budget: when set, the run makes as many fitness evaluations as this allows, whatever
    `generations` says, and never more; the last generation is cut short to fit.
    mask: the lengths that may change. The others hold the starting leg's value (Jansen's, or
    start_genes for the "design" start) in every beest.
    start: how the first beests are made (STARTS). Under "jansen" and "design" the first is the
    leg itself and the rest are copies put through `mutate` at `rate` and `size`. Random search
    makes every generation's newcomers the same way. Checking whether a beest turns fully is not
    an evaluation. start_genes: the 13 lengths of the "design" start.
    tol: how close to its lowest point a foot counts as down, in mm. margin: see leg_from.
    """
    preset: str = "ga"
    pop: int = POP_SIZE
    generations: int = GENERATIONS
    budget: int | None = None
    elite: int = ELITE
    rate: float = RATE
    size: float = MUTATION_SIZE
    crossover: str = "uniform"
    mask: frozenset[str] = frozenset(LENGTH_NAMES)
    layout_mutates: bool = False
    seed: int = 1
    fitness: FitnessSettings = field(default_factory=FitnessSettings)
    tol: float = DOWN_TOLERANCE_MM
    margin: float = JAM_MARGIN_MM
    start: str = "random"
    start_genes: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "mask", frozenset(self.mask))
        if self.preset not in PRESETS:
            raise ValueError(f"preset must be one of {', '.join(PRESETS)}, not {self.preset!r}")
        if self.start not in STARTS:
            raise ValueError(f"start must be one of {', '.join(STARTS)}, not {self.start!r}")
        if self.start_genes is not None:
            numbers = [_number(x) for x in self.start_genes]
            if len(numbers) != len(LENGTH_NAMES) or None in numbers:
                raise ValueError(f"start_genes must be {len(LENGTH_NAMES)} ordinary numbers, "
                                 f"a to m, not {self.start_genes!r}")
            object.__setattr__(self, "start_genes", tuple(numbers))
        elif self.start == "design":
            raise ValueError("the design start needs start_genes, the design's 13 lengths")
        if self.crossover not in CROSSOVERS:
            raise ValueError(f"crossover must be one of {', '.join(CROSSOVERS)}, "
                             f"not {self.crossover!r}")
        if not self.mask <= set(LENGTH_NAMES):
            raise ValueError(f"the mask may hold only lengths a to m, not {sorted(self.mask)}")
        budget = 1 if self.budget is None else self.budget
        for name, count, lowest in (("pop", self.pop, 1), ("generations", self.generations, 1),
                                    ("budget", budget, 1), ("elite", self.elite, 0)):
            if isinstance(count, bool) or not isinstance(count, int) or count < lowest:
                raise ValueError(f"{name} must be a whole number from {lowest}, not {count!r}")
        if self.preset == "ga" and self.elite >= self.pop:
            raise ValueError(f"elite ({self.elite}) must be smaller than the population "
                             f"({self.pop}), or no children are made")
        for name, value in (("rate", self.rate), ("size", self.size), ("tol", self.tol)):
            if not 0 <= value < math.inf:
                raise ValueError(f"{name} must be 0 or more, not {value}")
        if not math.isfinite(self.margin):
            raise ValueError(f"margin must be an ordinary number, not {self.margin}")


@dataclass(frozen=True)
class Member:
    """One beest a generation tried: its genes, layout, score and whether it jams."""
    genes: list[float]
    layout: Layout
    score: float
    jams: bool


@dataclass(frozen=True)
class Report:
    """One generation's results.

    The best beest is the one the search keeps: the GA's best in this generation, hill
    climbing's parent, or random search's best so far. `best_values` are its raw ingredients;
    `best_jams` and `best_fits` are its winner checks. `mean_score` covers the beests this
    generation tried (hill climbing's parent and child), which `population` lists in the order
    they were scored. `evaluations` counts every fitness call so far.

    The `run_best_` fields describe the best beest of the whole run so far in the same way:
    the highest-scoring of the generations' best beests, a tie going to the later one.
    `run_best_generation` is the generation it first led. Under per-generation normalisation
    scores compare only within one generation, so the latest best is the run's best.
    """
    generation: int
    evaluations: int
    best_score: float
    mean_score: float
    best_genes: list[float]
    best_layout: Layout
    best_values: dict[str, float]
    best_jams: bool
    best_fits: bool
    run_best_generation: int
    run_best_score: float
    run_best_genes: list[float]
    run_best_layout: Layout
    run_best_values: dict[str, float]
    run_best_jams: bool
    run_best_fits: bool
    population: list[Member]

    def as_dict(self) -> dict:
        """The report as plain dicts, lists and numbers, ready to send from a web worker.

        Each member of the population is `{"genes", "phases", "score", "jams"}`, its lengths
        rounded to POPULATION_DECIMALS.
        """
        plain = asdict(replace(self, population=[]))
        plain["best_layout"]["phases"] = list(self.best_layout.phases)
        plain["run_best_layout"]["phases"] = list(self.run_best_layout.phases)
        plain["population"] = [{"genes": [round(x, POPULATION_DECIMALS) for x in m.genes],
                                "phases": list(m.layout.phases), "score": m.score,
                                "jams": m.jams} for m in self.population]
        return plain


# The file name student code is compiled under, so tracebacks give the editor's line numbers.
EDITOR = "<editor>"


class StudentCodeError(Exception):
    """fitness or mutate gave back something the GA cannot use.

    `function` names which, and `line` is the editor line that defines it (None when it did not
    come from the editor).
    """

    def __init__(self, function: str, message: str, line: int | None = None):
        super().__init__(function, message, line)
        self.function = function
        self.message = message
        self.line = line

    def __str__(self) -> str:
        return self.message


class StartError(ValueError):
    """The run could not make a beest the way its start asks, such as one that turns fully."""


def _editor_line(fn: object) -> int | None:
    code = getattr(fn, "__code__", None)
    return code.co_firstlineno if code is not None and code.co_filename == EDITOR else None


def _number(value: object) -> float | None:
    """The value as a float if it is a finite real number, else None.

    True and False are refused: `return leg.jams` is a slip, not a score.
    """
    if not isinstance(value, Real) or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _described(value: object) -> str:
    shown = repr(value)
    if len(shown) > 40:
        shown = shown[:37] + "..."
    if value is None or isinstance(value, Real):
        return shown
    kind = "text" if isinstance(value, str) else f"a {type(value).__name__}"
    return f"{shown} ({kind})"


def _checked_score(score: object, fitness_fn: object) -> float:
    number = _number(score)
    if number is not None:
        return number
    hint = " Check that every way through it ends with return." if score is None else ""
    raise StudentCodeError("fitness", f"fitness returned {_described(score)}, but it must return "
                                      f"an ordinary number.{hint}", _editor_line(fitness_fn))


def _checked_genes(genes: object, mutate_fn: object) -> list[float]:
    count = len(LENGTH_NAMES)
    line = _editor_line(mutate_fn)
    if not isinstance(genes, (list, tuple)):
        hint = " Check that it ends with return." if genes is None else ""
        raise StudentCodeError("mutate", f"mutate returned {_described(genes)}, but it must "
                                         f"return a list of {count} lengths.{hint}", line)
    if len(genes) != count:
        raise StudentCodeError("mutate", f"mutate returned {len(genes)} lengths, but a leg "
                                         f"needs {count} (a to m).", line)
    numbers = [_number(x) for x in genes]
    for name, x, number in zip(LENGTH_NAMES, genes, numbers):
        if number is None:
            raise StudentCodeError("mutate", f"mutate returned {_described(x)} for length {name}, "
                                             f"but every length must be an ordinary number.", line)
    return numbers


# Genes and layout of a beest not built yet.
Plan = tuple[list[float], Layout]


@dataclass(frozen=True)
class _Beest:
    """One beest in a run: the genes it was built from, its layout and the Leg built from them."""
    genes: tuple[float, ...]
    layout: Layout
    leg: Leg


class _Search:
    """What the three searches share: making, building and scoring beests, and the counts."""

    def __init__(self, settings: RunSettings, fitness_fn: Callable[[Leg], object],
                 mutate_fn: Callable[[list[float], float], object]):
        self.settings = settings
        self.fitness_fn = fitness_fn
        self.mutate_fn = mutate_fn
        # Jansen's reference beest turns fully whatever the run's jam margin.
        self.jansen = leg_from(jansen_lengths(), tol=settings.tol)
        # The leg the run starts from, whose lengths outside the mask every beest keeps.
        self.base = (clamp(list(settings.start_genes)) if settings.start == "design"
                     else list(self.jansen.genes))
        self.fixed = [name not in settings.mask for name in LENGTH_NAMES]
        # Under per-generation normalisation the beest a search keeps is scored again each generation.
        self.together = settings.fitness.normalisation == "generation"
        self.generation = 0
        self.evaluations = 0
        # The beests built for the last generation, by genes and layout; leg_from is deterministic.
        self.built: dict[tuple[tuple[float, ...], Layout], _Beest] = {}
        # Newcomers already built to check that they turn fully, until the next build.
        self.checked: dict[tuple[tuple[float, ...], Layout], _Beest] = {}
        # The run's best beest so far, its score and the generation it first led.
        self.run_best: tuple[_Beest, float, int] | None = None

    def more(self, cost: int = 1) -> bool:
        """Whether a further generation costing at least `cost` evaluations fits in the run."""
        if self.settings.budget is None:
            return self.generation < self.settings.generations
        return self.evaluations + cost <= self.settings.budget

    def room(self, wanted: int) -> int:
        """How many of `wanted` beests the budget leaves room to score."""
        if self.settings.budget is None:
            return wanted
        return min(wanted, self.settings.budget - self.evaluations)

    def kept_outside_mask(self, genes: list[float]) -> list[float]:
        return [b if fixed else x for x, b, fixed in zip(genes, self.base, self.fixed)]

    def first(self, wanted: int) -> list[Plan]:
        """The first generation: the starting leg itself, when the start has one, then newcomers."""
        own = self.settings.start in LEG_STARTS and wanted > 0
        plans = [(list(self.base), Layout())] if own else []
        return plans + [self.newcomer() for _ in range(wanted - len(plans))]

    def newcomer(self) -> Plan:
        """A new beest on the standard layout, made the way the run starts (RunSettings.start).

        Raises StartError when START_TRIES random beests in a row jam under the "turning" start.
        """
        s = self.settings
        if s.start in LEG_STARTS:
            return self.kept_outside_mask(mutate(list(self.base), s.rate, s.size)), Layout()
        for _ in range(START_TRIES):
            genes = self.kept_outside_mask(random_genes())
            if s.start == "random":
                return genes, Layout()
            key = (tuple(genes), Layout())
            beest = _Beest(key[0], key[1], leg_from(genes, key[1], s.tol, margin=s.margin))
            if not beest.leg.jams:
                self.checked[key] = beest
                return genes, key[1]
        raise StartError(f"No random beest that turns fully came up in {START_TRIES} tries. Let "
                         f"more lengths change, or make the jam margin smaller.")

    def mutant(self, genes: list[float], layout: Layout, parent: tuple[float, ...]) -> Plan:
        """New `genes` put through mutate, with the masked lengths taken back from `parent`."""
        changed = _checked_genes(self.mutate_fn(genes, self.settings.rate), self.mutate_fn)
        genes = [p if fixed else x for x, p, fixed in zip(changed, parent, self.fixed)]
        if self.settings.layout_mutates:
            layout = mutate_layout(layout, self.settings.rate)
        return genes, layout

    def build(self, plans: list[Plan]) -> list[_Beest]:
        built = {}
        for genes, layout in plans:
            key = (tuple(genes), layout)
            if key not in built:
                beest = self.built.get(key) or self.checked.get(key)
                if beest is None:
                    leg = leg_from(genes, layout, self.settings.tol, margin=self.settings.margin)
                    beest = _Beest(key[0], layout, leg)
                built[key] = beest
        self.built = built
        self.checked = {}
        return [built[tuple(genes), layout] for genes, layout in plans]

    def score(self, beests: list[_Beest]) -> list[float]:
        """Normalise the beests together, then score each one; each score is an evaluation."""
        legs = [beest.leg for beest in beests]
        normalise(legs, self.settings.fitness, self.jansen)
        scores = []
        for leg in legs:
            # Legs are reused between generations, so fitness gets its own genes and normalised.
            own = replace(leg, genes=list(leg.genes), normalised=dict(leg.normalised))
            scores.append(_checked_score(self.fitness_fn(own), self.fitness_fn))
        self.evaluations += len(legs)
        return scores

    def keep_run_best(self, beest: _Beest, score: float) -> tuple[_Beest, float, int]:
        """The run's best once this generation's best, scoring `score`, is counted."""
        held = self.run_best
        if held is None or self.together or score >= held[1]:
            same = held is not None and (held[0].genes, held[0].layout) == (beest.genes,
                                                                            beest.layout)
            self.run_best = beest, score, held[2] if same else self.generation
        return self.run_best

    def report(self, beest: _Beest, score: float, tried: list[tuple[_Beest, float]]) -> Report:
        """The generation's report: `beest` is the one the search keeps and `tried` the beests
        this generation tried, with their scores."""
        top, top_score, found = self.keep_run_best(beest, score)
        population = [Member(list(b.genes), b.layout, s, b.leg.jams) for b, s in tried]
        report = Report(generation=self.generation, evaluations=self.evaluations, best_score=score,
                        mean_score=sum(m.score for m in population) / len(population),
                        best_genes=list(beest.genes),
                        best_layout=beest.layout, best_values=ingredient_values(beest.leg),
                        best_jams=beest.leg.jams, best_fits=beest.leg.fits,
                        run_best_generation=found, run_best_score=top_score,
                        run_best_genes=list(top.genes), run_best_layout=top.layout,
                        run_best_values=ingredient_values(top.leg), run_best_jams=top.leg.jams,
                        run_best_fits=top.leg.fits, population=population)
        self.generation += 1
        return report

    def ga(self) -> Iterator[Report]:
        population = self.build(self.first(self.room(self.settings.pop)))
        while True:
            scores = self.score(population)
            leader, top = best(population, scores)
            yield self.report(leader, top, list(zip(population, scores)))
            if not self.more():
                return
            population = self.build(self.next_generation(population, scores))

    def next_generation(self, population: list[_Beest], scores: list[float]) -> list[Plan]:
        """The elites unchanged, then children of tournament winners, up to the room left."""
        s = self.settings
        size = self.room(s.pop)
        ranked = sorted(range(len(population)), key=lambda k: scores[k], reverse=True)
        plans = [(list(population[k].genes), population[k].layout)
                 for k in ranked[:min(s.elite, size)]]
        while len(plans) < size:
            mum, dad = select(population, scores), select(population, scores)
            genes = crossover(mum.genes, dad.genes, s.crossover)
            layout = mum.layout
            if s.layout_mutates and s.crossover != "none":
                layout = random.choice((mum.layout, dad.layout))
            plans.append(self.mutant(genes, layout, mum.genes))
        return plans

    def hill(self) -> Iterator[Report]:
        [parent] = self.build(self.first(1))
        [parent_score] = self.score([parent])
        yield self.report(parent, parent_score, [(parent, parent_score)])
        while self.more(2 if self.together else 1):
            [child] = self.build([self.mutant(list(parent.genes), parent.layout, parent.genes)])
            if self.together:
                parent_score, child_score = self.score([parent, child])
            else:
                [child_score] = self.score([child])
            compared = [(parent, parent_score), (child, child_score)]
            # Ties must go to the child, or a climber that starts jammed never moves.
            if child_score >= parent_score:
                parent, parent_score = child, child_score
            yield self.report(parent, parent_score, compared)

    def random_search(self) -> Iterator[Report]:
        champion, record = None, -math.inf
        while True:
            kept = [champion] if self.together and champion is not None else []
            wanted = self.room(self.settings.pop + len(kept)) - len(kept)
            newcomers = (self.first(wanted) if self.generation == 0
                         else [self.newcomer() for _ in range(wanted)])
            entrants = kept + self.build(newcomers)
            scores = self.score(entrants)
            if kept:
                record = scores[0]
            leader, top = best(entrants, scores)
            if top > record:
                champion, record = leader, top
            yield self.report(champion, record,
                              list(zip(entrants[len(kept):], scores[len(kept):])))
            if not self.more(2 if self.together else 1):
                return


def run(settings: RunSettings, fitness_fn: Callable[[Leg], object] | None = None,
        mutate_fn: Callable[[list[float], float], object] | None = None,
        on_generation: Callable[[Report], object] | None = None) -> Report:
    """Run one search and return the last generation's report.

    Without `fitness_fn` the settings route's fitness scores the beests; without `mutate_fn`,
    `mutate` at the settings' rate and size. Every generation is normalised together before it
    is scored. `on_generation` sees each report, and returning False stops the run.
    The module's `random` is seeded with `settings.seed`, so student code using it repeats too.
    """
    random.seed(settings.seed)
    if fitness_fn is None:
        fitness_fn = settings_fitness(settings.fitness)
    if mutate_fn is None:
        mutate_fn = functools.partial(mutate, size=settings.size)
    search = _Search(settings, fitness_fn, mutate_fn)
    steps = {"ga": search.ga, "hill": search.hill, "random": search.random_search}[settings.preset]
    for report in steps():
        if on_generation is not None and on_generation(report) is False:
            break
    return report
