"""Printable templates: true lengths at 1:1, counts, the chassis holes, and pages that never clip."""
import math
import xml.etree.ElementTree as ET

import pytest

from beest.geometry import LENGTH_NAMES
from beest.leg import MM_PER_UNIT, Layout, jansen_lengths
from beest.template import (PAGE_HEIGHT_MM, PAGE_MARGIN_MM, PAGE_WIDTH_MM, STICK_WIDTH_MM, Chassis,
                            Stick, four_bar_template_svg, leg_template_svg, template_pages,
                            text_width)

NS = "{http://www.w3.org/2000/svg}"
JANSEN = jansen_lengths()
LEG_STICKS = [name for name in LENGTH_NAMES if name not in "al"]
# Descent below the baseline, in ems, as the layout assumes.
DESCENT = 0.3
KNOWN = {"svg", "title", "g", "tspan", "rect", "circle", "line", "text"}
# Coordinates are written to 0.001 mm.
WRITTEN = 1e-3


def genes_with(**lengths):
    named = dict(zip(LENGTH_NAMES, JANSEN)) | lengths
    return [named[name] for name in LENGTH_NAMES]


def parse(pages):
    return [ET.fromstring(page) for page in pages]


def tag(el):
    return el.tag.removeprefix(NS)


def has_class(el, name):
    return name in el.get("class", "").split()


def find_all(root, name):
    return [el for el in root.iter() if has_class(el, name)]


def sticks(roots):
    return [g for root in roots for g in find_all(root, "stick")]


def holes(group):
    return [(float(c.get("cx")), float(c.get("cy"))) for c in find_all(group, "hole")]


def text_of(el):
    return "".join(el.itertext())


def text_box(el):
    runs = list(el.iter(f"{NS}tspan")) or [el]
    width, top_size = 0.0, 0.0
    for run in runs:
        size = float(run.get("font-size") or el.get("font-size"))
        width += float(run.get("dx", 0)) + text_width(run.text or "", size)
        top_size = max(top_size, size)
    x, y = float(el.get("x")), float(el.get("y"))
    left = x - {"start": 0, "middle": width / 2, "end": width}[el.get("text-anchor", "start")]
    return left, y - top_size, left + width, y + DESCENT * top_size


def box(el):
    """The element's extent in viewBox units, ignoring stroke width; None if it draws nothing."""
    match tag(el):
        case "rect":
            x, y = float(el.get("x")), float(el.get("y"))
            return x, y, x + float(el.get("width")), y + float(el.get("height"))
        case "circle":
            cx, cy, r = float(el.get("cx")), float(el.get("cy")), float(el.get("r"))
            return cx - r, cy - r, cx + r, cy + r
        case "line":
            xs = float(el.get("x1")), float(el.get("x2"))
            ys = float(el.get("y1")), float(el.get("y2"))
            return min(xs), min(ys), max(xs), max(ys)
        case "text":
            return text_box(el)
    return None


def union(boxes):
    boxes = list(boxes)
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def group_box(group):
    return union(b for el in group.iter() if (b := box(el)) is not None)


def assert_printable(roots):
    """Every drawn element lies inside its page's margins, so nothing is clipped by a printer."""
    low_x, low_y = PAGE_MARGIN_MM, PAGE_MARGIN_MM
    high_x, high_y = PAGE_WIDTH_MM - PAGE_MARGIN_MM, PAGE_HEIGHT_MM - PAGE_MARGIN_MM
    for number, root in enumerate(roots, 1):
        assert root.get("width") == "210mm" and root.get("height") == "297mm"
        assert root.get("viewBox") == "0 0 210 297"
        assert root.get("data-page") == str(number)
        assert root.get("data-pages") == str(len(roots))
        for el in root.iter():
            assert tag(el) in KNOWN, tag(el)
            if (b := box(el)) is None:
                continue
            assert low_x - WRITTEN <= b[0] and b[2] <= high_x + WRITTEN, (number, tag(el), b)
            assert low_y - WRITTEN <= b[1] and b[3] <= high_y + WRITTEN, (number, tag(el), b)


def assert_blocks_apart(roots):
    """The page's parts (heading, calibration bar, page number, each stick) never overlap."""
    for root in roots:
        blocks = [group_box(el) if tag(el) == "g" else box(el) for el in root if tag(el) != "title"]
        for i, p in enumerate(blocks):
            for q in blocks[i + 1:]:
                apart = (p[2] <= q[0] + WRITTEN or q[2] <= p[0] + WRITTEN
                         or p[3] <= q[1] + WRITTEN or q[3] <= p[1] + WRITTEN)
                assert apart, (p, q)


def chassis_holes(roots):
    [group] = [g for root in roots for g in find_all(root, "chassis")]
    return group, {c.get("data-joint"): (float(c.get("cx")), float(c.get("cy")))
                   for c in find_all(group, "hole")}


@pytest.mark.parametrize("text, ems", [
    ("G", 0.778), ("M", 0.833), ("W", 0.944), ("m", 0.889), ("b", 0.611), ("%", 0.889),
    ("49.8 mm", 3.89),
])
def test_text_estimate_covers_helvetica_bold(text, ems):
    # Advance widths of Helvetica Bold, in ems; Arial's are the same.
    assert text_width(text, 1.0) >= ems


def test_pages_are_a4_at_1_to_1():
    roots = parse(leg_template_svg(JANSEN, Layout()))
    assert roots
    assert_printable(roots)
    assert_blocks_apart(roots)


def test_sticks_true_length():
    by_name = dict(zip(LENGTH_NAMES, JANSEN))
    found = sticks(parse(leg_template_svg(JANSEN, Layout())))
    assert sorted(g.get("data-name") for g in found) == LEG_STICKS
    for g in found:
        name = g.get("data-name")
        p, q = holes(g)
        assert math.dist(p, q) == pytest.approx(by_name[name], abs=1e-3)
        assert float(g.get("data-length")) == pytest.approx(by_name[name], abs=1e-3)
        [length] = find_all(g, "length")
        assert text_of(length) == f"{by_name[name]:.1f} mm"
        [letter] = find_all(g, "letter")
        assert text_of(letter) == name


def test_end_margins():
    for g in sticks(parse(leg_template_svg(JANSEN, Layout()))):
        [outline] = find_all(g, "outline")
        x, y = float(outline.get("x")), float(outline.get("y"))
        width, height = float(outline.get("width")), float(outline.get("height"))
        (x1, y1), (x2, y2) = sorted(holes(g))
        assert x1 - x == pytest.approx(5, abs=1e-3)
        assert x + width - x2 == pytest.approx(5, abs=1e-3)
        assert width == pytest.approx(float(g.get("data-length")) + 10, abs=1e-3)
        assert height == pytest.approx(STICK_WIDTH_MM)
        assert y1 == y2 == pytest.approx(y + height / 2)


def test_calibration_bar():
    roots = parse(template_pages("Test", "Twelve sticks.", [Stick("x", 104.0, 1)] * 12))
    assert len(roots) > 1
    for root in roots:
        [bar_group] = find_all(root, "calibration")
        [bar] = find_all(bar_group, "bar")
        assert float(bar.get("x2")) - float(bar.get("x1")) == pytest.approx(100)
        assert bar.get("y1") == bar.get("y2")
        assert "check it with a ruler" in text_of(bar_group)


@pytest.mark.parametrize("pairs", [1, 2, 3, 4])
def test_counts_follow_pairs(pairs):
    found = sticks(parse(leg_template_svg(JANSEN, Layout(pairs))))
    counts = {g.get("data-name"): int(g.get("data-count")) for g in found}
    assert counts == {name: pairs if name == "m" else 2 * pairs for name in LEG_STICKS}
    for g in found:
        [count] = find_all(g, "count")
        assert text_of(count) == f"make {g.get('data-count')}"


def test_ends_name_the_joints():
    found = {g.get("data-name"): g for g in sticks(parse(leg_template_svg(JANSEN, Layout())))}
    assert found["b"].get("data-ends") == "G J2"
    assert found["m"].get("data-ends") == "O C"
    assert [c.get("data-joint") for c in find_all(found["h"], "hole")] == ["J5", "F"]


def test_overflow_continues_on_next_page():
    roots = parse(template_pages("Overflow", "Fourteen long sticks.",
                                 [Stick(f"s{n}", 104.0, 1) for n in range(14)]))
    assert len(roots) > 1
    assert_printable(roots)
    assert_blocks_apart(roots)
    assert sorted(g.get("data-name") for g in sticks(roots)) == sorted(f"s{n}" for n in range(14))
    for g in sticks(roots):
        p, q = holes(g)
        assert math.dist(p, q) == pytest.approx(104.0, abs=1e-3)


@pytest.mark.parametrize("genes", [
    [10.0] * 13,
    genes_with(l=-30.0),
    genes_with(l=30.0),
    [104.0] * 11 + [30.0, 104.0],
    [104.0] * 11 + [-30.0, 104.0],
], ids=["all-10", "l-negative", "l-30", "all-104", "all-104-l-negative"])
def test_extreme_lengths_still_print(genes):
    roots = parse(leg_template_svg(genes, Layout(4)))
    assert_printable(roots)
    assert_blocks_apart(roots)
    by_name = dict(zip(LENGTH_NAMES, genes))
    found = sticks(roots)
    assert sorted(g.get("data-name") for g in found) == LEG_STICKS
    for g in found:
        p, q = holes(g)
        assert math.dist(p, q) == pytest.approx(by_name[g.get("data-name")], abs=1e-3)
        [letter] = find_all(g, "letter")
        assert text_of(letter) == g.get("data-name")
    _, chassis = chassis_holes(roots)
    a, l = by_name["a"], by_name["l"]
    assert math.dist(chassis["G"], chassis["mirrored-G"]) == pytest.approx(2 * a, abs=1e-3)
    assert math.dist(chassis["O"], chassis["G"]) == pytest.approx(math.hypot(a, l), abs=1e-3)
    assert math.dist(chassis["O"], chassis["mirrored-G"]) == pytest.approx(math.hypot(a, l), abs=1e-3)


def test_short_stick_label_sits_above_it():
    roots = parse(leg_template_svg([10.0] * 13, Layout()))
    for g in sticks(roots):
        [outline] = find_all(g, "outline")
        [label] = find_all(g, "label")
        assert box(label)[3] <= float(outline.get("y"))
        assert float(find_all(label, "letter")[0].get("font-size")) >= 5


@pytest.mark.parametrize("l", [7.8 * MM_PER_UNIT, 0.0, -20.0])
def test_chassis_holes_match_a_and_l(l):
    a = 38 * MM_PER_UNIT
    roots = parse(leg_template_svg(genes_with(a=a, l=l), Layout()))
    group, chassis = chassis_holes(roots)
    assert group.get("data-turned") == "false"
    (ox, oy), (gx, gy), (mx, my) = chassis["O"], chassis["G"], chassis["mirrored-G"]
    # The page's y runs down, so G at (−a, −l) is drawn l below O.
    assert (gx - ox, gy - oy) == pytest.approx((-a, l), abs=1e-3)
    assert (mx - ox, my - oy) == pytest.approx((a, l), abs=1e-3)
    assert float(group.get("data-a")) == pytest.approx(a, abs=1e-3)
    assert float(group.get("data-l")) == pytest.approx(l, abs=1e-3)
    assert f"l = {l:.1f} mm".replace("-", "−") in text_of(group)
    assert "crank axle" in text_of(group)


def test_wide_chassis_turns_to_fit():
    roots = parse(leg_template_svg(genes_with(a=104.0, l=30.0), Layout()))
    group, chassis = chassis_holes(roots)
    assert group.get("data-turned") == "true"
    assert math.dist(chassis["G"], chassis["mirrored-G"]) == pytest.approx(208, abs=1e-3)
    assert_printable(roots)


def apart(p, q, gap):
    return p[2] + gap <= q[0] or q[2] + gap <= p[0] or p[3] + gap <= q[1] or q[3] + gap <= p[1]


# Student code may set a outside its bounds, even to 0.
@pytest.mark.parametrize("a", [-10.0, 0.0, 10.0, 20.0, 30.0, 45.6, 70.0, 104.0])
@pytest.mark.parametrize("l", [-30.0, -10.0, 0.0, 10.0, 30.0])
def test_chassis_labels_stay_clear(a, l):
    # Each hole's label keeps 1 mm from the other labels and from every cross.
    group, _ = chassis_holes(parse(leg_template_svg(genes_with(a=a, l=l), Layout())))
    labels = [text_box(el) for el in find_all(group, "hole-label")]
    crosses = [union(box(el) for el in pair)
               for pair in zip(*[iter(find_all(group, "cross"))] * 2)]
    assert len(labels) == len(crosses) == 3
    for i, p in enumerate(labels):
        assert all(apart(p, q, 1 - WRITTEN) for q in labels[i + 1:]), (p, labels)
        assert all(apart(p, c, 1 - WRITTEN) for c in crosses), (p, crosses)


def test_four_bar_template():
    lengths = {"ground": 40.0, "crank": 15.0, "coupler": 40.0, "rocker": 35.0}
    roots = parse(four_bar_template_svg(*lengths.values()))
    assert_printable(roots)
    assert_blocks_apart(roots)
    found = sticks(roots)
    assert [g.get("data-name") for g in found] == list(lengths)
    for g in found:
        assert g.get("data-count") == "1"
        p, q = holes(g)
        assert math.dist(p, q) == pytest.approx(lengths[g.get("data-name")], abs=1e-3)
    assert not any(find_all(root, "chassis") for root in roots)
    assert "Four-bar" in text_of(roots[0])


def test_text_is_escaped():
    [root] = parse(template_pages("Tom & Jerry's <leg>", "a < b", [Stick("<b>", 20.0, 1)]))
    [g] = sticks([root])
    assert g.get("data-name") == "<b>"
    assert text_of(find_all(g, "letter")[0]) == "<b>"
    assert "Tom & Jerry's <leg>" in text_of(root)


def test_chassis_without_sticks():
    roots = parse(template_pages("Frame", "Holes only.", [], Chassis(45.6, 9.36)))
    assert len(roots) == 1
    assert_printable(roots)
    assert set(chassis_holes(roots)[1]) == {"O", "G", "mirrored-G"}


@pytest.mark.parametrize("call", [
    lambda: leg_template_svg(JANSEN[:12], Layout()),
    lambda: leg_template_svg(genes_with(h=300.0), Layout()),
    lambda: leg_template_svg(genes_with(a=200.0), Layout()),
    lambda: leg_template_svg(genes_with(b=0.0), Layout()),
    lambda: leg_template_svg(genes_with(c=math.nan), Layout()),
    lambda: four_bar_template_svg(40.0, -15.0, 40.0, 35.0),
], ids=["twelve-genes", "too-long", "chassis-too-wide", "zero-stick", "nan", "negative"])
def test_unprintable_input_raises(call):
    with pytest.raises(ValueError):
        call()
