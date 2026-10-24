"""A whole beest drawn from its lengths and layout: every leg at the crank's angle, walking left.

The body is held still and the ground moves under it. Each pair is a leg and its mirror image on
one crank throw; the pair on the throw at 0° is drawn darker, in front.
"""
from __future__ import annotations

import math

from app import draw
from app.controls import Animator
from beest.geometry import ANGLES, DRAW_ANGLES, LENGTH_NAMES, LegTrace, Point, trace_leg
from beest.measures import throw_steps

# Each stick of a leg: the joints at its ends.
LEG_STICKS = (("C", "J2"), ("G", "J2"), ("G", "J3"), ("J2", "J3"), ("C", "J4"), ("G", "J4"),
              ("J3", "J5"), ("J4", "J5"), ("J4", "F"), ("J5", "F"))
TRIANGLES = (("G", "J2", "J3"), ("J4", "J5", "F"))
FRONT = draw.COUPLER
BEHIND = draw.translucent(draw.COUPLER, 0.28)
# Room above the beest for the arrow and its label, in px.
ARROW_ROOM = 52

Joints = dict[str, Point]


def mirrored(joints: Joints) -> Joints:
    return {name: (-x, y) for name, (x, y) in joints.items()}


class BeestPicture:
    """The best beest on its canvas, turned by an Animator whose controls sit inside `root`."""

    def __init__(self, root, canvas):
        self.view = draw.View(canvas, self._resized)
        self.animator = Animator(root, self.draw)
        self.trace: LegTrace | None = None
        self.foot: list[Point] = []
        self.shifts: list[int] = []
        self.key: tuple | None = None

    def show(self, genes: list[float], phases: list[float], margin: float, jams: bool) -> None:
        """Draws this beest from now on; the same beest again changes nothing.

        `margin` is the run's jam margin and `jams` what the run found. A leg that jams only
        between the angles it was scored at is drawn at those angles, so the picture agrees.
        """
        key = (tuple(genes), tuple(phases), margin, jams)
        if key == self.key:
            return
        self.key = key
        lengths = dict(zip(LENGTH_NAMES, genes))
        n = DRAW_ANGLES
        trace = trace_leg(lengths, n, margin)
        if trace.jammed != jams:
            n = ANGLES
            trace = trace_leg(lengths, n, margin)
        self.trace = trace
        self.foot = trace.foot
        self.shifts = throw_steps(phases, n)
        self._fit()
        self.animator.load(trace.angles, n, loops=not trace.jammed)

    def legs(self, index: int) -> list[list[Joints]]:
        """Each pair's two legs at this step of the turn, the pair on the 0° throw first.

        A jammed beest is drawn as its first leg alone, which turns only as far as the jam.
        """
        joints = self.trace.joints
        if self.trace.jammed:
            return [[joints[index]]]
        n = len(joints)
        # The mirror image at crank angle θ is the leg at 180° − θ, reflected.
        return [[joints[(index + s) % n], mirrored(joints[(n // 2 - index - s) % n])]
                for s in self.shifts]

    def _fit(self) -> None:
        points = [p for joints in self.trace.joints for p in joints.values()]
        if not self.trace.jammed:
            points += [(-x, y) for x, y in points]
        if not points:
            points = [(0.0, 0.0)]
        self.view.fit(draw.bounds(points), pad=(ARROW_ROOM, 0, 12, 0))

    def _resized(self) -> None:
        if self.trace is not None:
            self._fit()
        self.animator.draw_now()

    def draw(self, index: int | None) -> bool:
        view = self.view
        if not view.ready:
            return False
        view.clear()
        if self.trace is None or index is None:
            message = ("This beest cannot be put together: its sticks do not meet."
                       if self.trace is not None else "The best beest appears here.")
            view.text((view.width / 2, view.height / 2), message, world=False)
            return True
        front, *behind = self.legs(index)
        # The lowest foot carries the body, so the ground passes under it.
        ground = min(leg["F"][1] for pair in (front, *behind) for leg in pair)
        x0, _, x1, y1 = view.box
        view.path([(x0 - 1000, ground), (x1 + 1000, ground)], colour=draw.GROUND, width=2)
        view.path(self.foot, closed=not self.trace.jammed, colour=draw.TRACE, width=1.5)
        for pair in behind:
            for leg in pair:
                self._leg(leg, BEHIND, front=False)
        if len(front) == 2:
            # The frame joins the two fixed pivots.
            view.stick(front[0]["G"], front[1]["G"], draw.GROUND)
        for leg in front:
            self._leg(leg, FRONT, front=True)
        for pair in (*behind, front):
            view.stick((0.0, 0.0), pair[0]["C"], draw.CRANK)
        view.hole(front[0]["C"])
        view.pivot((0.0, 0.0))
        for leg in front:
            view.pivot(leg["G"])
        if self.trace.jam_angle is not None and index == len(self.trace.joints) - 1:
            theta, m = self.trace.jam_angle, math.dist(front[0]["O"], front[0]["C"])
            view.cross((m * math.cos(theta), m * math.sin(theta)))
        # The arrow sits a fixed distance above the beest, however it is scaled.
        above = (ARROW_ROOM - 18) / view.scale
        view.arrow(((x0 + x1) / 2, y1 + above), (-1.0, 0.0), "walks this way")
        return True

    def _leg(self, joints: Joints, colour: str, front: bool) -> None:
        view = self.view
        if front:
            for corners in TRIANGLES:
                view.plate([joints[name] for name in corners], colour)
        for p, q in LEG_STICKS:
            view.stick(joints[p], joints[q], colour, width=draw.STICK_PX - 3)
        if front:
            for name in ("J2", "J3", "J4", "J5", "F"):
                view.hole(joints[name], colour)
