"""A whole beest walking on flat ground in 2D physics: the arena (decisions Q2, Q3).

Units are mm, g and s, with y up and the ground's surface at y = 0. The beest walks −x. pymunk is
the only library outside the standard library in beest/, and only this module imports it, so the
rest of the model runs without it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pymunk

from .geometry import (ANGLES, LENGTH_NAMES, _LEG_JOINTS, LegTrace, Point, _fixed_joints,
                       _nearest, circ, trace_leg)
from .leg import STICKS, Layout

STEPS_PER_TURN = 600
TURNS_PER_SECOND = 1.0
CHASSIS_G = 30.0
STICK_G = 1.0
GRAVITY_MM_S2 = 9810.0
# Solver passes per physics step.
SOLVER_ITERATIONS = 30
FOOT_RADIUS_MM = 2.0
# Half a stick's thickness, where it can touch the ground.
STICK_RADIUS_MM = 1.0
# How far the chassis box reaches beyond the crank axle and the two fixed pivots.
CHASSIS_MARGIN_MM = 5.0
FRICTION = 1.0
# The beest starts this far above the ground, then stands with its crank held for SETTLE_STEPS.
DROP_MM = 0.5
SETTLE_STEPS = 300
# A beest has tipped once its chassis leans further than this or touches the ground.
TIP_ANGLE_DEG = 30.0
ARENA_TURNS = 10
# The ground runs this far each way from where the beest starts, and is this thick.
GROUND_HALF_LENGTH_MM = 10_000_000.0
GROUND_DEPTH_MM = 10.0

# Each stick's two joints; the crank m runs from the axle O to the crank pin C.
STICK_ENDS: dict[str, tuple[str, str]] = {
    "b": ("G", "J2"), "c": ("G", "J4"), "d": ("G", "J3"), "e": ("J2", "J3"), "f": ("J3", "J5"),
    "g": ("J4", "J5"), "h": ("J5", "F"), "i": ("J4", "F"), "j": ("C", "J2"), "k": ("C", "J4"),
    "m": ("O", "C")}
# The sticks of one leg that move as one body: the two triangles, and each other stick alone.
LEG_BODIES = (("j",), ("k",), ("b", "d", "e"), ("c",), ("f",), ("g", "h", "i"))
# The beest's own parts pass through each other (they lie side by side) but not through the ground.
_BEEST_GROUP = 1


def _lengths(genes: list[float]) -> dict[str, float]:
    if len(genes) != len(LENGTH_NAMES):
        raise ValueError(f"a leg needs {len(LENGTH_NAMES)} lengths (a to m), not {len(genes)}")
    lengths = dict(zip(LENGTH_NAMES, (float(x) for x in genes)))
    for name, length in lengths.items():
        if not math.isfinite(length):
            raise ValueError(f"length {name} must be an ordinary number, not {length}")
        if name in STICKS and length <= 0:
            raise ValueError(f"stick {name} must be longer than 0 mm, not {length}")
    return lengths


def _pose(lengths: dict[str, float], trace: LegTrace, theta: float) -> dict[str, Point]:
    """The joints at crank angle theta, on the branches the leg tracked round to there."""
    theta %= 2 * math.pi
    n = len(trace.joints)
    near = trace.joints[round(theta * n / (2 * math.pi)) % n]
    joints = _fixed_joints(lengths, theta)
    for name, p, r1, q, r2, _, _ in _LEG_JOINTS:
        points = circ(joints[p], lengths[r1], joints[q], lengths[r2])
        if points is None:
            raise ValueError(f"this leg jams: {r1} and {r2} cannot meet at "
                             f"{round(math.degrees(theta))}°")
        joints[name] = _nearest(points, near[name])
    return joints


def starting_legs(genes: list[float], layout: Layout = Layout()) -> list[dict[str, Point]]:
    """Every leg's joints with the crank at θ = 0, in mm with the axle O at the origin.

    One pair per throw in the layout's order, each the original leg then its mirror. Each joint
    is where the leg has tracked to from θ = 0 (decisions Q14), not Al's rule applied afresh.
    """
    return _starting_legs(_lengths(genes), layout)


def _starting_legs(lengths: dict[str, float], layout: Layout) -> list[dict[str, Point]]:
    # Traced at the angles leg_from checks, so the arena and the GA agree on which legs jam.
    trace = trace_leg(lengths, ANGLES)
    if trace.jammed:
        raise ValueError(f"this leg jams: {trace.jam_reason}")
    legs = []
    for phase in layout.phases:
        theta = math.radians(phase)
        legs.append(_pose(lengths, trace, theta))
        mirror = _pose(lengths, trace, math.pi - theta)
        legs.append({name: (-x, y) for name, (x, y) in mirror.items()})
    return legs


def _chassis_box(lengths: dict[str, float]) -> list[Point]:
    """The chassis: a box round the axle and both fixed pivots, corners anticlockwise."""
    half = abs(lengths["a"]) + CHASSIS_MARGIN_MM
    low = min(0.0, -lengths["l"]) - CHASSIS_MARGIN_MM
    high = max(0.0, -lengths["l"]) + CHASSIS_MARGIN_MM
    return [(-half, low), (half, low), (half, high), (-half, high)]


@dataclass(frozen=True)
class ArenaResult:
    """How a beest has walked in the arena so far."""
    # Crank turns since the crank started.
    turns: float
    # How far the axle moved towards −x since then, in mm; negative when the beest went backwards.
    travel: float
    # Travel per crank turn.
    distance: float
    tipped: bool
    # Crank turns made when it tipped: 0 if it tipped while standing still.
    tipped_at: float | None
    # The furthest the chassis leant from level, in degrees.
    max_tilt: float


class Arena:
    """A beest on flat ground, stepped one physics step at a time.

    Building it stands the beest on the ground with the crank held still; each step after that
    turns the crank by 1 / STEPS_PER_TURN of a turn, θ growing as in the brief, so it walks −x.
    """

    def __init__(self, genes: list[float], layout: Layout = Layout()) -> None:
        lengths = _lengths(genes)
        legs = _starting_legs(lengths, layout)
        self.layout = layout
        box = _chassis_box(lengths)
        feet = [leg["F"][1] - FOOT_RADIUS_MM for leg in legs]
        joints = [y - STICK_RADIUS_MM for leg in legs for _, y in leg.values()]
        lift = DROP_MM - min(feet + joints + [box[0][1]])

        def up(p: Point) -> Point:
            return (p[0], p[1] + lift)

        space = pymunk.Space()
        space.gravity = (0.0, -GRAVITY_MM_S2)
        space.iterations = SOLVER_ITERATIONS
        depth = GROUND_DEPTH_MM / 2
        ground = pymunk.Segment(space.static_body, (-GROUND_HALF_LENGTH_MM, -depth),
                                (GROUND_HALF_LENGTH_MM, -depth), depth)
        ground.friction = FRICTION
        space.add(ground)
        own = pymunk.ShapeFilter(group=_BEEST_GROUP)

        def shape(s: pymunk.Shape, mass: float) -> None:
            s.mass, s.friction, s.filter = mass, FRICTION, own
            space.add(s)

        chassis = pymunk.Body()
        space.add(chassis)
        self._box = pymunk.Poly(chassis, [up(p) for p in box])
        shape(self._box, CHASSIS_G)
        crank = pymunk.Body()
        space.add(crank)
        for leg in legs[::2]:
            shape(pymunk.Segment(crank, up(leg["O"]), up(leg["C"]), STICK_RADIUS_MM), STICK_G)
        space.add(pymunk.PivotJoint(chassis, crank, up((0.0, 0.0))))
        # A SimpleMotor turns its second body at minus its rate relative to the first.
        self._motor = pymunk.SimpleMotor(chassis, crank, 0.0)
        space.add(self._motor)

        # For each leg, the body and local point each joint is read from.
        self._reads: list[dict[str, tuple[pymunk.Body, pymunk.Vec2d]]] = []
        for leg in legs:
            # The bodies that hold each joint; the first is pinned to each of the others there.
            holders: dict[str, list[pymunk.Body]] = {"O": [chassis], "G": [chassis], "C": [crank]}
            for group in LEG_BODIES:
                body = pymunk.Body()
                space.add(body)
                for name in group:
                    p, q = STICK_ENDS[name]
                    shape(pymunk.Segment(body, up(leg[p]), up(leg[q]), STICK_RADIUS_MM), STICK_G)
                # In a fixed order, so every run builds the same space and repeats exactly.
                for joint in dict.fromkeys(end for name in group for end in STICK_ENDS[name]):
                    holders.setdefault(joint, []).append(body)
            shape(pymunk.Circle(holders["F"][0], FOOT_RADIUS_MM, up(leg["F"])), 0.0)
            for joint, bodies in holders.items():
                for other in bodies[1:]:
                    space.add(pymunk.PivotJoint(bodies[0], other, up(leg[joint])))
            self._reads.append({name: (holders[name][0], holders[name][0].world_to_local(up(p)))
                                for name, p in leg.items()})

        self._space = space
        self._chassis = chassis
        self._axle = chassis.world_to_local(up((0.0, 0.0)))
        self._box_corners = [chassis.world_to_local(up(p)) for p in box]
        self._dt = 1 / (STEPS_PER_TURN * TURNS_PER_SECOND)
        self._turning = False
        self._turning_steps = 0
        self.max_tilt = 0.0
        self.tipped_at: float | None = None
        for _ in range(SETTLE_STEPS):
            self._advance()
        self._start_x = self.axle[0]
        # Negative, so θ grows.
        self._motor.rate = -2 * math.pi * TURNS_PER_SECOND
        self._turning = True

    def _advance(self) -> None:
        self._space.step(self._dt)
        if self._turning:
            self._turning_steps += 1
        tilt = abs(math.degrees(math.remainder(self._chassis.angle, 2 * math.pi)))
        self.max_tilt = max(self.max_tilt, tilt)
        if self.tipped_at is None and (tilt > TIP_ANGLE_DEG or self._box.bb.bottom <= 0):
            self.tipped_at = self.turns

    def step(self, n: int = 1) -> None:
        """Turn the crank on by n physics steps."""
        if not isinstance(n, int) or isinstance(n, bool) or n < 0:
            raise ValueError(f"the arena steps a whole number of times, 0 or more, not {n!r}")
        for _ in range(n):
            self._advance()

    def run(self, turns: float = ARENA_TURNS) -> ArenaResult:
        """Turn the crank on by this many turns and say how the beest has done so far."""
        if not 0 <= turns < math.inf:
            raise ValueError(f"the crank turns 0 or more times, not {turns}")
        self.step(round(turns * STEPS_PER_TURN))
        return self.result()

    @property
    def turns(self) -> float:
        """Crank turns since the crank started."""
        return self._turning_steps / STEPS_PER_TURN

    @property
    def tipped(self) -> bool:
        return self.tipped_at is not None

    @property
    def axle(self) -> Point:
        """Where the crank axle O is now, in mm."""
        x, y = self._chassis.local_to_world(self._axle)
        return (x, y)

    @property
    def travel(self) -> float:
        """How far the axle has moved towards −x since the crank started, in mm."""
        return self._start_x - self.axle[0]

    def legs(self) -> list[dict[str, Point]]:
        """Every leg's joints now, in mm, in starting_legs' order (the phase-0 pair first)."""
        legs = []
        for reads in self._reads:
            leg = {}
            for name, (body, local) in reads.items():
                x, y = body.local_to_world(local)
                leg[name] = (x, y)
            legs.append(leg)
        return legs

    def chassis_outline(self) -> list[Point]:
        """The chassis box's corners now, in mm."""
        return [(v.x, v.y) for v in map(self._chassis.local_to_world, self._box_corners)]

    def result(self) -> ArenaResult:
        turns = self.turns
        travel = self.travel
        return ArenaResult(turns=turns, travel=travel, distance=travel / turns if turns else 0.0,
                           tipped=self.tipped, tipped_at=self.tipped_at, max_tilt=self.max_tilt)


def run(genes: list[float], layout: Layout = Layout(), turns: float = ARENA_TURNS) -> ArenaResult:
    """Stand the beest these 13 lengths (a to m) describe on the ground and walk it."""
    return Arena(genes, layout).run(turns)
