"""Jansen legs and four-bar linkages: circle intersections, joint tracking and jams.

Lengths are in whatever unit the caller uses (mm in the interface, Jansen units in the reference
tests). Angles are in radians unless a name says otherwise; y points up and the crank turns
counter-clockwise as the angle grows.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

Point = tuple[float, float]

# Jansen's holy numbers, in Jansen units (docs/brief.md §2).
HOLY: dict[str, float] = {"a": 38, "b": 41.5, "c": 39.3, "d": 40.1, "e": 55.8, "f": 39.4,
                          "g": 36.7, "h": 65.7, "i": 49, "j": 50, "k": 61.9, "l": 7.8, "m": 15}
LENGTH_NAMES = tuple("abcdefghijklm")

ANGLES = 180
DRAW_ANGLES = 360
JAM_MARGIN_MM = 0.0
# A tracked linkage must come back this close to where it started after one turn.
CLOSURE_MM = 0.5
# Each loop of a figure of eight must be at least this round (4π × area / perimeter², 1 for a
# circle), so the slivers left by sampling a path that doubles back on itself do not count.
FIGURE_EIGHT_MIN_ROUNDNESS = 0.02

# Each moving joint, in solving order: the two circles it lies on (centre joint, radius link) and
# Al's rule for choosing between their intersections at the first angle.
_LEG_JOINTS = (
    ("J2", "C", "j", "G", "b", 1, max),
    ("J3", "G", "d", "J2", "e", 0, min),
    ("J4", "C", "k", "G", "c", 1, min),
    ("J5", "J3", "f", "J4", "g", 0, min),
    ("F", "J4", "i", "J5", "h", 1, min),
)


def circ(p: Point, r1: float, q: Point, r2: float) -> tuple[Point, Point] | None:
    """The two intersections of the circle of radius r1 about p and r2 about q, or None."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    d = math.hypot(dx, dy)
    if d == 0 or d > r1 + r2 or d < abs(r1 - r2):
        return None
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h = math.sqrt(max(r1 * r1 - a * a, 0.0))
    mx, my = p[0] + a * dx / d, p[1] + a * dy / d
    return (mx + h * dy / d, my - h * dx / d), (mx - h * dy / d, my + h * dx / d)


def circle_margin(p: Point, r1: float, q: Point, r2: float) -> float:
    """How far the two circles are from failing to meet; negative when they miss."""
    d = math.dist(p, q)
    return min(r1 + r2 - d, d - abs(r1 - r2))


def _fixed_joints(lengths: dict[str, float], theta: float) -> dict[str, Point]:
    m = lengths["m"]
    return {"O": (0.0, 0.0), "C": (m * math.cos(theta), m * math.sin(theta)),
            "G": (-lengths["a"], -lengths["l"])}


def rule_joints(lengths: dict[str, float], theta: float) -> dict[str, Point] | None:
    """Every joint at one crank angle by Al's rule alone (max-y, min-x and so on), or None."""
    joints = _fixed_joints(lengths, theta)
    for name, p, r1, q, r2, axis, choose in _LEG_JOINTS:
        points = circ(joints[p], lengths[r1], joints[q], lengths[r2])
        if points is None:
            return None
        joints[name] = choose(points, key=lambda pt: pt[axis])
    return joints


@dataclass(frozen=True)
class LegTrace:
    """A leg followed round one turn; `angles` and `joints` stop short at a jam."""
    angles: list[float]
    joints: list[dict[str, Point]]
    jammed: bool
    jam_angle: float | None
    jam_reason: str | None
    closest_to_jam: float
    rule_disagreements: int

    @property
    def foot(self) -> list[Point]:
        return [j["F"] for j in self.joints]


def _nearest(points: tuple[Point, Point], previous: Point) -> Point:
    return min(points, key=lambda pt: math.dist(pt, previous))


def trace_leg(lengths: dict[str, float], n: int = ANGLES, margin: float = JAM_MARGIN_MM) -> LegTrace:
    """Follow a leg round n crank angles as a built leg would move.

    Each joint takes Al's rule at the first angle, then the intersection nearest its previous
    position. A pair of circles closer than `margin` to failing counts as failing.
    """
    angles: list[float] = []
    joints: list[dict[str, Point]] = []
    closest = math.inf
    disagreements = 0

    def result(jam_angle: float | None = None, reason: str | None = None) -> LegTrace:
        return LegTrace(angles, joints, reason is not None, jam_angle, reason, closest, disagreements)

    # The extra angle at 2π checks that the leg comes back to where it started.
    for t in range(n + 1):
        theta = 2 * math.pi * t / n
        here = _fixed_joints(lengths, theta)
        disagrees = False
        for name, p, r1, q, r2, axis, choose in _LEG_JOINTS:
            centre1, radius1, centre2, radius2 = here[p], lengths[r1], here[q], lengths[r2]
            gap = circle_margin(centre1, radius1, centre2, radius2)
            closest = min(closest, gap)
            points = circ(centre1, radius1, centre2, radius2)
            if points is None or gap < margin:
                if t == n:
                    return result(reason="the leg does not come back to where it started")
                return result(theta, f"{r1} and {r2} cannot meet at {round(math.degrees(theta))}°")
            ruled = choose(points, key=lambda pt: pt[axis])
            here[name] = ruled if t == 0 else _nearest(points, joints[-1][name])
            disagrees |= math.dist(here[name], ruled) > 1e-9
        if t == n:
            if any(math.dist(here[name], joints[0][name]) > CLOSURE_MM for name in here):
                return result(reason="the leg does not come back to where it started")
            return result()
        disagreements += disagrees
        angles.append(theta)
        joints.append(here)
    raise AssertionError("unreachable")


def grashof_class(ground: float, crank: float, coupler: float, rocker: float) -> str:
    """Name the four-bar's kind by Grashof's rule (S + L against P + Q) and its shortest link."""
    links = {"ground": ground, "crank": crank, "coupler": coupler, "rocker": rocker}
    ordered = sorted(links.values())
    slack = ordered[1] + ordered[2] - ordered[0] - ordered[3]
    if abs(slack) < 1e-6:
        return "change point"
    if slack < 0:
        return "non-Grashof"
    shortest = min(links, key=links.get)
    return {"ground": "double-crank", "crank": "crank-rocker", "coupler": "double-rocker",
            "rocker": "rocker-crank"}[shortest]


@dataclass(frozen=True)
class FourBarTrace:
    """A four-bar followed round one turn; the point lists stop short at a jam."""
    angles: list[float]
    crank_tip: list[Point]
    coupler_joint: list[Point]
    tracer: list[Point]
    jammed: bool
    jam_angle: float | None
    jam_reason: str | None
    grashof: str
    figure_eight: bool


def trace_four_bar(ground: float, crank: float, coupler: float, rocker: float,
                   along: float = 0.0, offset: float = 0.0, n: int = ANGLES) -> FourBarTrace:
    """Follow a four-bar round n crank angles.

    The crank turns about the origin and the rocker about (ground, 0). The coupler joint starts
    at the higher intersection, then takes the one nearest its previous position. The tracer sits
    `along` from the crank tip towards the coupler joint and `offset` to the left of that line.
    """
    pivot = (ground, 0.0)
    angles: list[float] = []
    tips: list[Point] = []
    couplers: list[Point] = []
    tracer: list[Point] = []
    jam_angle, reason = None, None
    for t in range(n + 1):
        theta = 2 * math.pi * t / n
        tip = (crank * math.cos(theta), crank * math.sin(theta))
        points = circ(tip, coupler, pivot, rocker)
        joint = None
        if points is not None:
            joint = max(points, key=lambda pt: pt[1]) if t == 0 else _nearest(points, couplers[-1])
        if t == n:
            if joint is None or math.dist(joint, couplers[0]) > CLOSURE_MM:
                reason = "the linkage does not come back to where it started"
            break
        if joint is None:
            jam_angle = theta
            reason = f"the coupler and rocker cannot meet at {round(math.degrees(theta))}°"
            break
        ux, uy = (joint[0] - tip[0]) / coupler, (joint[1] - tip[1]) / coupler
        angles.append(theta)
        tips.append(tip)
        couplers.append(joint)
        tracer.append((tip[0] + along * ux - offset * uy, tip[1] + along * uy + offset * ux))
    jammed = reason is not None
    figure_eight = not jammed and self_intersects(tracer, FIGURE_EIGHT_MIN_ROUNDNESS)
    return FourBarTrace(angles, tips, couplers, tracer, jammed, jam_angle, reason,
                        grashof_class(ground, crank, coupler, rocker), figure_eight)


def _orientation(p: Point, q: Point, r: Point) -> float:
    return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])


def _roundness(loop: list[Point]) -> float:
    edges = list(zip(loop, loop[1:] + loop[:1]))
    area = abs(sum(p[0] * q[1] - q[0] * p[1] for p, q in edges)) / 2
    perimeter = sum(math.dist(p, q) for p, q in edges)
    return 4 * math.pi * area / perimeter ** 2 if perimeter else 0.0


def _crossing(q1: Point, q2: Point, o1: float, o2: float) -> Point:
    """Where q1–q2 crosses a line from which q1 and q2 have orientations o1 and o2."""
    s = o1 / (o1 - o2)
    return q1[0] + s * (q2[0] - q1[0]), q1[1] + s * (q2[1] - q1[1])


def self_intersects(path: list[Point], min_roundness: float = 0.0) -> bool:
    """Whether a closed polyline crosses itself; segments sharing a corner do not count.

    A crossing splits the path into two loops; it counts only if each is at least `min_roundness`.
    """
    n = len(path)
    segments = [(path[i], path[(i + 1) % n], i) for i in range(n)]
    # Sweep in order of each segment's left end, so only segments overlapping in x are compared.
    segments.sort(key=lambda s: min(s[0][0], s[1][0]))
    for k, (p1, p2, i) in enumerate(segments):
        right = max(p1[0], p2[0])
        low, high = min(p1[1], p2[1]), max(p1[1], p2[1])
        for q1, q2, j in segments[k + 1:]:
            if min(q1[0], q2[0]) > right:
                break
            if (j - i) % n in (1, n - 1) or max(q1[1], q2[1]) < low or min(q1[1], q2[1]) > high:
                continue
            o1, o2 = _orientation(p1, p2, q1), _orientation(p1, p2, q2)
            if o1 * o2 < 0 and _orientation(q1, q2, p1) * _orientation(q1, q2, p2) < 0:
                first, last = min(i, j), max(i, j)
                x = _crossing(q1, q2, o1, o2)
                inner = [x] + path[first + 1:last + 1]
                outer = [x] + path[last + 1:] + path[:first + 1]
                if min(_roundness(inner), _roundness(outer)) >= min_roundness:
                    return True
    return False
