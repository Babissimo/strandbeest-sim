"""The code route: the editor's starting text, and how the editor's text becomes functions.

SOURCE's fitness scores as the settings route's default does, and its mutate follows the brief's
§4 (decisions S5). Student code runs as a module of its own, so it imports what it uses, as SOURCE
does.
"""
from __future__ import annotations

import io
import linecache
from collections.abc import Callable

from .ga import EDITOR, StudentCodeError

SOURCE = '''\
import random

from beest.ga import clamp


def fitness(leg):
    # A beest that jams scores nothing.
    if leg.jams:
        return 0
    # How far it walks and how much its body bobs, on the Normalisation setting's scale.
    distance = leg.normalised["distance"]
    bob = leg.normalised["flatness"]
    # Further is better and less bob is better, so average distance with 1 - bob.
    return (distance + (1 - bob)) / 2


def mutate(genes, rate):
    child = []
    for length in genes:
        if random.random() < rate:
            length = length + random.gauss(0, 3)
        child.append(length)
    return clamp(child)
'''

FUNCTIONS = {"fitness": "fitness(leg)", "mutate": "mutate(genes, rate)"}


def student_functions(source: str) -> tuple[Callable, Callable]:
    """Run the editor's text and return the `fitness` and `mutate` it defines.

    A syntax error or an exception while it runs propagates unchanged.
    """
    # Tracebacks then show each editor line beside its number, so the lines break only where
    # Python's do (not at a form feed, as str.splitlines would).
    lines = io.StringIO(source, newline=None).readlines()
    linecache.cache[EDITOR] = (len(source), None, lines, EDITOR)
    namespace: dict[str, object] = {"__name__": "student"}
    exec(compile(source, EDITOR, "exec"), namespace)
    for name, signature in FUNCTIONS.items():
        if not callable(namespace.get(name)):
            raise StudentCodeError(name, f"The code needs a function {signature}.")
    return namespace["fitness"], namespace["mutate"]
