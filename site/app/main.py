"""The page's Python entry point: sets up each mode, then marks the status line ready.

index.html switches the tabs and reports a start-up error, so both work before Python is running.
"""

import sys

from pyscript import document

# An error setting up a mode stops here, before the status says ready.
from app.arena_mode import ArenaMode
from app.evolve_mode import EvolveMode
from app.fourbar_mode import FourBarMode
from app.leg_mode import LegMode

leg = LegMode(document.getElementById("leg-mode"))
arena = ArenaMode(document.getElementById("arena-mode"), playground=lambda: leg.lengths)
# Evolve hands each best beest it shows to the arena.
modes = [FourBarMode(document.getElementById("fourbar-mode")), leg,
         EvolveMode(document.getElementById("evolve-mode"), on_best=arena.offer_evolved), arena]

status = document.getElementById("status")
status.dataset.python = ".".join(str(part) for part in sys.version_info[:3])
status.textContent = "Python is ready."
status.dataset.status = "ready"
