"""Printing a template at actual size, or saving it as SVG files (decisions Q19).

Printing puts the template's pages in the page's #template-print and marks the body
`data-print="template"`, so the print stylesheet shows those pages alone, one to each A4 sheet at
210 × 297 mm. Both are cleared once printing is over, and when a print begins that no button asked
for, so that one prints the page itself.
"""
from __future__ import annotations

from collections.abc import Callable

from pyodide.ffi import create_once_callable
from pyscript import document, window
from pyscript.ffi import to_js

from app.controls import listen

SHEETS_ID = "template-print"
SVG_TYPE = "image/svg+xml"
# A saved file's address is released after this long, when its download has long started.
RELEASE_AFTER_MS = 60_000
SEVERAL_SAVED = ("Saved {count} files, one for each page. If your browser asks, let it download "
                 "several files.")

HTML = """
<div class="buttons">
  <button type="button" class="print-template" disabled>{print_text}</button>
  <button type="button" class="save-template" disabled>Download SVG</button>
</div>
<p class="hint">In the print settings choose 100% or "Actual size", not "Fit to page", then check
  the 100 mm bar with a ruler. Download SVG saves each A4 page as its own file.</p>
<p class="warning template-error" role="alert" hidden></p>
<p class="hint template-saved" role="status" hidden></p>
"""

# The print listeners, added on the first print.
_listening: list[object] = []
# Whether the next print is the one a button asked for.
_asked = False


def print_pages(pages: list[str]) -> None:
    """Opens the print dialog for `pages`, one SVG string per A4 page."""
    global _asked
    document.getElementById(SHEETS_ID).innerHTML = "".join(pages)
    document.body.dataset.print = "template"
    if not _listening:
        _listening.extend([listen(window, "beforeprint", _before_print),
                           listen(window, "afterprint", _clear)])
    _asked = True
    window.print()


def _before_print(event=None) -> None:
    global _asked
    if not _asked:
        _clear()
    _asked = False


def _clear(event=None) -> None:
    document.body.removeAttribute("data-print")
    document.getElementById(SHEETS_ID).replaceChildren()


def file_names(stem: str, pages: int) -> list[str]:
    """One name per page: `stem`.svg for a single page, else `stem`-page-1-of-2.svg and so on."""
    if pages == 1:
        return [f"{stem}.svg"]
    return [f"{stem}-page-{k}-of-{pages}.svg" for k in range(1, pages + 1)]


def save_pages(pages: list[str], stem: str) -> None:
    """Downloads each page as an SVG file."""
    for name, page in zip(file_names(stem, len(pages)), pages):
        blob = window.Blob.new(to_js([page]), to_js({"type": SVG_TYPE}))
        address = window.URL.createObjectURL(blob)
        link = document.createElement("a")
        link.href = address
        link.download = name
        # Some browsers follow only a link that is in the page.
        document.body.appendChild(link)
        link.click()
        link.remove()
        window.setTimeout(create_once_callable(lambda address=address:
                                               window.URL.revokeObjectURL(address)),
                          RELEASE_AFTER_MS)


class TemplateButtons:
    """A mode's print and download buttons for the template that `make` draws.

    `make` returns one SVG string per page, or raises ValueError, whose message is shown, for a
    template that cannot be printed at actual size. A message stays until the next press. The
    mode's root mirrors the number of pages last drawn in `data-template-pages` (0 when it could
    not be drawn).
    """

    def __init__(self, root, parent, print_text: str, stem: str,
                 make: Callable[[], list[str]]):
        self.root = root
        self.stem = stem
        self.make = make
        parent.innerHTML = HTML.format(print_text=print_text)
        self.print_button = parent.querySelector(".print-template")
        self.download_button = parent.querySelector(".save-template")
        self.error = parent.querySelector(".template-error")
        self.saved = parent.querySelector(".template-saved")
        self._proxies = [listen(self.print_button, "click", self._print_clicked),
                         listen(self.download_button, "click", self._download_clicked)]

    def enable(self) -> None:
        self.print_button.disabled = self.download_button.disabled = False

    def pages(self) -> list[str] | None:
        """The template's pages; None, with the reason shown, when it cannot be drawn."""
        self._show(self.saved, None)
        try:
            pages = self.make()
        except ValueError as exc:
            self._show(self.error, str(exc))
            self.root.dataset.templatePages = "0"
            return None
        self._show(self.error, None)
        self.root.dataset.templatePages = str(len(pages))
        return pages

    @staticmethod
    def _show(element, message: str | None) -> None:
        element.hidden = message is None
        element.textContent = message or ""

    def _print_clicked(self, event=None) -> None:
        if (pages := self.pages()) is not None:
            print_pages(pages)

    def _download_clicked(self, event=None) -> None:
        if (pages := self.pages()) is not None:
            save_pages(pages, self.stem)
            if len(pages) > 1:
                self._show(self.saved, SEVERAL_SAVED.format(count=len(pages)))
