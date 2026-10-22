"""Throwaway spike from scoping: timing of leg geometry and a pymunk beest, in CPython or Pyodide.

Not product code. It uses Al's selection rule without continuity tracking, and numpy, which the
product does not. What it shows: a six-legged beest walks 142-145 mm per turn at 600 steps per turn
(the kinematic model says 141.8), the two-legged one tips over, 240 steps per turn falls apart, and
results are identical in CPython and the browser. A positive SimpleMotor rate turns the crank
clockwise (theta decreasing), so the beest walks +x; Al's convention of theta increasing walks -x.
"""
import math
import time

import numpy as np
import pymunk

HOLY = dict(a=38, b=41.5, c=39.3, d=40.1, e=55.8, f=39.4, g=36.7, h=65.7,
            i=49, j=50, k=61.9, l=7.8, m=15)


# ---------- geometry, pure Python ----------
def circ(P, r1, Q, r2):
    dx, dy = Q[0] - P[0], Q[1] - P[1]
    D = math.hypot(dx, dy)
    if D == 0 or D > r1 + r2 or D < abs(r1 - r2):
        return None
    a = (r1 * r1 - r2 * r2 + D * D) / (2 * D)
    h = math.sqrt(max(r1 * r1 - a * a, 0.0))
    mx, my = P[0] + a * dx / D, P[1] + a * dy / D
    return ((mx + h * dy / D, my - h * dx / D), (mx - h * dy / D, my + h * dx / D))


def joints(L, th):
    C = (L['m'] * math.cos(th), L['m'] * math.sin(th))
    G = (-L['a'], -L['l'])
    s = circ(C, L['j'], G, L['b'])
    if not s: return None
    J2 = max(s, key=lambda p: p[1])
    s = circ(G, L['d'], J2, L['e'])
    if not s: return None
    J3 = min(s, key=lambda p: p[0])
    s = circ(C, L['k'], G, L['c'])
    if not s: return None
    J4 = min(s, key=lambda p: p[1])
    s = circ(J3, L['f'], J4, L['g'])
    if not s: return None
    J5 = min(s, key=lambda p: p[0])
    s = circ(J4, L['i'], J5, L['h'])
    if not s: return None
    F = min(s, key=lambda p: p[1])
    return dict(C=C, G=G, J2=J2, J3=J3, J4=J4, J5=J5, F=F)


# ---------- geometry, numpy over all crank angles at once ----------
def circ_np(Px, Py, r1, Qx, Qy, r2):
    dx, dy = Qx - Px, Qy - Py
    D = np.hypot(dx, dy)
    ok = (D > 0) & (D <= r1 + r2) & (D >= abs(r1 - r2))
    a = (r1 * r1 - r2 * r2 + D * D) / (2 * D)
    h = np.sqrt(np.clip(r1 * r1 - a * a, 0, None))
    mx, my = Px + a * dx / D, Py + a * dy / D
    return ok, (mx + h * dy / D, my - h * dx / D), (mx - h * dy / D, my + h * dx / D)


def pick(p1, p2, axis, want_max):
    v1, v2 = p1[axis], p2[axis]
    first = v1 >= v2 if want_max else v1 <= v2
    return np.where(first, p1[0], p2[0]), np.where(first, p1[1], p2[1])


def foot_np(L, th):
    Cx, Cy = L['m'] * np.cos(th), L['m'] * np.sin(th)
    Gx, Gy = np.full_like(th, -L['a']), np.full_like(th, -L['l'])
    ok1, p, q = circ_np(Cx, Cy, L['j'], Gx, Gy, L['b']); J2 = pick(p, q, 1, True)
    ok2, p, q = circ_np(Gx, Gy, L['d'], *J2, L['e']);    J3 = pick(p, q, 0, False)
    ok3, p, q = circ_np(Cx, Cy, L['k'], Gx, Gy, L['c']); J4 = pick(p, q, 1, False)
    ok4, p, q = circ_np(*J3, L['f'], *J4, L['g']);       J5 = pick(p, q, 0, False)
    ok5, p, q = circ_np(*J4, L['i'], *J5, L['h']);       F = pick(p, q, 1, False)
    return ok1 & ok2 & ok3 & ok4 & ok5, F


def time_geometry(log, reps=200):
    n = 180
    t0 = time.perf_counter()
    for _ in range(reps):
        for t in range(n):
            joints(HOLY, 2 * math.pi * t / n)
    py_ms = (time.perf_counter() - t0) / reps * 1000
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    t0 = time.perf_counter()
    for _ in range(reps):
        foot_np(HOLY, th)
    np_ms = (time.perf_counter() - t0) / reps * 1000
    log(f"one leg, 180 angles: pure Python {py_ms:.2f} ms, numpy {np_ms:.3f} ms")
    for pop, gens in ((50, 100), (200, 200)):
        log(f"  GA {pop}x{gens} (x2 for mirror re-use is free): "
            f"pure {pop * gens * py_ms / 1000:.1f} s, numpy {pop * gens * np_ms / 1000:.1f} s")


# ---------- pymunk beest ----------
def build_beest(L, phases, foot_r=2.0, iterations=30):
    space = pymunk.Space()
    space.gravity = (0, -9810)          # mm/s^2
    space.iterations = iterations
    legs = []
    for ph in phases:
        J = joints(L, ph)
        legs.append(J)
        Jm = joints(L, math.pi - ph)
        legs.append({k: (-x, y) for k, (x, y) in Jm.items()})
    y0 = -min(J['F'][1] for J in legs) + foot_r + 0.5

    def up(p):
        return (p[0], p[1] + y0)

    ground = pymunk.Segment(space.static_body, (-20000, 0), (20000, 0), 1)
    ground.friction = 1.0
    space.add(ground)

    nocollide = pymunk.ShapeFilter(group=1)
    chassis = pymunk.Body()
    box = pymunk.Poly(chassis, [up((-L['a'] - 5, -L['l'] - 5)), up((L['a'] + 5, -L['l'] - 5)),
                                up((L['a'] + 5, 10)), up((-L['a'] - 5, 10))])
    box.mass, box.filter = 60, nocollide
    space.add(chassis, box)

    crank = pymunk.Body()
    disc = pymunk.Circle(crank, L['m'] + 2, up((0, 0)))
    disc.mass, disc.filter = 5, nocollide
    motor = pymunk.SimpleMotor(chassis, crank, 0)
    space.add(crank, disc, pymunk.PivotJoint(chassis, crank, up((0, 0))), motor)

    def bar(p, q, mass=1.0):
        b = pymunk.Body()
        s = pymunk.Segment(b, up(p), up(q), 1.0)
        s.mass, s.filter = mass, nocollide
        space.add(b, s)
        return b

    def tri(p, q, r, mass=2.0):
        b = pymunk.Body()
        s = pymunk.Poly(b, [up(p), up(q), up(r)])
        s.mass, s.filter = mass, nocollide
        space.add(b, s)
        return b, s

    def pin(b1, b2, p):
        space.add(pymunk.PivotJoint(b1, b2, up(p)))

    feet = []
    for J in legs:
        j, k = bar(J['C'], J['J2']), bar(J['C'], J['J4'])
        top, _ = tri(J['G'], J['J2'], J['J3'])
        c, f = bar(J['G'], J['J4']), bar(J['J3'], J['J5'])
        bot, _ = tri(J['J4'], J['J5'], J['F'])
        toe = pymunk.Circle(bot, foot_r, up(J['F']))
        toe.mass, toe.friction = 0.2, 1.0
        toe.filter = pymunk.ShapeFilter(group=1)   # legs ignore each other, not the ground
        space.add(toe)
        pin(crank, j, J['C']); pin(crank, k, J['C'])
        pin(j, top, J['J2']); pin(chassis, top, J['G']); pin(chassis, c, J['G'])
        pin(top, f, J['J3']); pin(k, bot, J['J4']); pin(c, bot, J['J4']); pin(f, bot, J['J5'])
        feet.append(toe)
    return space, chassis, crank, motor


def run_beest(log, phases, turns=10, dt=1 / 600, rate=2 * math.pi, iterations=30):
    space, chassis, crank, motor = build_beest(HOLY, phases, iterations=iterations)
    for _ in range(300):                     # settle onto the ground, motor holding still
        space.step(dt)
    x0, a0 = chassis.position.x, crank.angle - chassis.angle
    motor.rate = rate
    steps = int(turns * 2 * math.pi / rate / dt)
    t0 = time.perf_counter()
    for _ in range(steps):
        space.step(dt)
    wall = time.perf_counter() - t0
    dturns = (crank.angle - chassis.angle - a0) / (2 * math.pi)
    dx = chassis.position.x - x0
    log(f"{len(phases)} pair(s), {len(space.bodies)} bodies, {len(space.constraints)} joints, "
        f"iter {iterations}: {steps} steps in {wall:.2f} s ({steps / wall:.0f} steps/s); "
        f"crank turned {dturns:+.2f}, body moved {dx:+.1f} mm = {dx / dturns:+.1f} per turn; "
        f"body tilt {math.degrees(chassis.angle):+.1f} deg")


def main(log=print):
    log(f"pymunk {pymunk.version}, numpy {np.__version__}")
    time_geometry(log)
    run_beest(log, [0])
    run_beest(log, [0, math.pi])
    run_beest(log, [0, 2 * math.pi / 3, 4 * math.pi / 3])
    run_beest(log, [0, 2 * math.pi / 3, 4 * math.pi / 3], iterations=10)
    run_beest(log, [0, 2 * math.pi / 3, 4 * math.pi / 3], dt=1 / 240, iterations=10)


if __name__ == "__main__":
    main()
