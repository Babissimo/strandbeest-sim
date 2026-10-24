"""A whole beest walking in 2D physics, and the races it can run: the arena (decisions Q2, Q3).

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
# A beest has tipped once its chassis leans further than this, or touches the ground or anything
# lying on it.
TIP_ANGLE_DEG = 30.0
ARENA_TURNS = 10
# The ground runs this far each way from where the beest starts, and is this thick.
GROUND_HALF_LENGTH_MM = 10_000_000.0
GROUND_DEPTH_MM = 10.0

# What can lie on the ground. A course starts RUN_UP_MM ahead of the beest's front and runs on
# towards −x.
COURSES = ("flat", "pencils", "towel")
RUN_UP_MM = 20.0
# Pencils are fixed, lying across the beest's path. Their paint is slippery.
PENCIL_DIAMETER_MM = 7.5
PENCIL_SPACING_MM = 40.0
PENCIL_COUNT = 8
PENCIL_FRICTION = 0.3
# The towel is ground with more grip, rising and falling smoothly (a cosine) by TOWEL_BUMP_MM
# every TOWEL_BUMP_SPACING_MM. Its steepest slope, 32°, is gentle enough that a foot pushed into
# a bump rides up it rather than levering the beest over.
TOWEL_LENGTH_MM = 500.0
TOWEL_FRICTION = 1.5
TOWEL_BUMP_MM = 2.0
TOWEL_BUMP_SPACING_MM = 10.0
# Straight pieces each bump is built from, and their half-thickness.
TOWEL_PIECES_PER_BUMP = 10
TOWEL_SURFACE_RADIUS_MM = 0.5

# The races (brief §4) and the course each is run on.
RACES = {"distance": "flat", "pencils": "pencils", "towel": "towel"}
# The distance race lasts this many turns; the others give up after MAX_RACE_TURNS.
DISTANCE_TURNS = 10
MAX_RACE_TURNS = 20
# A race is decided only every this many physics steps, however the steps are taken.
CHECK_STEPS = 10

# Each stick's two joints; the crank m runs from the axle O to the crank pin C.
STICK_ENDS: dict[str, tuple[str, str]] = {
    "b": ("G", "J2"), "c": ("G", "J4"), "d": ("G", "J3"), "e": ("J2", "J3"), "f": ("J3", "J5"),
    "g": ("J4", "J5"), "h": ("J5", "F"), "i": ("J4", "F"), "j": ("C", "J2"), "k": ("C", "J4"),
    "m": ("O", "C")}
# The sticks of one leg that move as one body: the two triangles, and each other stick alone.
LEG_BODIES = (("j",), ("k",), ("b", "d", "e"), ("c",), ("f",), ("g", "h", "i"))
# The beest's own parts pass through each other (they lie side by side) but not through the ground.
_BEEST_GROUP = 1
_CHASSIS_TYPE = 1


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
class Course:
    """What lies on the ground ahead of the beest, in mm."""
    name: str
    # Each pencil's centre; every pencil is PENCIL_DIAMETER_MM across.
    pencils: tuple[Point, ...] = ()
    # The towel's ends along the ground (left, right), and its surface from right to left.
    towel: tuple[float, float] | None = None
    surface: tuple[Point, ...] = ()
    # A beest is across once every foot is left of this; None when there is nothing to cross.
    finish_x: float | None = None


def lay_course(name: str, start_x: float) -> Course:
    """The course called `name`, starting at x = start_x and running towards −x."""
    if name == "flat":
        return Course(name)
    if name == "pencils":
        radius = PENCIL_DIAMETER_MM / 2
        pencils = tuple((start_x - radius - k * PENCIL_SPACING_MM, radius)
                        for k in range(PENCIL_COUNT))
        return Course(name, pencils=pencils, finish_x=pencils[-1][0] - radius)
    if name == "towel":
        pieces = round(TOWEL_LENGTH_MM / TOWEL_BUMP_SPACING_MM) * TOWEL_PIECES_PER_BUMP
        step = TOWEL_LENGTH_MM / pieces
        phase = 2 * math.pi / TOWEL_PIECES_PER_BUMP
        surface = tuple((start_x - k * step, TOWEL_BUMP_MM / 2 * (1 - math.cos(k * phase)))
                        for k in range(pieces + 1))
        left = start_x - TOWEL_LENGTH_MM
        return Course(name, towel=(left, start_x), surface=surface, finish_x=left)
    raise ValueError(f"there is no course called {name!r}; the courses are {', '.join(COURSES)}")


def _add_ground(space: pymunk.Space, course: Course) -> None:
    ground = space.static_body
    depth = GROUND_DEPTH_MM / 2
    far = GROUND_HALF_LENGTH_MM
    # Stretches of ground (left end, right end, friction), the towel among them. Their round ends
    # meet at the same point, so the surface stays level across each join.
    stretches = [(-far, far, FRICTION)]
    if course.towel is not None:
        left, right = course.towel
        stretches = [(-far, left, FRICTION), (left, right, TOWEL_FRICTION), (right, far, FRICTION)]
    shapes = [(pymunk.Segment(ground, (x0, -depth), (x1, -depth), depth), friction)
              for x0, x1, friction in stretches]
    shapes += [(pymunk.Circle(ground, PENCIL_DIAMETER_MM / 2, centre), PENCIL_FRICTION)
               for centre in course.pencils]
    # The towel's surface, lowered by its half-thickness so its top follows the profile. Each
    # piece knows its neighbours, so nothing catches on the joins.
    line = [(x, y - TOWEL_SURFACE_RADIUS_MM) for x, y in course.surface]
    for k in range(len(line) - 1):
        piece = pymunk.Segment(ground, line[k], line[k + 1], TOWEL_SURFACE_RADIUS_MM)
        piece.set_neighbors(line[max(k - 1, 0)], line[min(k + 2, len(line) - 1)])
        shapes.append((piece, TOWEL_FRICTION))
    for shape, friction in shapes:
        shape.friction = friction
        space.add(shape)


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
    """A beest on the ground, stepped one physics step at a time.

    Building it stands the beest on the ground with the crank held still; each step after that
    turns the crank by 1 / STEPS_PER_TURN of a turn, θ growing as in the brief, so it walks −x.
    The course (one of COURSES) lies ahead of it.
    """

    def __init__(self, genes: list[float], layout: Layout = Layout(), course: str = "flat") -> None:
        lengths = _lengths(genes)
        legs = _starting_legs(lengths, layout)
        self.layout = layout
        box = _chassis_box(lengths)
        front = min([x for leg in legs for x, _ in leg.values()] + [box[0][0]]) - FOOT_RADIUS_MM
        self.course = lay_course(course, front - RUN_UP_MM)
        feet = [leg["F"][1] - FOOT_RADIUS_MM for leg in legs]
        joints = [y - STICK_RADIUS_MM for leg in legs for _, y in leg.values()]
        lift = DROP_MM - min(feet + joints + [box[0][1]])

        def up(p: Point) -> Point:
            return (p[0], p[1] + lift)

        space = pymunk.Space()
        space.gravity = (0.0, -GRAVITY_MM_S2)
        space.iterations = SOLVER_ITERATIONS
        _add_ground(space, self.course)
        own = pymunk.ShapeFilter(group=_BEEST_GROUP)

        def shape(s: pymunk.Shape, mass: float) -> None:
            s.mass, s.friction, s.filter = mass, FRICTION, own
            space.add(s)

        chassis = pymunk.Body()
        space.add(chassis)
        self._box = pymunk.Poly(chassis, [up(p) for p in box])
        self._box.collision_type = _CHASSIS_TYPE
        shape(self._box, CHASSIS_G)
        # Only the ground and what lies on it can touch the chassis.
        self._grounded = False
        space.on_collision(_CHASSIS_TYPE, None, begin=self._chassis_landed)
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
        self._feet = [reads["F"] for reads in self._reads]

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
        if self.tipped_at is None and (tilt > TIP_ANGLE_DEG or self._grounded):
            self.tipped_at = self.turns

    def _chassis_landed(self, arbiter: pymunk.Arbiter, space: pymunk.Space, data: object) -> None:
        self._grounded = True

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
    def steps(self) -> int:
        """Physics steps since the crank started."""
        return self._turning_steps

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

    def feet(self) -> list[Point]:
        """Where every foot is now, in mm, in starting_legs' order."""
        return [(v.x, v.y) for v in (body.local_to_world(local) for body, local in self._feet)]

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


@dataclass(frozen=True)
class RaceResult:
    """How a race turned out."""
    race: str
    # "finished", "fell" (it tipped) or "gave up" (not across after the race's most turns).
    outcome: str
    # Crank turns when the race was decided: the time taken, for a beest that finished.
    turns: float
    # How far the axle moved towards −x, in mm.
    travel: float
    # What happened, in a sentence.
    message: str

    @property
    def finished(self) -> bool:
        return self.outcome == "finished"


# What each race's beest has to get across, in words.
_ACROSS = {"pencils": "the pencils", "towel": "the towel"}


def fell(tipped_at: float) -> str:
    """When a beest fell over, in words: "before the crank started", "after 2.3 turns"."""
    if tipped_at == 0:
        return "before the crank started"
    if round(tipped_at, 1) == 0:
        return "as the crank started"
    return f"after {tipped_at:.1f} turns"


class Race:
    """One of the races, stepped like an Arena until it is decided.

    The distance race lasts DISTANCE_TURNS. The pencils and the towel are decided once every foot
    is past the far end, or after `max_turns`, when the beest gives up. A beest that tips over
    has lost.
    """

    def __init__(self, genes: list[float], layout: Layout = Layout(), race: str = "distance",
                 max_turns: float = MAX_RACE_TURNS) -> None:
        if race not in RACES:
            raise ValueError(f"there is no race called {race!r}; the races are "
                             f"{', '.join(RACES)}")
        self.race = race
        self.max_turns = max_turns
        self.arena = Arena(genes, layout, RACES[race])
        self.result: RaceResult | None = None
        # It may have fallen over while standing still.
        self._decide()

    @property
    def done(self) -> bool:
        return self.result is not None

    def step(self, n: int = 1) -> None:
        """Runs the race on by up to n physics steps, stopping once it is decided."""
        if not isinstance(n, int) or isinstance(n, bool) or n < 0:
            raise ValueError(f"a race steps a whole number of times, 0 or more, not {n!r}")
        arena = self.arena
        while n > 0 and self.result is None:
            batch = min(n, CHECK_STEPS - arena.steps % CHECK_STEPS)
            arena.step(batch)
            n -= batch
            if arena.steps % CHECK_STEPS == 0:
                self._decide()

    def run(self) -> RaceResult:
        """Runs the race to the end."""
        while self.result is None:
            self.step(STEPS_PER_TURN)
        return self.result

    def _decide(self) -> None:
        arena = self.arena
        turns = arena.turns
        if arena.tipped:
            self._end("fell", f"It fell over {fell(arena.tipped_at)}, so it did not finish.")
        elif self.race == "distance":
            if turns >= DISTANCE_TURNS:
                walked = f"{arena.travel:.0f}".replace("-", "\u2212")
                self._end("finished", f"It walked {walked} mm in {DISTANCE_TURNS} turns.")
        elif all(x < arena.course.finish_x for x, _ in arena.feet()):
            self._end("finished", f"It crossed {_ACROSS[self.race]} in {turns:.1f} turns.")
        elif turns >= self.max_turns:
            most = f"{self.max_turns:g} turn{'' if self.max_turns == 1 else 's'}"
            self._end("gave up", f"It was not across {_ACROSS[self.race]} after {most}, so it "
                                 f"did not finish.")

    def _end(self, outcome: str, message: str) -> None:
        arena = self.arena
        self.result = RaceResult(race=self.race, outcome=outcome, turns=arena.turns,
                                 travel=arena.travel, message=message)


def race(genes: list[float], layout: Layout = Layout(), name: str = "distance",
         max_turns: float = MAX_RACE_TURNS) -> RaceResult:
    """Runs the beest these 13 lengths (a to m) describe in the race called `name`."""
    return Race(genes, layout, name, max_turns).run()
