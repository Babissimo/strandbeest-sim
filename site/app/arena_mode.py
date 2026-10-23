"""Arena: a whole beest walking on the ground in 2D physics (decisions Q2).

The physics engine (pymunk, on Pyodide's own cffi, app/physics.py) loads the first time the tab
is opened, unless Evolve has loaded it already, and the other tabs work even if it cannot load.
The beest stands still until Start. The root element shows `data-status` (loading, ready,
running or error), `data-playing` (true while it walks), `data-beest`, `data-pairs`,
`data-jammed` (a beest that cannot be built leaves the status ready, with nothing to start),
`data-turns`, `data-travel` (mm walked left), `data-distance-per-turn` (empty until a whole turn
is done) and `data-tipped`. In a race it also shows `data-race`, and once the race is decided,
`data-outcome` (finished, fell or gave-up) and `data-race-turns`.
"""
from __future__ import annotations

import asyncio
import math
import traceback
from collections.abc import Callable

from pyodide.ffi import create_proxy
from pyscript import window

from app import draw
from app.controls import MAX_FRAME_S, announce, listen
from app.leg_mode import COLOURS, STICKS, TRIANGLES
from app.physics import engine
from beest.geometry import LENGTH_NAMES, Point
from beest.leg import Layout, jansen_lengths

# The choices in #arena-beest.
JANSEN, PLAYGROUND, EVOLVED = "jansen", "leg", "evolved"
# The choice in #arena-race that is no race; the others are beest.arena's RACES.
WALK = "walk"
PENCIL = "#e8b10a"
TOWEL = "#0c8599"
# Distance per turn is shown once this many turns are done; before then the start-up dominates it.
SETTLED_TURNS = 1
# The view follows the axle and shows this many times the beest's reach either side of it.
VIEW_REACH = 1.6
# Ground shown below the surface, in mm, and room above the beest for the arrow, in px.
BELOW_MM = 12.0
ARROW_ROOM_PX = 48
# Distance markers along the ground, in mm from where the beest started.
MARK_MM = 100
# The pairs on the other throws are drawn thinner and faint, behind the phase-0 pair.
FAINT = {name: draw.translucent(colour, 0.35) for name, colour in COLOURS.items()}
FAINT_STICK_PX = 6
LOADING = "Loading the physics engine…"
LOAD_FAILED = ("The physics engine could not load, so the arena cannot run. Try reloading the "
               "page; the other tabs still work.")
# What the arena says when the chosen beest has changed since this one was stood up.
STALE = {PLAYGROUND: "The leg in the Leg tab has changed since this one started. Press Reset to "
                     "walk it.",
         EVOLVED: "Evolve has found a new best beest. Press Reset to walk it."}
FAULT = ("Something went wrong in the arena, so this beest cannot walk. Try Reset or another "
         "beest; the other tabs still work.")


def minus(text: str) -> str:
    """A number as text with a true minus sign."""
    return text.replace("-", "\u2212")


def sentence(error: Exception) -> str:
    """An error's message as a sentence."""
    text = str(error)
    return f"{text[:1].upper()}{text[1:]}."


class ArenaMode:
    """The arena section of the page: the choice of beest, the controls and the live drawing.

    `playground` gives the Leg tab's current lengths by name. Evolve mode hands over its winner
    with `offer_evolved`, which makes "The best from Evolve" a choice.
    """

    def __init__(self, root, playground: Callable[[], dict[str, float]]):
        self.root = root
        self.playground = playground
        self.message = root.querySelector("#arena-message")
        self.choice = root.querySelector("#arena-beest")
        self.pairs = root.querySelector("#arena-pairs")
        self.start = root.querySelector("#arena-start")
        self.reset = root.querySelector("#arena-reset")
        self.course = root.querySelector("#arena-race")
        self.cells = {name: root.querySelector(f"#arena-{name}")
                      for name in ("turns", "travel", "distance", "upright", "race-result")}
        self.view = draw.View(root.querySelector("canvas"), self.resized)
        # beest.arena, once pymunk has loaded.
        self.physics = None
        self.arena = None
        # The race the arena belongs to, when one was chosen.
        self.race = None
        # The beest on show, as chosen_beest() gave it, and what is wrong with it, if anything.
        self.beest: tuple[list[float], Layout | None] | None = None
        self.problem = ""
        self.evolved: tuple[list[float], Layout] | None = None
        self.running = False
        # Where the axle started, and the half-width and height in mm the view shows.
        self.start_x = 0.0
        self.half_width = self.top = 1.0
        self._loader: asyncio.Future | None = None
        self._owed = 0.0
        self._last_time: float | None = None
        self._scheduled = False
        self._shown: dict[str, str] = {}
        self._frame_proxy = create_proxy(self._frame)
        self.mirror("playing", "false")
        self._proxies = [listen(window, "hashchange", self.opened),
                         listen(self.start, "click", self.toggle),
                         listen(self.reset, "click", self.rebuild),
                         listen(self.choice, "change", self.rebuild),
                         listen(self.pairs, "change", self.adjusted),
                         listen(self.course, "change", self.adjusted)]
        self.opened(None)

    def offer_evolved(self, genes: list[float], layout: Layout) -> None:
        """Makes Evolve's best beest of the run (13 lengths a to m in mm, and its layout) a choice.

        Evolve calls this as it shows each best, so it only notes the beest: the arena stands it
        up when the tab is opened or the user acts, and never stops a walk for it.
        """
        self.evolved = [float(x) for x in genes], layout
        option = self.choice.querySelector(f'option[value="{EVOLVED}"]')
        option.disabled = False
        if not self.root.hidden and self.physics is not None:
            self.tell()

    @property
    def walked(self) -> bool:
        return self.arena is not None and self.arena.turns > 0

    @property
    def started(self) -> bool:
        """Whether the beest is walking, or has walked since it was stood up."""
        return self.running or self.walked

    def opened(self, event) -> None:
        """Loads the engine the first time the tab is shown; after that, shows the beest, or the
        chosen one if it has changed and this one has not started."""
        if self.root.hidden:
            return
        if self.physics is None:
            if self._loader is None:
                self._loader = asyncio.ensure_future(self.load())
            return
        if not self.started and self.chosen_beest() != self.beest:
            self.rebuild(None)
            return
        self.tell()
        # Frames stop while the tab is hidden, so a walk under way carries on from here.
        self._wake()

    def tell(self) -> None:
        """Says to press Reset when the chosen beest has changed since this one was stood up, or
        else what is wrong with this one, if anything."""
        if self.chosen_beest() != self.beest:
            self.say(STALE[self.choice.value], notice=True)
        else:
            self.say(self.problem)

    def say(self, text: str, notice: bool = False) -> None:
        """Shows a warning, or a notice when `notice`; empty text clears it. Text already on show
        is not announced again."""
        self.message.className = "notice" if notice and text else "warning"
        announce(self.message, text)

    async def load(self) -> None:
        self.mirror("status", "loading")
        self.say(LOADING, notice=True)
        try:
            physics = await engine()
        except Exception as error:
            self.mirror("status", "error")
            self.say(LOAD_FAILED)
            window.console.warn(f"The arena's physics engine did not load: {error!r}")
            # Opening the tab again tries again.
            self._loader = None
            return
        self.physics = physics
        for control in (self.choice, self.pairs, self.course, self.reset):
            control.disabled = False
        self.rebuild(None)

    def chosen_beest(self) -> tuple[list[float], Layout | None] | None:
        """The chosen beest's 13 lengths and, for Evolve's best, its layout; None when there is no
        such beest yet."""
        kind = self.choice.value
        if kind == EVOLVED:
            return self.evolved
        if kind == PLAYGROUND:
            lengths = self.playground()
            return [lengths[name] for name in LENGTH_NAMES], None
        return jansen_lengths(), None

    def chosen_layout(self) -> Layout:
        """Evolve's layout while Pairs is its own number of pairs, or else even throws."""
        pairs = int(self.pairs.value)
        layout = None if self.beest is None else self.beest[1]
        return layout if layout is not None and layout.pairs == pairs else Layout(pairs)

    def adjusted(self, event) -> None:
        """Pairs or the race was changed: the number of pairs shown stands, even for a best from
        Evolve."""
        self.rebuild(event, keep_pairs=True)

    def rebuild(self, event, keep_pairs: bool = False) -> None:
        """Stands the chosen beest at the start with its crank still.

        A best from Evolve other than the one on show brings its own number of pairs, unless
        `keep_pairs`.
        """
        if self.physics is None:
            return
        self.stop()
        self.arena = self.race = None
        beest = self.chosen_beest()
        new_best = self.choice.value == EVOLVED and beest is not None and beest != self.beest
        if new_best and not keep_pairs:
            self.pairs.value = str(beest[1].pairs)
        self.beest = beest
        layout = self.chosen_layout()
        course = self.course.value
        self.mirror("beest", self.choice.value)
        self.mirror("pairs", str(layout.pairs))
        self.mirror("race", course)
        self.problem = ""
        if beest is None:
            self.problem = "There is no such beest yet."
        else:
            try:
                if course == WALK:
                    self.arena = self.physics.Arena(beest[0], layout)
                else:
                    self.race = self.physics.Race(beest[0], layout, course)
                    self.arena = self.race.arena
            except ValueError as error:
                self.problem = f"{sentence(error)} It cannot walk."
            except Exception:
                self.arena = self.race = None
                self.problem = FAULT
                self.mirror("status", "error")
                window.console.error(
                    f"The arena could not stand the beest up.\n{traceback.format_exc()}")
        self.mirror("jammed", str(self.arena is None).lower())
        self.say(self.problem)
        # A beest can fall over before its race starts.
        self.start.disabled = self.arena is None or (self.race is not None and self.race.done)
        if self.arena is not None:
            self.fit_to_beest()
        self.show()

    def fit_to_beest(self) -> None:
        """Sizes the view to the beest as it stands: its reach from the axle, either side."""
        legs = self.arena.legs()
        axle = self.arena.axle
        reach = max(math.dist(p, axle) for leg in legs for p in leg.values())
        reach = max(reach, *(math.dist(p, axle) for p in self.arena.chassis_outline()))
        self.start_x = axle[0]
        self.half_width = VIEW_REACH * reach
        self.top = axle[1] + reach

    def toggle(self, event) -> None:
        if self.arena is None:
            return
        if self.running:
            self.stop()
        else:
            self.running = True
            self.start.textContent = "Pause"
            self.mirror("status", "running")
            self.mirror("playing", "true")
            self._wake()

    def stop(self) -> None:
        self.running = False
        self._last_time = None
        self._owed = 0.0
        self.start.textContent = "Start"
        self.mirror("status", "ready")
        self.mirror("playing", "false")

    def resized(self) -> None:
        self.show()

    def _wake(self) -> None:
        if not self._scheduled:
            self._scheduled = True
            window.requestAnimationFrame(self._frame_proxy)

    def _frame(self, now: float) -> None:
        # Frames stop while paused or hidden; Start and opening the tab begin them again.
        self._scheduled = False
        if self.root.hidden or self.arena is None:
            self._last_time = None
            return
        if self.running and self._last_time is not None:
            seconds = min((now - self._last_time) / 1000, MAX_FRAME_S)
            self._owed += seconds * self.physics.TURNS_PER_SECOND * self.physics.STEPS_PER_TURN
            steps = int(self._owed)
            self._owed -= steps
            try:
                (self.arena if self.race is None else self.race).step(steps)
            except Exception:
                self.stop()
                self.start.disabled = True
                self.mirror("status", "error")
                self.problem = FAULT
                self.say(FAULT)
                raise
            if self.race is not None and self.race.done:
                self.stop()
                self.start.disabled = True
        self._last_time = now if self.running else None
        self.show()
        if self.running:
            self._wake()

    def show(self) -> None:
        """Updates the numbers and draws the beest as it is now."""
        arena = self.arena
        if arena is None:
            for name in ("turns", "travel", "distance-per-turn", "tipped", "outcome", "race-turns"):
                self.mirror(name, "")
            for cell in self.cells.values():
                cell.textContent = ""
            if self.view.ready:
                self.view.clear()
            return
        result = arena.result()
        settled = result.turns >= SETTLED_TURNS
        self.mirror("turns", str(round(result.turns, 3)))
        self.mirror("travel", str(round(result.travel, 2)))
        self.mirror("distance-per-turn", str(round(result.distance, 2)) if settled else "")
        self.mirror("tipped", str(result.tipped).lower())
        self.cells["turns"].textContent = f"{result.turns:.1f}"
        self.cells["travel"].textContent = minus(f"{result.travel:.0f} mm")
        self.cells["distance"].textContent = (minus(f"{result.distance:.1f} mm") if settled
                                              else "after the first turn")
        self.cells["upright"].textContent = (
            f"No: it fell over {self.physics.fell(result.tipped_at)}" if result.tipped else "Yes")
        self.show_race()
        self.draw(result.tipped)

    def show_race(self) -> None:
        race = None if self.race is None else self.race.result
        self.mirror("outcome", "" if race is None else race.outcome.replace(" ", "-"))
        self.mirror("race-turns", "" if race is None else str(round(race.turns, 3)))
        if self.race is None:
            text = "No race: it just walks"
        elif race is not None:
            text = race.message
        else:
            text = "Under way" if self.walked else "Press Start to begin"
        self.cells["race-result"].textContent = text

    def draw(self, tipped: bool) -> None:
        view = self.view
        x, _ = self.arena.axle
        view.fit((x - self.half_width, -BELOW_MM, x + self.half_width, self.top),
                 pad=(ARROW_ROOM_PX, 0, 0, 0))
        if not view.ready:
            return
        view.clear()
        view.grid()
        # The box is centred on the axle, and the canvas may be wider than it.
        half = view.mm(view.width / 2)
        self.draw_ground(x - half, x + half)
        self.draw_course()
        view.arrow((x, self.top + view.mm(ARROW_ROOM_PX / 2)), (-1.0, 0.0),
                   "The beest walks this way")
        legs = self.arena.legs()
        outline = self.arena.chassis_outline()
        chassis = draw.JAM if tipped else draw.GROUND
        view.plate(outline, chassis)
        view.path(outline, closed=True, colour=chassis, width=2)
        # The other pairs behind, faint; the phase-0 pair in front, as the Leg tab draws a leg.
        for leg in legs[2:]:
            self.draw_leg(leg, faint=True)
        for leg in legs[:2]:
            self.draw_leg(leg, faint=False)
        view.hole(legs[0]["O"])

    def draw_leg(self, joints: dict[str, Point], faint: bool) -> None:
        view = self.view
        if faint:
            for name, p, q in STICKS:
                view.stick(joints[p], joints[q], FAINT[name], FAINT_STICK_PX)
            return
        for corners, colour in TRIANGLES:
            view.plate([joints[name] for name in corners], colour)
        for name, p, q in STICKS:
            view.stick(joints[p], joints[q], COLOURS[name])
        for name in ("C", "G", "J2", "J3", "J4", "J5"):
            view.hole(joints[name])
        view.hole(joints["F"], draw.TRACE)

    def draw_ground(self, x0: float, x1: float) -> None:
        """The ground, with a marker every MARK_MM along it from where the beest started."""
        view = self.view
        view.band(-BELOW_MM * 10, 0.0, draw.translucent(draw.GROUND, 0.25))
        view.path([(x0, 0.0), (x1, 0.0)], colour=draw.GROUND, width=2)
        # Marker k is k * MARK_MM to the left of the start.
        first = math.ceil((self.start_x - x1) / MARK_MM)
        last = math.floor((self.start_x - x0) / MARK_MM)
        labels = []
        for k in range(first, last + 1):
            mark = self.start_x - k * MARK_MM
            view.path([(mark, 0.0), (mark, -view.mm(6))], colour=draw.INK, width=1.5)
            labels.append(((mark, -view.mm(15)), "start" if k == 0 else minus(f"{k * MARK_MM} mm")))
        view.labels(labels, draw.MUTED)

    def draw_course(self) -> None:
        """The pencils or the towel, and the line every foot has to pass."""
        view = self.view
        course = self.arena.course
        if course.towel is not None:
            left, right = course.towel
            view.plate([*course.surface, (left, 0.0), (right, 0.0)], TOWEL)
            view.path(course.surface, colour=TOWEL, width=2)
        for centre in course.pencils:
            view.disc(centre, self.physics.PENCIL_DIAMETER_MM / 2, PENCIL)
        if course.finish_x is not None:
            flag = self.top * 0.6
            view.path([(course.finish_x, 0.0), (course.finish_x, flag)], colour=draw.INK,
                      width=1.5)
            view.text((course.finish_x, flag + view.mm(10)), "finish", draw.INK)

    def mirror(self, name: str, value: str) -> None:
        if self._shown.get(name) != value:
            self._shown[name] = value
            self.root.setAttribute(f"data-{name}", value)
