"""Example project: an L bracket with two M3 holes and a nut pocket."""
from hexcad import feature
from hexcad.shapes import bx, color, cyl, part, prism, rbx

M3 = 3.2


@feature
def bracket():
    base = rbx([0, 0, 0], [40, 20, 4], [3, 3, 3, 3])
    wall = bx([0, 0, 0], [4, 20, 30])
    holes = [cyl([x, 10, -1], [x, 10, 5], M3 / 2) for x in (15, 32)]
    holes.append(cyl([-1, 10, 20], [5, 10, 20], M3 / 2))
    part("L bracket", [base, wall], holes, color(0.12, 0.30, 0.75))


@feature
def washer():
    rib = prism([0, 0, 0], [0, 0, 1], [1, 0, 0], [[50, 0], [60, 0], [55, 8]], 2)
    part("Rib", [rib], [], color(0.85, 0.65, 0.13))
