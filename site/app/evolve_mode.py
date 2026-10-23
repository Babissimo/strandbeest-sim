"""Evolve mode: the settings panel, runs in a worker, the progress graph and the best beests.

The GA runs in a PyScript worker (app/ga_worker.py), so the page stays responsive. The worker
starts the first time the mode is on screen. Stop terminates it and starts a fresh one, which
also ends code that never returns; so does a run of the editor's code, or a worker that fails.
Two beests are shown side by side, the best of the latest generation and the best of the whole
run so far, with every beest of a recent generation below them, all turned by one crank; the
template and the arena take the run's best.
The root element mirrors the mode's state in `data-*` attributes: status (starting, ready,
running or error), generation and evaluations (of the latest report in the run), best-score,
winner-turns and winner-fits (the latest generation's best), run-best-score,
run-best-generation, run-winner-turns and run-winner-fits (the run's best), same-best (whether
they are one beest), population and population-generation (the beests in the grid and their
generation), the crank's playing, angle and drawn-to, series (runs on the graph), points
(in the latest run), graph-view, axis (the score axis's title), route (settings or code),
design-jams (while the start is the Leg tab's design) and, when a run fails, error and, for an
error in the editor's code with a line, error-line.
"""
from __future__ import annotations

import asyncio
import html
import json
import math
import time
import traceback
from collections.abc import Callable

from pyodide.ffi import create_proxy
from pyscript import PyWorker, document, window

from app import draw, job
from app.beest_picture import BeestPicture
from app.controls import Animator, listen
from app.editor import CodePanel
from app.graph import MAX_SERIES, Graph, label, reading, short, title
from app.leg_mode import TOLERANCE_BOUNDS
from app.population import PopulationGrid
from app.printing import TemplateButtons
from app.storage import keep, recall
from beest import ga
from beest.fitness import INGREDIENTS, NORMALISATIONS, fixed_limits
from beest.geometry import ANGLES, DRAW_ANGLES, JAM_MARGIN_MM, LENGTH_NAMES, trace_leg
from beest.leg import DOWN_TOLERANCE_MM, LENGTH_BOUNDS, RANDOM_SPREAD, STICKS, Layout
from beest.template import leg_template_svg

WORKER = "./app/ga_worker.py"
WORKER_CONFIG = "./worker.toml"
PYODIDE = "./vendor/pyodide/pyodide.mjs"
# A worker not ready after this long counts as failed.
WORKER_START_S = 90
# During a run the best beests are drawn again at most this often.
BEST_EVERY_MS = 250
# During a run the grid takes a new generation at most this often, in s; tracing one takes a good
# part of the spare time in that many frames. A run's last generation is always shown.
POPULATION_EVERY_S = 1.0
# The crank angles every beest picture shares: one turn, round and round.
CRANK_TURN = [2 * math.pi * k / DRAW_ANGLES for k in range(DRAW_ANGLES)]
# The two best beests on show, by the start of their fields' names in a report.
BESTS = {"latest": "best_", "run": "run_best_"}
BEST_FIELDS = ("score", "genes", "layout", "values", "jams", "fits")

# The legend's name for each preset.
PRESET_NAMES = {"ga": "GA", "hill": "Hill climbing", "random": "Random search"}
# The settings each preset ignores; their boxes are greyed out.
UNUSED = {"ga": set(), "hill": {"pop", "elite", "crossover"},
          "random": {"elite", "rate", "size", "crossover", "layout"}}
# The settings the editor's fitness and mutate take over from on the code route; normalisation
# still fills in leg.normalised.
CODE_UNUSED = {"size", "weights"}
# Hill climbing breeds one beest at a time by mutation only, and the panel shows that.
HILL_SETTINGS = {"pop": 1, "elite": 0, "crossover": "none"}
# Hill climbing starts from a beest that turns fully, though the student may change that.
HILL_START = "turning"
# Where the browser keeps the chosen route.
ROUTE_KEY = "strandbeest-sim.route"
# Choosing these presets sets "Stop after" to a number of evaluations.
COMPARED_BY_BUDGET = {"hill", "random"}
# Each choice in a drop-down: its words, and a line saying what it does. A choice missing here
# shows under the engine's own name.
DESCRIBED: dict[str, dict[str, tuple[str, str]]] = {
    "start": {
        "random": ("Random beests",
                   f"Every length is drawn at random, within {RANDOM_SPREAD:.0%} of Jansen's."),
        "turning": ("Random, turning fully",
                    "Random beests, each drawn again until it turns all the way round. Checking "
                    "this costs no evaluations."),
        "jansen": ("Jansen and mutants",
                   "Jansen's own leg, and copies of it changed by mutation."),
        "design": ("Leg tab design",
                   "The leg you set up in the Leg tab, and copies of it changed by mutation."),
    },
    "preset": {
        "ga": ("Genetic algorithm (GA)",
               "The beests that score best are the most likely to become parents."),
        "hill": ("Hill climbing",
                 "One beest at a time: its mutated child takes over if it scores as well or "
                 "better."),
        "random": ("Random search",
                   "Fresh random beests every generation, keeping the best so far."),
    },
    "normalisation": {
        "jansen": ("Divide by Jansen's value", "Jansen's own leg scores 1 on every ingredient."),
        "limits": ("Fixed limits",
                   "The lowest limit counts 0 and the highest 1; values beyond them are cut off."),
        "generation": ("This generation's lowest and highest",
                       "The worst beest in each generation counts 0 and the best 1, so a score "
                       "only compares beests in the same generation."),
    },
    "crossover": {
        "uniform": ("Uniform", "Each length comes from one parent or the other."),
        "blend": ("Blend", "Each length is a random point between the parents' lengths."),
        "triangles": ("Triangles",
                      "As uniform, but b, d and e come from the same parent, and so do g, h and "
                      "i."),
        "none": ("None", "The child is a copy of one parent before it mutates."),
    },
}
CHOICES = {"preset": ga.PRESETS, "start": ga.STARTS, "normalisation": NORMALISATIONS,
           "crossover": ga.CROSSOVERS}
TICK, CROSS = "✓", "✗"


def described(key: str, value: str) -> tuple[str, str]:
    return DESCRIBED[key].get(value, (value, ""))


def _field(key: str, text: str, control: str, hint: str = "") -> str:
    return (f'<div class="field" data-setting="{key}"><label for="ev-{key}">{text}</label>'
            f'{control}<small class="hint" id="ev-{key}-hint">{hint}</small></div>')


def _number(key: str, value: float, step: float | str, low: float | None = None,
            high: float | None = None, aria: str | None = None) -> str:
    extra = "" if low is None else f' min="{low}"'
    extra += "" if high is None else f' max="{high}"'
    extra += "" if aria is None else f' aria-label="{aria}"'
    return (f'<input id="ev-{key}" type="number" inputmode="decimal" step="{step}"{extra} '
            f'value="{value:g}">')


def _select(key: str, text: str, chosen: str) -> str:
    """A drop-down of CHOICES[key], with a line under it saying what the chosen one does."""
    options = "".join(f'<option value="{value}"{" selected" if value == chosen else ""}>'
                      f'{html.escape(described(key, value)[0])}</option>'
                      for value in CHOICES[key])
    return _field(key, text, f'<select id="ev-{key}">{options}</select>',
                  html.escape(described(key, chosen)[1]))


def limit_text(value: float) -> str:
    """A surveyed limit as its box shows it."""
    return f"{value:.4g}"


def panel_html() -> str:
    """The settings panel, its defaults taken from the engine's constants."""
    default = ga.RunSettings()
    fitness = default.fitness
    limits = fixed_limits()
    rows, limit_rows = [], []
    for name in INGREDIENTS:
        named = html.escape(label(name))
        flipped = " checked" if fitness.flipped(name) else ""
        rows.append(
            f'<tr><th scope="row"><label for="ev-w-{name}">{named}</label></th>'
            f'<td>{_number(f"w-{name}", fitness.weight(name), 0.1, 0)}</td>'
            f'<td><input id="ev-flip-{name}" type="checkbox"{flipped} '
            f'aria-label="Flip {named}"></td></tr>')
        low, high = limits.get(name, (0.0, 1.0))
        limit_rows.append(
            f'<tr><th scope="row">{named}</th>'
            f'<td>{_number(f"lo-{name}", float(limit_text(low)), "any", aria=f"Lowest {named}")}'
            f'</td><td>'
            f'{_number(f"hi-{name}", float(limit_text(high)), "any", aria=f"Highest {named}")}'
            f'</td></tr>')
    mask = "".join(f'<label class="gene"><input type="checkbox" id="ev-mask-{name}" checked>'
                   f'{name}</label>' for name in LENGTH_NAMES)
    generations = _number("generations", default.generations, 1, 1, aria="Generations")
    budget = _number("budget", ga.BUDGET, 10, 1, aria="Evaluations")
    return f"""
<div class="buttons">
  <button type="button" class="ev-run primary" disabled>Run</button>
  <button type="button" class="ev-stop" disabled>Stop</button>
</div>
<p class="warning ev-error" role="alert" hidden></p>
<p class="ev-progress" role="status">Starting the evolution engine…</p>
<fieldset class="field" data-setting="route">
  <legend>Score and mutate with</legend>
  <label class="choice"><input type="radio" name="ev-route" value="settings" checked>
    the settings</label>
  <label class="choice"><input type="radio" name="ev-route" value="code"> my code</label>
  <small class="hint">With my code, the fitness and mutate you write in the editor take over from
    the fitness weights and the mutation size.</small>
</fieldset>
{_select("preset", "Search", default.preset)}
{_select("start", "Start from", default.start)}
<p class="warning ev-design-jams" role="status" hidden></p>
<fieldset class="field" data-setting="limit">
  <legend>Stop after</legend>
  <label class="choice"><input type="radio" name="ev-limit" value="generations" checked>
    {generations} generations</label>
  <label class="choice"><input type="radio" name="ev-limit" value="budget">
    {budget} evaluations</label>
  <small class="hint">An evaluation is one beest scored.</small>
</fieldset>
{_field("pop", "Population", _number("pop", default.pop, 1, 1), "beests in each generation")}
{_field("rate", "Mutation rate", _number("rate", default.rate, 0.05, 0, 1),
        "the chance that each length changes")}
{_field("size", "Mutation size (mm)", _number("size", default.size, 0.5, 0),
        "how far a length typically moves when it changes")}
{_field("seed", "Seed", _number("seed", default.seed, 1),
        "the same seed and settings give the same run again")}
<details class="group">
  <summary>Fitness: what makes a good beest</summary>
  <p class="hint ev-code-note" hidden>Your fitness gives the score, so the weights and flips are
    not used. Normalisation still fills in <code>leg.normalised</code>.</p>
  {_select("normalisation", "Normalisation (scaling)", fitness.normalisation)}
  <div class="field" data-setting="weights">
    <table class="ingredients">
      <thead><tr><th>Ingredient</th><th>Weight</th><th>Flip</th></tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
    <p class="hint">A beest that jams scores 0. Flip an ingredient when lower is better: it then
      counts 1 − its normalised value.</p>
  </div>
  <div class="limits" hidden>
    <table class="ingredients">
      <thead><tr><th>Fixed limits</th><th>Lowest</th><th>Highest</th></tr></thead>
      <tbody>{"".join(limit_rows)}</tbody>
    </table>
  </div>
</details>
<details class="group">
  <summary>More settings</summary>
  {_field("elite", "Elite", _number("elite", default.elite, 1, 0),
          "the best beests copied unchanged into the next generation")}
  {_select("crossover", "Crossover", default.crossover)}
  <fieldset class="field" data-setting="mask">
    <legend>Lengths that can change</legend>
    <div class="genes">{mask}</div>
    <small class="hint">The others stay at Jansen's length.</small>
  </fieldset>
  <div class="field" data-setting="layout">
    <label class="choice"><input type="checkbox" id="ev-layout">
      Let the number of leg pairs and their crank angles change</label>
  </div>
  {_field("tol", "Down tolerance (mm)", _number("tol", DOWN_TOLERANCE_MM, 0.1, *TOLERANCE_BOUNDS),
          "how close to its lowest point a foot counts as down")}
  {_field("margin", "Jam margin (mm)", _number("margin", JAM_MARGIN_MM, 0.1, 0),
          "links closer than this to not meeting count as jammed")}
</details>
"""


class SettingsForm:
    """The settings panel, turned into RunSettings on demand.

    `design` gives the Leg tab's 13 lengths, a to m, for the "design" start; without it that
    start cannot be chosen. `on_start` runs when the start, or the jam margin it is checked at,
    changes.
    """

    def __init__(self, panel, design: Callable[[], list[float]] | None = None,
                 on_start: Callable[[], None] | None = None):
        self.panel = panel
        self.design = design
        self.on_start = on_start
        panel.innerHTML = panel_html()
        if design is None:
            self._get("start").querySelector('option[value="design"]').disabled = True
        self.preset = self._get("preset").value
        # "settings" or "code": what scores and mutates the beests.
        self.route = "settings"
        # The boxes hill climbing fills in, as they were before it did.
        self._saved: dict[str, str] = {}
        # The surveyed limits as their boxes first showed them.
        self._limits_shown = {key: self._get(key).value for name in INGREDIENTS
                              for key in (f"lo-{name}", f"hi-{name}")}
        self._proxies = [listen(self._get("preset"), "change", self._preset_changed),
                         listen(self._get("start"), "change", self._start_changed),
                         listen(self._get("margin"), "input", self._margin_changed),
                         listen(self._get("normalisation"), "change", self._normalisation_changed)]
        for key in CHOICES:
            self._proxies.append(listen(self._get(key), "change",
                                        lambda event, key=key: self._describe(key)))
        for key in ("generations", "budget"):
            self._proxies.append(listen(self._get(key), "input",
                                        lambda event, key=key: self._choose_limit(key)))

    def _get(self, key: str):
        return document.getElementById(f"ev-{key}")

    def _describe(self, key: str) -> None:
        self._get(f"{key}-hint").textContent = described(key, self._get(key).value)[1]

    def _preset_changed(self, event=None) -> None:
        """Grey out what the chosen preset ignores; hill climbing shows its own values."""
        chosen = self._get("preset").value
        if chosen == "hill" and self.preset != "hill":
            self._saved = {key: self._get(key).value for key in (*HILL_SETTINGS, "start")}
            for key, value in (HILL_SETTINGS | {"start": HILL_START}).items():
                self._get(key).value = str(value)
            self._described_again()
        elif chosen != "hill" and self.preset == "hill":
            for key, value in self._saved.items():
                # A start chosen while on hill climbing stays.
                if key != "start" or self.start == HILL_START:
                    self._get(key).value = value
            self._described_again()
        if chosen in COMPARED_BY_BUDGET:
            # Searches are compared on the same number of evaluations (decisions Q17), and
            # hill climbing's 40 generations would be only 40 beests.
            self._choose_limit("budget")
        self.preset = chosen
        self._grey_out()

    def _described_again(self) -> None:
        """After hill climbing filled in or gave back its settings."""
        self._describe("crossover")
        self._describe("start")
        if self.on_start is not None:
            self.on_start()

    @property
    def start(self) -> str:
        return self._get("start").value

    def _start_changed(self, event=None) -> None:
        self._grey_out()
        if self.on_start is not None:
            self.on_start()

    def _margin_changed(self, event=None) -> None:
        if self.on_start is not None:
            self.on_start()

    def design_genes(self) -> list[float]:
        return [float(x) for x in self.design()]

    def margin(self) -> float:
        """The jam margin in its box, or the engine's when the box holds no usable number."""
        try:
            return self._read("margin", "Jam margin", low=0)
        except ValueError:
            return JAM_MARGIN_MM

    def set_route(self, route: str) -> None:
        """Choose what scores and mutates the beests, "settings" or "code"."""
        self.route = route
        for radio in self.panel.querySelectorAll('input[name="ev-route"]'):
            radio.checked = radio.value == route
        self.panel.querySelector(".ev-code-note").hidden = route != "code"
        self._grey_out()

    def unused(self) -> set[str]:
        """The settings the chosen preset, on the chosen route, does not use."""
        preset = self._get("preset").value
        unused = UNUSED.get(preset, set()) | (CODE_UNUSED if self.route == "code" else set())
        # The copies of Jansen's leg or the design are made with the engine's mutate; hill
        # climbing starts from the leg itself and makes none.
        copies = self.start in ga.LEG_STARTS and preset != "hill"
        return unused - {"rate", "size"} if copies else unused

    def _grey_out(self) -> None:
        unused = self.unused()
        for row in self.panel.querySelectorAll("[data-setting]"):
            greyed = row.dataset.setting in unused
            row.classList.toggle("unused", greyed)
            for control in row.querySelectorAll("input, select"):
                control.disabled = greyed

    def _limit(self) -> str:
        """Which "Stop after" is chosen: "generations" or "budget"."""
        return self.panel.querySelector('input[name="ev-limit"]:checked').value

    def _choose_limit(self, key: str) -> None:
        for radio in self.panel.querySelectorAll('input[name="ev-limit"]'):
            radio.checked = radio.value == key

    def _normalisation_changed(self, event=None) -> None:
        self.panel.querySelector(".limits").hidden = self._get("normalisation").value != "limits"

    def _read(self, key: str, what: str, whole: bool = False, low: float | None = None,
              high: float | None = None) -> float:
        text = self._get(key).value.strip()
        try:
            value = float(text)
        except ValueError:
            raise ValueError(f"{what} needs a number.") from None
        if not math.isfinite(value):
            raise ValueError(f"{what} needs an ordinary number.")
        if whole:
            if value != int(value):
                raise ValueError(f"{what} must be a whole number, not {text}.")
            value = int(value)
        if low is not None and value < low or high is not None and value > high:
            between = f"at least {low:g}" if high is None else f"from {low:g} to {high:g}"
            raise ValueError(f"{what} must be {between}, not {text}.")
        return value

    def to_dict(self) -> dict:
        """The panel's settings as job.settings_from_dict reads them.

        Raises ValueError naming the box to fix when one does not hold a usable number.
        """
        preset = self._get("preset").value
        unused = self.unused()
        budget = self._limit() == "budget"
        settings = {
            "preset": preset,
            "seed": self._read("seed", "Seed", True),
            "mask": [name for name in LENGTH_NAMES if self._get(f"mask-{name}").checked],
            "tol": self._read("tol", "Down tolerance", False, *TOLERANCE_BOUNDS),
            "margin": self._read("margin", "Jam margin", low=0),
            "layout_mutates": "layout" not in unused and bool(self._get("layout").checked),
            "start": self.start,
        }
        if self.start == "design":
            settings["start_genes"] = self.design_genes()
        if budget:
            settings["budget"] = self._read("budget", "Evaluations", True, 1)
        else:
            settings["generations"] = self._read("generations", "Generations", True, 1)
        if preset == "hill":
            settings |= HILL_SETTINGS
        for key, what, whole, low, high in (("pop", "Population", True, 1, None),
                                            ("elite", "Elite", True, 0, None),
                                            ("rate", "Mutation rate", False, 0, 1),
                                            ("size", "Mutation size", False, 0, None)):
            if key not in unused:
                settings[key] = self._read(key, what, whole, low, high)
        if "crossover" not in unused:
            settings["crossover"] = self._get("crossover").value
        settings["fitness"] = self._fitness("weights" not in unused)
        return settings

    def _fitness(self, weighted: bool) -> dict:
        """The Fitness settings; without the weights and flips unless `weighted`."""
        normalisation = self._get("normalisation").value
        fitness: dict = {"normalisation": normalisation}
        if weighted:
            fitness["weights"] = {
                name: self._read(f"w-{name}", f"The weight of {title(name).lower()}", low=0)
                for name in INGREDIENTS}
            fitness["flip"] = {name: bool(self._get(f"flip-{name}").checked)
                               for name in INGREDIENTS}
        if normalisation == "limits":
            fitness["limits"] = {}
            surveyed = fixed_limits()
            for name in INGREDIENTS:
                pair = []
                for k, (key, what) in enumerate(((f"lo-{name}", "lowest"),
                                                 (f"hi-{name}", "highest"))):
                    if self._get(key).value == self._limits_shown[key] and name in surveyed:
                        # A box left as shown keeps the surveyed value, which it shows rounded.
                        pair.append(surveyed[name][k])
                    else:
                        pair.append(self._read(key, f"The {what} {title(name).lower()}"))
                if name not in surveyed or pair != list(surveyed[name]):
                    fitness["limits"][name] = pair
        return fitness

    def settings(self) -> tuple[ga.RunSettings, dict]:
        """The settings, checked by the engine, and their plain form for the worker."""
        plain = self.to_dict()
        return job.settings_from_dict(plain), plain


def misfits(genes: list[float]) -> str:
    """In words, which sticks of a beest do not fit on a lolly stick."""
    lengths = dict(zip(LENGTH_NAMES, genes))
    wrong = [f"{name} is {lengths[name]:.1f} mm, outside {low:g} to {high:g} mm"
             for name in STICKS for low, high in [LENGTH_BOUNDS[name]]
             if not low <= lengths[name] <= high]
    return "Does not fit on lolly sticks" + (f": {'; '.join(wrong)}" if wrong else "")


def best_of(report: dict, kind: str) -> dict:
    """One of a report's best beests ("latest" or "run"): its score, genes, layout, values,
    jams and fits."""
    return {name: report[BESTS[kind] + name] for name in BEST_FIELDS}


def layout_of(beest: dict) -> Layout:
    layout = beest["layout"]
    return Layout(layout["pairs"], tuple(layout["phases"]))


def facts_html(beest: dict, which: str) -> str:
    """A best beest's winner checks, ingredients, lengths and layout, under `which` (HTML)."""
    turns, fits = not beest["jams"], beest["fits"]
    turns_text = f"{TICK} Turns fully" if turns else f"{CROSS} Jams: it cannot turn fully"
    fits_text = f"{TICK} Fits on lolly sticks" if fits else f"{CROSS} {misfits(beest['genes'])}"
    numbers = "".join(f"<dt>{html.escape(label(name))}</dt><dd>{reading(name, value)}</dd>"
                      for name, value in beest["values"].items())
    lengths = " ".join(f"<span><b>{name}</b> {length:.1f}</span>"
                       for name, length in zip(LENGTH_NAMES, beest["genes"]))
    layout = beest["layout"]
    phases = ", ".join(f"{p:.0f}°" for p in layout["phases"])
    return f"""
<p class="which">{which}: score <b>{short(beest["score"])}</b></p>
<ul class="checks">
  <li class="{'ok' if turns else 'bad'}" data-check="turns">{turns_text}</li>
  <li class="{'ok' if fits else 'bad'}" data-check="fits">{fits_text}</li>
</ul>
<dl class="numbers">{numbers}</dl>
<p class="lengths">Lengths in mm: {lengths}</p>
<p class="layout">{layout["pairs"]} pair{'' if layout["pairs"] == 1 else 's'} of legs, cranks at
  {phases}</p>
"""


def same_note(relative: bool, since: int) -> str:
    """What the run's column says when its best is the latest generation's best."""
    if relative:
        return ("The same beest as the best of the latest generation. Scores relative to each "
                "generation cannot be compared between generations, so the latest best counts as "
                "the best of the run.")
    return (f"The same beest as the best of the latest generation. It has been the best of the "
            f"run since generation {since}.")


class Run:
    """One run on its way: its settings, the editor's source if it uses it, its series on the
    graph and when it started."""

    def __init__(self, settings: ga.RunSettings, source: str | None, series):
        self.settings = settings
        self.source = source
        self.series = series
        self.started = time.monotonic()
        self.last: dict | None = None
        # The task waiting for the worker's answer.
        self.task: asyncio.Future | None = None


class EvolveMode:
    """`on_best` is given the run's best beest each time the panel shows the bests: its 13
    lengths and its layout. `design` gives the Leg tab's lengths by name, for the "design" start.
    """

    def __init__(self, root, on_best: Callable[[list[float], Layout], None] | None = None,
                 design: Callable[[], dict[str, float]] | None = None):
        self.root = root
        self.on_best = on_best
        self.status = ""
        self.worker = None
        self.current: Run | None = None
        self.runs = 0
        self.best: dict | None = None
        self.best_run: Run | None = None
        # The report whose best beests are on show; the template prints the run's best.
        self.shown_best: dict | None = None
        self._shown: dict[str, str] = {}
        self._scheduled = False
        self._best_shown = False
        # When the best beests were last drawn, in ms on the animation clock.
        self._best_drawn = -math.inf
        # When the grid was last offered a generation, in s.
        self._population_offered = -math.inf
        # What the status line last said about a run.
        self._said = ""
        # The error on show, and whether it is in the editor's code.
        self._error: str | None = None
        self._error_in_code = False
        # Tasks still running; asyncio itself keeps only weak references to them.
        self._tasks: set[asyncio.Future] = set()
        self._pyodide = window.URL.new(PYODIDE, document.baseURI).href
        design_genes = None if design is None else (
            lambda: [design()[name] for name in LENGTH_NAMES])
        self.form = SettingsForm(root.querySelector(".controls"), design_genes,
                                 self._check_design)
        self.design_warning = root.querySelector(".ev-design-jams")
        stage = root.querySelector(".stage")
        stage.innerHTML = STAGE_HTML
        self.code = CodePanel(stage, on_reset=self._code_reset)
        self.run_button = root.querySelector(".ev-run")
        self.stop_button = root.querySelector(".ev-stop")
        self.error = root.querySelector(".ev-error")
        self.progress = root.querySelector(".ev-progress")
        self.legend = root.querySelector(".ev-legend")
        self.readout = root.querySelector(".ev-readout")
        self.columns = {kind: root.querySelector(f'.best-beest[data-best="{kind}"]')
                        for kind in BESTS}
        canvas = root.querySelector(".ev-graph")
        self.graph = Graph(canvas, window)
        # The view only sizes the graph's canvas, at the screen's pixel density.
        self.graph_canvas = draw.View(canvas, self._graph_resized)
        self.pictures = {kind: BeestPicture(column.querySelector(".ev-beest"),
                                            self._pictures_resized, "The best beest appears here.")
                         for kind, column in self.columns.items()}
        self.population = PopulationGrid(root.querySelector(".ev-population"),
                                         self._pictures_resized)
        self.population_hint = root.querySelector(".ev-population-hint")
        # One crank turns every picture, so they keep in step; it starts once there is a best.
        self.animator = Animator(root, self._draw_beests)
        # Disabled until a run has a best beest to print.
        self.template = TemplateButtons(root, root.querySelector(".ev-template"),
                                        "Print the leg template", "strandbeest-leg-template",
                                        self._leg_template)
        self._proxies = [
            listen(self.run_button, "click", self._run_clicked),
            listen(self.stop_button, "click", self._stop_clicked),
            listen(root.querySelector(".ev-clear"), "click", self._clear_clicked),
            listen(canvas, "pointermove", self._hover),
            listen(canvas, "pointerleave", self._hover),
            # The Leg tab's design may have changed while this mode was hidden.
            listen(window, "hashchange", self._check_design),
        ]
        for radio in root.querySelectorAll('input[name="ev-view"]'):
            self._proxies.append(listen(radio, "change", self._view_changed))
        for radio in root.querySelectorAll('input[name="ev-route"]'):
            self._proxies.append(listen(radio, "change", self._route_changed))
        self._set_route("code" if recall(ROUTE_KEY) == "code" else "settings")
        self._frame_proxy = create_proxy(self._frame)
        self._mirror("graph-view", self.graph.view)
        self._show_runs()
        self._show_best()
        self._graph_resized()

    # The worker

    def _spawn(self, coroutine) -> asyncio.Future:
        task = asyncio.ensure_future(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def _launch_worker(self) -> None:
        self._set_status("starting")
        self._spawn(self._start_worker())

    async def _start_worker(self) -> None:
        worker = None

        async def started() -> None:
            await worker.ready
            await worker.sync.started()

        try:
            worker = PyWorker(WORKER, type="pyodide", config=WORKER_CONFIG, version=self._pyodide)
            worker.sync.report = self._on_report
            self.worker = worker
            await asyncio.wait_for(started(), WORKER_START_S)
        except Exception as exc:
            if worker is self.worker:
                self.worker = None
                if worker is not None:
                    worker.terminate()
                self._set_status("error")
                window.console.error(f"The GA worker did not start: {exc!r}")
            return
        if worker is self.worker:
            self._set_status("ready")

    def _on_report(self, text: str) -> bool:
        """Called by the worker after each generation; returns whether the run goes on."""
        run = self.current
        if run is None:
            return False
        report = json.loads(text)
        run.series.add(report)
        run.last = report
        self.best, self.best_run, self._best_shown = report, run, False
        # The page shows it on the next frame, so the worker waits no longer than this.
        self._schedule()
        return True

    # Run, Stop and Clear graph

    def _run_clicked(self, event=None) -> None:
        self._check_design()
        self.start_run(self.code.text if self.form.route == "code" else None)

    def start_run(self, source: str | None = None) -> bool:
        """Start a run with the panel's settings; with `source`, the editor's fitness and
        mutate in it score and mutate the beests. False when no run could start."""
        if self.status != "ready" or self.current is not None:
            return False
        try:
            settings, plain = self.form.settings()
        except ValueError as exc:
            self._show_error(str(exc))
            return False
        self._show_error(None)
        self.runs += 1
        name = PRESET_NAMES.get(settings.preset, settings.preset)
        coded = "" if source is None else ", your code"
        series = self.graph.add(f"Run {self.runs}: {name}{coded}, seed {settings.seed}",
                                relative=settings.fitness.normalisation == "generation")
        run = Run(settings, source, series)
        self.current = run
        for attribute in ("generation", "evaluations"):
            self._mirror(attribute, "")
        self._set_status("running")
        self._show_runs()
        self._show_progress()
        self._schedule()
        request = json.dumps({"settings": plain, "source": source})
        run.task = self._spawn(self._carry_out(run, self.worker, request))
        return True

    async def _carry_out(self, run: Run, worker, request: str) -> None:
        alive = True
        try:
            answer = json.loads(await worker.sync.run(request))
        except Exception as exc:
            # The worker itself failed, as when its Python runs out of stack.
            alive = False
            answer = {"status": "error",
                      "error": {"kind": "crash", "message": f"The run failed: {exc}",
                                "line": None, "traceback": None}}
        if run is not self.current:
            # Stopped meanwhile; a fresh worker has taken over.
            return
        self.current = None
        ended = answer["status"]
        if ended == "error" and self._failed(run, answer["error"]):
            ended = "code"
        self._show_ended(run, ended)
        if alive and run.source is None:
            self._set_status("ready")
        else:
            # Editor code may have changed the engine's modules, so the next run starts afresh.
            self._replace_worker()

    def _show_ended(self, run: Run, ended: str) -> None:
        """Everything about a run that has ended, shown straight away."""
        self._show_runs()
        self._show_progress(run, ended)
        self._show_best()
        self._offer_population(at_once=True)
        self._schedule()

    def _give_back(self, run: Run, ended: str) -> None:
        """A run that never got going gives back its place on the graph and its number."""
        if len(run.series):
            run.series.ended = ended
        else:
            self.graph.discard(run.series)
            self.runs -= 1

    def _failed(self, run: Run, error: dict) -> bool:
        """Show why the run failed; True when the editor's code was at fault."""
        in_code = error["kind"] == "student"
        self._give_back(run, "ended by an error in your code" if in_code else "ended by an error")
        message = error["message"]
        self._show_error(message, error.get("line"), error.get("traceback"),
                         run.source if in_code else None)
        if error["kind"] == "crash":
            # A crash is a fault in the simulator rather than in the settings or the editor.
            window.console.error(error.get("traceback") or message)
        return in_code

    def _stop_clicked(self, event=None) -> None:
        run = self.current
        if run is None:
            return
        self.current = None
        # The terminated worker never answers, so nothing is left waiting for it.
        run.task.cancel()
        self._give_back(run, "stopped")
        self._show_ended(run, "stopped")
        self._replace_worker()

    def _replace_worker(self) -> None:
        """End the worker, whatever it is doing, and start a fresh one."""
        if self.worker is not None:
            self.worker.terminate()
            self.worker = None
        self._launch_worker()

    def _clear_clicked(self, event=None) -> None:
        self.graph.clear(keep=self.current.series if self.current is not None else None)
        self._show_runs()
        self._schedule()

    # Showing state

    def _set_status(self, status: str) -> None:
        self.status = status
        self._mirror("status", status)
        self.run_button.disabled = status != "ready"
        self.stop_button.disabled = status != "running"
        self._show_status_line()

    def _show_error(self, message: str | None, line: int | None = None,
                    trace: str | None = None, source: str | None = None) -> None:
        """Say why a run could not go on; None clears it.

        An error in the editor's code (`source`, the code that ran) shows beside the editor,
        which marks `line` and offers `trace`. Any other error shows beside Run, as does one in
        the code while the editor is hidden.
        """
        self._error = message
        self._error_in_code = message is not None and source is not None
        if self._error_in_code:
            self.code.show_error(message, line, trace, source)
        else:
            self.code.show_error(None)
        self._place_error()
        if message is None:
            self._forget("error")
        else:
            self._mirror("error", message)
        if self._error_in_code and line is not None:
            self._mirror("error-line", str(line))
        else:
            self._forget("error-line")

    def _place_error(self) -> None:
        """Show the error beside Run, unless the editor on show has it."""
        beside_run = None if self._error_in_code and self.code.shown else self._error
        self.error.hidden = beside_run is None
        self.error.textContent = beside_run or ""

    def _show_progress(self, run: Run | None = None, ended: str | None = None) -> None:
        run = run or self.current
        if run is None:
            return
        report = run.last
        done = report["generation"] + 1 if report else 0
        scored = report["evaluations"] if report else 0
        if report is not None:
            self._mirror("generation", str(report["generation"]))
            self._mirror("evaluations", str(report["evaluations"]))
        counts = f"{done:,} generation{'' if done == 1 else 's'}, {scored:,} beests scored"
        if ended is None:
            self._said = f"Running: {counts}."
        elif ended == "done":
            seconds = time.monotonic() - run.started
            self._said = f"Finished: {counts} in {seconds:.1f} s."
        elif ended == "stopped":
            self._said = f"Stopped after {counts}."
        elif ended == "code":
            self._said = f"Your code stopped the run after {counts}."
        else:
            self._said = f"The run ended early after {counts}."
        self._show_status_line()

    def _show_status_line(self) -> None:
        if self.status == "error":
            text = "The evolution engine could not start. Try reloading the page."
        elif self.status == "starting":
            text = f"{self._said} Starting the evolution engine…".lstrip()
        else:
            text = self._said or "Ready. Choose your settings and press Run."
        self.progress.textContent = text

    def _show_runs(self) -> None:
        series = self.graph.series
        self._mirror("series", str(len(series)))
        self._mirror("points", str(len(series[-1]) if series else 0))
        items = []
        for s in series:
            notes = []
            if s.relative and not self.graph.relative:
                notes.append("relative to each generation")
            if s.ended:
                notes.append(s.ended)
            note = f" ({', '.join(notes)})" if notes else ""
            items.append(f'<li><span class="key" style="background:{s.colour}"></span>'
                         f'{html.escape(s.label)}{note}</li>')
        self.legend.innerHTML = "".join(items)
        self.root.querySelector(".ev-styles").hidden = not series
        dropped = self.root.querySelector(".ev-dropped")
        dropped.hidden = not self.graph.dropped
        dropped.textContent = (f"The graph keeps the last {MAX_SERIES} runs, so the oldest "
                               f"{'has' if self.graph.dropped == 1 else 'have'} gone.")
        self._mirror("axis", self.graph.axis_title)

    def _show_best(self) -> None:
        if self._best_shown:
            return
        self._best_shown = True
        report = self.best
        if report is None:
            for kind, text in (("latest", "Press Run and the best beest of the latest generation "
                                          "appears here."),
                               ("run", "The best beest of the whole run so far appears here.")):
                self.columns[kind].querySelector(".ev-facts").innerHTML = (
                    f'<p class="hint">{text}</p>')
            return
        run = self.best_run
        self.shown_best = report
        self.template.enable()
        latest, top = best_of(report, "latest"), best_of(report, "run")
        since = report["run_best_generation"]
        same = (latest["genes"], latest["layout"]) == (top["genes"], top["layout"])
        for prefix, beest in (("", latest), ("run-", top)):
            self._mirror(f"{prefix}best-score", repr(beest["score"]))
            self._mirror(f"{prefix}winner-turns", str(not beest["jams"]).lower())
            self._mirror(f"{prefix}winner-fits", str(beest["fits"]).lower())
        self._mirror("run-best-generation", str(since))
        self._mirror("same-best", str(same).lower())
        name = html.escape(run.series.label)
        shown = [("latest", latest, f"{name}, generation {report['generation']}")]
        if not same:
            shown.append(("run", top, f"{name}, the best since generation {since}"))
        for kind, beest, which in shown:
            self.pictures[kind].show(beest["genes"], beest["layout"]["phases"],
                                     run.settings.margin, beest["jams"])
            self.columns[kind].querySelector(".ev-facts").innerHTML = facts_html(beest, which)
        column = self.columns["run"]
        column.querySelector(".best-shown").hidden = same
        note = column.querySelector(".ev-same")
        note.hidden = not same
        note.textContent = same_note(run.settings.fitness.normalisation == "generation", since)
        if self.animator.angles:
            self.animator.redraw()
        else:
            self.animator.load(CRANK_TURN, DRAW_ANGLES, loops=True)
        self._offer_population()
        if self.on_best is not None:
            # The panel is already shown; an error in the receiver goes no further than the console.
            try:
                self.on_best(top["genes"], layout_of(top))
            except Exception:
                window.console.error(
                    f"Handing on the best beest failed.\n{traceback.format_exc()}")

    def _leg_template(self) -> list[str]:
        """The template of the run's best beest on show, for its number of leg pairs."""
        top = best_of(self.shown_best, "run")
        return leg_template_svg(top["genes"], layout_of(top))

    def _draw_beests(self, index: int | None) -> bool:
        """Draws both best beests and the generation's grid with the crank at this step of its
        turn."""
        theta = 0.0 if index is None else CRANK_TURN[index]
        drew = [picture.draw(theta) for picture in self.pictures.values()]
        drew.append(self.population.draw(theta))
        return any(drew)

    def _offer_population(self, at_once: bool = False) -> None:
        """Gives the grid the generation whose bests are on show; during a run, only so often."""
        report, run = self.shown_best, self.best_run
        now = time.monotonic()
        if report is None or not at_once and now - self._population_offered < POPULATION_EVERY_S:
            return
        self._population_offered = now
        # The key names the generation and says what the grid's hint needs about its run.
        key = (id(run), report["generation"], run.series.label, run.settings.preset)
        self.population.offer(key, report["population"], run.settings.margin)

    def _show_population(self) -> None:
        """A newly traced generation has gone on show in the grid."""
        grid = self.population
        _, generation, name, preset = grid.key
        self._mirror("population", str(len(grid.shown)))
        self._mirror("population-generation", str(generation))
        tried = "parent and child" if preset == "hill" else "every beest"
        self.population_hint.textContent = (
            f"{name}, generation {generation}: {tried}, best first, with each one's score. A "
            f"grey beest jams, so it stays still. Play turns them with the best beests.")
        self.animator.redraw()

    def _pictures_resized(self) -> None:
        self.animator.draw_now()

    def _mirror(self, name: str, value: str) -> None:
        if self._shown.get(name) != value:
            self._shown[name] = value
            self.root.setAttribute(f"data-{name}", value)

    def _forget(self, name: str) -> None:
        self.root.removeAttribute(f"data-{name}")
        self._shown.pop(name, None)

    # Drawing

    def _schedule(self) -> None:
        if not self._scheduled:
            self._scheduled = True
            window.requestAnimationFrame(self._frame_proxy)

    def _frame(self, now: float) -> None:
        self._scheduled = False
        if self.current is not None:
            self._show_progress()
            self._mirror("points", str(len(self.current.series)))
        self.graph.draw()
        if not self._best_shown:
            # Tracing the beest to draw it takes a while, so a run redraws it only so often.
            if self.current is None or now - self._best_drawn >= BEST_EVERY_MS:
                self._show_best()
                self._best_drawn = now
            else:
                self._schedule()
        if self.population.busy:
            # The grid traces a few beests each frame, so frames stay short.
            if self.population.work():
                self._show_population()
            if self.population.busy:
                self._schedule()
        self.readout.textContent = "\n".join(self.graph.readout())

    def _graph_resized(self) -> None:
        self.graph.width, self.graph.height = self.graph_canvas.width, self.graph_canvas.height
        self.graph.draw()
        if not self.status and self.graph.width:
            # The worker, a second Python, starts the first time this mode is on screen.
            self._launch_worker()

    def _hover(self, event) -> None:
        leaving = event.type == "pointerleave"
        self.graph.hover = None if leaving else (float(event.offsetX), float(event.offsetY))
        self._schedule()

    def _check_design(self, event=None) -> None:
        """Warns, while the run is to start from the Leg tab's design, when that leg jams."""
        if self.root.hidden:
            return
        reason = None
        if self.form.start == "design":
            # As the run starts from it.
            lengths = dict(zip(LENGTH_NAMES, ga.clamp(self.form.design_genes())))
            trace = trace_leg(lengths, ANGLES, self.form.margin())
            reason = trace.jam_reason if trace.jammed else None
            self._mirror("design-jams", str(trace.jammed).lower())
        else:
            self._forget("design-jams")
        self.design_warning.hidden = reason is None
        self.design_warning.textContent = (
            "" if reason is None else f"The leg in the Leg tab jams: {reason}. Its copies may "
                                      f"jam too, and a beest that jams scores 0.")

    def _code_reset(self) -> None:
        # A message about the student's own code goes with it; one about the settings stays.
        if self._error_in_code:
            self._show_error(None)

    def _route_changed(self, event) -> None:
        self._set_route(event.target.value)
        keep(ROUTE_KEY, self.form.route)

    def _set_route(self, route: str) -> None:
        self.form.set_route(route)
        self.code.show(route == "code")
        self._place_error()
        self._mirror("route", route)

    def _view_changed(self, event) -> None:
        self.graph.view = event.target.value
        self._mirror("graph-view", self.graph.view)
        self._schedule()


STAGE_HTML = """
<div class="panel progress-panel">
  <div class="panel-head">
    <h3>Progress</h3>
    <div class="segmented" role="radiogroup" aria-label="Graph shows">
      <label><input type="radio" name="ev-view" value="score" checked>Scores</label>
      <label><input type="radio" name="ev-view" value="ingredients">Ingredients</label>
    </div>
    <button type="button" class="ev-clear">Clear graph</button>
  </div>
  <canvas class="ev-graph" role="img"
    aria-label="Each run's best and average score against the number of beests scored"></canvas>
  <ul class="ev-legend"></ul>
  <p class="ev-styles" hidden><span class="line solid"></span> best beest
    <span class="line dashed"></span> average of the generation</p>
  <p class="hint ev-dropped" hidden></p>
  <p class="ev-readout"></p>
</div>
<div class="panel best-panel">
  <div class="panel-head">
    <h3>Best beests</h3>
    <div class="playback">
      <button type="button" class="play" disabled>Play</button>
      <label class="speed-label">Speed
        <input type="range" class="speed" min="1" max="60" step="1" value="15" disabled>
      </label>
      <output class="speed-shown">15 turns a minute</output>
    </div>
  </div>
  <div class="best-pair">
    <div class="best-beest" data-best="latest">
      <h4>Best of the latest generation</h4>
      <div class="best-shown">
        <canvas class="ev-beest" role="img"
          aria-label="The best beest of the latest generation, walking left"></canvas>
        <div class="ev-facts"></div>
      </div>
    </div>
    <div class="best-beest" data-best="run">
      <h4>Best of the whole run so far</h4>
      <p class="hint ev-same" hidden></p>
      <div class="best-shown">
        <canvas class="ev-beest" role="img"
          aria-label="The best beest of the whole run so far, walking left"></canvas>
        <div class="ev-facts"></div>
      </div>
    </div>
  </div>
  <p class="hint">The leg template is for the best beest of the whole run so far, and so is
    "The best from Evolve" in the Arena tab.</p>
  <div class="template ev-template"></div>
</div>
<div class="panel population-panel">
  <h3>The whole generation</h3>
  <p class="hint ev-population-hint">Press Run and every beest of each generation appears here,
    best first.</p>
  <canvas class="ev-population" role="img" hidden
    aria-label="Every beest of the generation, best first, each with its score"></canvas>
</div>
"""
