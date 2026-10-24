"""The page's Python entry point: loads the model, then marks the status line ready.

index.html switches the tabs and reports a start-up error, so both work before Python is running.
"""

import sys

from pyscript import document

# An error importing the model stops here, before the status says ready.
import beest.geometry  # noqa: F401

status = document.getElementById("status")
status.dataset.python = ".".join(str(part) for part in sys.version_info[:3])
status.textContent = "Python is ready."
status.dataset.status = "ready"
