"""The code route's panel: the editor (app/editor.js), Reset to slide code, and the message and
traceback when the code stops a run.

The browser keeps the editor's text in its storage (app.storage), so a reload brings it back.
Storage can be blocked or full; the page then works on, forgets the code on reload, and says
so.
"""
from __future__ import annotations

import html
from collections.abc import Callable

from pyodide.ffi import create_once_callable, create_proxy, to_js
from pyscript import window
from pyscript.js_modules import editor

from app.controls import listen
from app.storage import keep, recall
from beest.fitness import INGREDIENTS
from beest.student_default import SOURCE

# Where the browser keeps the editor's text.
CODE_KEY = "strandbeest-sim.code"
RESET_QUESTION = "Put the slide code back? Your own code in the editor will be lost."

# What `fitness(leg)` can read, as the help lists it.
LEG_HELP = (
    ("leg.jams", "True when the beest cannot turn its crank all the way round"),
    ("leg.distance", "how far the beest walks in one turn of the crank, in mm (below 0 when it "
                     "walks the wrong way)"),
    ("leg.stride", "how far one foot moves along the ground while it is down, in mm"),
    ("leg.step_height", "how high one foot lifts, in mm"),
    ("leg.time_down", "the fraction of each turn that one foot is down, from 0 to 1"),
    ("leg.bob", "how far the body rises and falls in one turn, in mm (leg.flatness is the same)"),
    ("leg.closest_to_jam", "how near the tightest pair of sticks comes to not meeting, in mm"),
    ("leg.fits", "True when every stick fits on a lolly stick"),
    ('leg.normalised["stride"]', "an ingredient on the scale the Normalisation setting "
                                 "chooses, not flipped, so leg.normalised[\"flatness\"] is "
                                 "higher for a bumpier ride; the ingredients are "
                                 + ", ".join(f'"{name}"' for name in INGREDIENTS)),
    ("leg.genes", "the 13 lengths, a to m, in mm"),
)

PANEL_HTML = f"""
<div class="panel code-panel" hidden>
  <div class="panel-head">
    <h3>Your code</h3>
    <button type="button" class="ev-reset-code">Reset to slide code</button>
  </div>
  <p class="hint">Run scores every beest with your <code>fitness(leg)</code>, and the GA and hill
    climbing make each child with your <code>mutate(genes, rate)</code>. Tab indents a line; press
    Esc and then Tab to move on from the editor.</p>
  <div class="ev-editor"></div>
  <p class="warning ev-code-error" role="alert" hidden></p>
  <details class="ev-traceback" hidden>
    <summary>Traceback: where your code had got to</summary>
    <pre></pre>
  </details>
  <p class="hint ev-not-kept" hidden>This browser is not keeping your code, so copy it somewhere
    safe before you reload the page.</p>
  <details class="ev-help">
    <summary>What your code can use</summary>
    <dl>{"".join(f"<dt><code>{html.escape(name)}</code></dt><dd>{html.escape(text)}</dd>"
                 for name, text in LEG_HELP)}
      <dt><code>mutate(genes, rate)</code></dt>
      <dd><code>genes</code> is a list of the 13 lengths, a to m, and <code>rate</code> is the
        Mutation rate setting. Return the child's 13 lengths.</dd>
    </dl>
  </details>
</div>
"""


class CodePanel:
    """The editor and its buttons, at the top of Evolve's stage, shown on the code route.

    `on_reset` is called after Reset to slide code puts the slide code back.
    """

    def __init__(self, stage, on_reset: Callable[[], None]):
        stage.insertAdjacentHTML("afterbegin", PANEL_HTML)
        self.panel = stage.querySelector(".code-panel")
        self.on_reset = on_reset
        self.message = self.panel.querySelector(".ev-code-error")
        self.traceback = self.panel.querySelector(".ev-traceback")
        self.not_kept = self.panel.querySelector(".ev-not-kept")
        stored = recall(CODE_KEY)
        self._changed_proxy = create_proxy(self._changed)
        self.editor = editor.create(self.panel.querySelector(".ev-editor"),
                                    SOURCE if stored is None else stored, self._changed_proxy)
        self._proxies = [listen(self.panel.querySelector(".ev-reset-code"), "click",
                                self._reset_clicked)]

    @property
    def text(self) -> str:
        return self.editor.getText()

    @property
    def shown(self) -> bool:
        return not self.panel.hidden

    def show(self, shown: bool) -> None:
        appearing = shown and not self.shown
        self.panel.hidden = not shown
        if appearing:
            # A line marked while the panel was hidden could not be scrolled to then.
            self.editor.revealMark()

    def show_error(self, message: str | None, line: int | None = None,
                   trace: str | None = None, source: str | None = None) -> None:
        """Shows why the code stopped a run and offers `trace`; None clears them.

        `line` is marked while the editor still holds `source`, the code that ran.
        """
        self.message.hidden = message is None
        self.message.textContent = message or ""
        self.traceback.hidden = trace is None
        self.traceback.open = False
        self.traceback.querySelector("pre").textContent = trace or ""
        self.editor.markLine(line if source == self.text else None)
        if message is not None and self.shown:
            # The editor scrolls to the marked line on its next frame; the message follows.
            window.requestAnimationFrame(create_once_callable(self._reveal_message))

    def _reveal_message(self, now: float) -> None:
        self.message.scrollIntoView(to_js({"block": "nearest"},
                                          dict_converter=window.Object.fromEntries))

    def _changed(self) -> None:
        # The slide code itself is not kept, so the page's own SOURCE shows after a reload, and
        # nothing is lost then while the editor holds it.
        text = self.text
        self.not_kept.hidden = keep(CODE_KEY, None if text == SOURCE else text) or text == SOURCE

    def _reset_clicked(self, event=None) -> None:
        if self.text != SOURCE:
            if not window.confirm(RESET_QUESTION):
                return
            self.editor.setText(SOURCE)
        self.on_reset()
