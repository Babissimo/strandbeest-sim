"""Controls shared by the modes: sliders with number boxes, and the crank animation."""
from __future__ import annotations

import math
from collections.abc import Callable

from pyodide.ffi import create_proxy
from pyscript import document, window

from beest.geometry import FourBarTrace, LegTrace

# A frame that comes late (the tab was in the background) moves the crank no further than this.
MAX_FRAME_S = 0.1
# Typed values keep this many decimal places, all a number box shows.
DECIMALS = 2


def shown(value: float, decimals: int = DECIMALS) -> str:
    """A value as a number box shows it: no trailing zeros."""
    text = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def listen(element, event: str, handler: Callable) -> object:
    """Calls `handler(event)` on each event; returns the proxy, which lives as long as the page."""
    proxy = create_proxy(handler)
    element.addEventListener(event, proxy)
    return proxy


class Slider:
    """A slider beside a number box, both showing one value that stays within its bounds.

    Dragging the slider moves in steps of `step`; a typed value keeps DECIMALS places, and one
    outside the bounds is brought back within them when the box is left or Enter is pressed. When
    the bounds move, the value keeps as near the one last chosen as they allow, so it comes back
    once they widen again.
    """

    def __init__(self, parent, key: str, label: str, bounds: tuple[float, float], value: float,
                 on_change: Callable[[], None], step: float = 0.1, colour: str | None = None):
        self.on_change = on_change
        self.step = step
        self.chosen = self.value = float(value)
        self.low = self.high = math.nan
        row = document.createElement("div")
        row.className = "slider"
        name = document.createElement("label")
        name.htmlFor = key
        if colour is not None:
            # Matches the stick's colour in the drawing.
            swatch = document.createElement("span")
            swatch.className = "swatch"
            swatch.style.background = colour
            name.appendChild(swatch)
        name.append(label)
        self.slider = document.createElement("input")
        self.slider.type = "range"
        self.slider.id = f"{key}-slider"
        self.slider.step = str(step)
        self.slider.tabIndex = -1
        self.slider.setAttribute("aria-label", label)
        self.box = document.createElement("input")
        self.box.type = "number"
        self.box.id = key
        self.box.step = str(step)
        # The decimal keypad on tablets has no minus sign.
        if bounds[0] >= 0:
            self.box.inputMode = "decimal"
        for element in (name, self.slider, self.box):
            row.appendChild(element)
        parent.appendChild(row)
        self.set_bounds(bounds)
        self.set(value)
        self._proxies = [listen(self.slider, "input", self._slid),
                         listen(self.box, "input", self._typed),
                         listen(self.box, "change", self._committed)]

    def set(self, value: float) -> None:
        """Chooses `value`, kept within the bounds, without calling `on_change`."""
        self.chosen = self.value = float(min(max(value, self.low), self.high))
        self.slider.value = str(self.value)
        self.box.value = shown(self.value)

    def set_bounds(self, bounds: tuple[float, float]) -> bool:
        """Moves the bounds; True if that moved the value."""
        if tuple(bounds) == (self.low, self.high):
            return False
        self.low, self.high = bounds
        # The ends sit on whole steps just inside the bounds, so dragging and the arrow keys give
        # round values that stay within them.
        low = math.ceil(self.low / self.step - 1e-9) * self.step
        high = math.floor(self.high / self.step + 1e-9) * self.step
        if low > high:
            low, high = self.low, self.high
        for element in (self.slider, self.box):
            element.min, element.max = shown(low, 6), shown(high, 6)
        value = float(min(max(self.chosen, self.low), self.high))
        moved = value != self.value
        self.value = value
        # New ends make the slider snap its thumb, so it is always set again.
        self.slider.value = str(value)
        if moved:
            # Left alone otherwise: the student may be typing in it.
            self.box.value = shown(value)
        return moved

    def _slid(self, event) -> None:
        dragged = round(float(self.slider.value), 6)
        self.chosen = self.value = min(max(dragged, self.low), self.high)
        self.box.value = shown(self.value)
        self.on_change()

    def _typed_value(self) -> float:
        # NaN while the box holds no number; JS hands whole numbers to Python as ints.
        return round(float(self.box.valueAsNumber), DECIMALS)

    def _typed(self, event) -> None:
        # Half-typed numbers outside the bounds wait for the box to be left.
        typed = self._typed_value()
        if not (math.isfinite(typed) and self.low <= typed <= self.high):
            return
        self.chosen = typed
        if typed != self.value:
            self.value = typed
            self.slider.value = str(typed)
            self.on_change()

    def _committed(self, event) -> None:
        typed = self._typed_value()
        if not math.isfinite(typed):
            self.box.value = shown(self.value)
            return
        before = self.value
        self.set(typed)
        if self.value != before:
            self.on_change()


def announce(region, text: str) -> None:
    """Puts `text` in a live region, such as a jam warning, only when it changes.

    The region stays on the page while empty (out of sight), so screen readers announce it as it
    fills, and a drag that keeps the same text is not announced again.
    """
    if region.textContent != text:
        region.textContent = text


def swings(trace: FourBarTrace | LegTrace) -> str:
    """What Animator does with a jammed trace, as a sentence to follow its jam warning."""
    if len(trace.angles) < 2:
        return ""
    if trace.jam_angle is None:
        return " The crank can only swing back and forth."
    return " The crank can only swing back and forth up to there."


class Animator:
    """Turns the crank through a traced turn, one animation frame at a time.

    It starts paused with the crank at 0°, and Play turns it. A full turn goes round and round. A
    linkage that jams swings from the start to its last position before the jam and back.
    `draw(index)` draws the linkage at that traced angle (None when nothing was traced) and says
    whether it could; a new trace or `redraw` draws it again while paused. The root element shows
    `data-playing`, `data-angle`, the angle drawn last, and `data-drawn-to`, the furthest angle
    drawn since the trace was loaded, both in whole degrees. Frames start with the first `load`.
    """

    def __init__(self, root, draw: Callable[[int | None], bool]):
        self.root = root
        self.draw = draw
        self.angles: list[float] = []
        self.per_turn = 1
        self.loops = True
        self.position = 0.0
        self.direction = 1
        self.drawn_to: int | None = None
        self._last_time: float | None = None
        self._stale = True
        self._failed = False
        self._shown: dict[str, str] = {}
        self.button = root.querySelector(".play")
        self.speed = root.querySelector(".speed")
        self.speed_shown = root.querySelector(".speed-shown")
        self.playing = False
        self.button.textContent = "Play"
        self._proxies = [listen(self.button, "click", self._toggle),
                         listen(self.speed, "input", self._show_speed)]
        self._show_speed(None)
        self._mirror("playing", "false")
        self._frame_proxy = create_proxy(self._frame)
        self._scheduled = False

    def load(self, angles: list[float], per_turn: int, loops: bool) -> None:
        """Animates a new trace, keeping the crank near where it was."""
        # The same angle at the new number of samples a turn.
        self.position *= per_turn / self.per_turn
        self.angles, self.per_turn, self.loops = angles, per_turn, loops
        count = len(angles)
        if count == 0:
            self.position = 0.0
        elif loops:
            self.position %= count
        elif self.position >= count - 1:
            self.position, self.direction = count - 1, -1
        self.drawn_to = None
        self._mirror("drawn-to", "")
        self._failed = False
        self.button.disabled = self.speed.disabled = False
        self.redraw()

    def redraw(self) -> None:
        """Draws again on the next frame, playing or not."""
        self._stale = True
        self._wake()

    def draw_now(self) -> None:
        """Draws straight away, as after a resize, which clears the canvas."""
        if not (self._failed or self.root.hidden):
            self._stale = False
            self._show()
        self._wake()

    @property
    def index(self) -> int | None:
        return min(int(self.position), len(self.angles) - 1) if self.angles else None

    def _advance(self, steps: float) -> None:
        last = len(self.angles) - 1
        if last <= 0:
            return
        if self.loops:
            self.position = (self.position + steps) % len(self.angles)
            return
        # Each end is drawn exactly, however fast the crank turns.
        self.position += self.direction * steps
        if self.position >= last:
            self.position, self.direction = float(last), -1
        elif self.position <= 0:
            self.position, self.direction = 0.0, 1

    def _wake(self) -> None:
        if not self._scheduled:
            self._scheduled = True
            window.requestAnimationFrame(self._frame_proxy)

    def _frame(self, now: float) -> None:
        # Frames stop while paused, hidden or failed; redraw(), draw_now() and Play start them.
        self._scheduled = False
        if self.root.hidden or self._failed:
            self._last_time = None
            return
        if self.playing and self._last_time is not None:
            seconds = min((now - self._last_time) / 1000, MAX_FRAME_S)
            self._advance(seconds * self.turns_per_minute / 60 * self.per_turn)
        self._last_time = now if self.playing else None
        if self.playing or self._stale:
            self._stale = False
            self._show()
        if self.playing:
            self._wake()

    def _show(self) -> None:
        index = self.index
        try:
            drew = self.draw(index)
        except Exception:
            # Logged once; drawing waits for the next trace rather than failing every frame.
            self._failed = True
            raise
        if not drew:
            return
        if index is None:
            self._mirror("angle", "")
            self._mirror("drawn-to", "")
            return
        degrees = round(math.degrees(self.angles[index]))
        self.drawn_to = degrees if self.drawn_to is None else max(self.drawn_to, degrees)
        self._mirror("angle", str(degrees))
        self._mirror("drawn-to", str(self.drawn_to))

    def _mirror(self, name: str, value: str) -> None:
        if self._shown.get(name) != value:
            self._shown[name] = value
            self.root.setAttribute(f"data-{name}", value)

    def _toggle(self, event) -> None:
        self.playing = not self.playing
        self.button.textContent = "Pause" if self.playing else "Play"
        self._mirror("playing", str(self.playing).lower())
        self._wake()

    def _show_speed(self, event) -> None:
        self.turns_per_minute = float(self.speed.value)
        turns = round(self.turns_per_minute)
        self.speed_shown.textContent = f"{turns} turn{'' if turns == 1 else 's'} a minute"
