"""The page's Python entry point: sets up each mode, then marks the status line ready.

index.html switches the tabs and reports a start-up error, so both work before Python is running.
"""

import sys

from pyscript import document

# An error setting up a mode stops here, before the status says ready.
from app.evolve_mode import EvolveMode
from app.fourbar_mode import FourBarMode
from app.leg_mode import LegMode

modes = [FourBarMode(document.getElementById("fourbar-mode")),
         LegMode(document.getElementById("leg-mode")),
         EvolveMode(document.getElementById("evolve-mode"))]

status = document.getElementById("status")
status.dataset.python = ".".join(str(part) for part in sys.version_info[:3])
status.textContent = "Python is ready."
status.dataset.status = "ready"
