#!/usr/bin/env python3
"""
FORMA — offline tests for reading a floor plan's walls and scale from the
image itself: dimension lines are not walls, and their printed lengths over
their measured span give the plan's scale. Plans are drawn here with Pillow;
no gateway calls.

Run:  python test_plan_scale.py
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app

try:
    from PIL import Image, ImageDraw
except ImportError:                                    # pragma: no cover
    Image = None


def draw_plan(path, thin_wall=True):
    """A 400 x 300 plan: a flat with thick outer walls at x=100/300, y=60/240,
    a thick wall at x=200, a thin interior wall at y=150 (meets the thick
    walls), and a grey dimension line above the flat at y=30 running from
    x=100 to x=300, broken where its numbers sit."""
    img = Image.new("L", (400, 300), 255)
    d = ImageDraw.Draw(img)
    for x in (100, 200, 300):
        d.rectangle([x - 4, 60, x + 4, 240], fill=0)
    for y in (60, 240):
        d.rectangle([100, y - 4, 300, y + 4], fill=0)
    if thin_wall:
        d.rectangle([100, 149, 200, 151], fill=0)
    # The dimension line: grey, with a gap where "3000" is printed, and ticks.
    d.line([100, 30, 180, 30], fill=120)
    d.line([186, 30, 300, 30], fill=120)
    for x in (100, 200, 300):
        d.line([x, 25, x, 35], fill=120)
        d.line([x, 35, x, 56], fill=150)                # extension line to the wall
    img.save(path)


@unittest.skipIf(Image is None, "needs Pillow")
class Walls(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.plan = str(self.tmp / "plan.png")
        draw_plan(self.plan)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_dimension_lines_are_not_walls(self):
        walls = app.detect_plan_walls(self.plan)
        self.assertEqual([round(x) for x in walls["x"]], [100, 200, 300])
        self.assertNotIn(30, [round(y) for y in walls["y"]])
        self.assertIn(60, [round(y) for y in walls["y"]])

    def test_thin_wall_meeting_thick_ones_is_kept(self):
        walls = app.detect_plan_walls(self.plan)
        self.assertIn(150, [round(y) for y in walls["y"]])

    def test_wall_thickness_is_the_walls_not_the_lines(self):
        self.assertGreaterEqual(app.detect_plan_walls(self.plan)["thickness"], 3)

    def test_dimension_line_is_found_end_to_end(self):
        lines = app.detect_plan_walls(self.plan)["dim_lines"]
        top = [l for l in lines if l["axis"] == "h" and abs(l["at"] - 30) <= 2]
        self.assertEqual(len(top), 1)
        self.assertAlmostEqual(top[0]["from"], 100, delta=1)
        self.assertAlmostEqual(top[0]["to"], 300, delta=1)


@unittest.skipIf(Image is None, "needs Pillow")
class Scale(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.plan = str(self.tmp / "plan.png")
        draw_plan(self.plan)
        self.walls = app.detect_plan_walls(self.plan)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_numbers_along_a_line_over_its_span(self):
        # Two 3000 mm spans read loosely — ends 15-20 px out — still give the
        # exact scale: 6000 mm over the line's 200 px.
        sample = app._clean_dimensions([{"mm": 3000, "from": [85, 28], "to": [190, 28]},
                                        {"mm": 3000, "from": [195, 33], "to": [318, 33]}])
        self.assertAlmostEqual(app.scale_from_dimension_lines([sample], self.walls, (400, 300)),
                               0.03, delta=0.0003)

    def test_a_line_read_only_in_part_is_not_used(self):
        # Only one of the two numbers along it: half its length, not all of it.
        sample = app._clean_dimensions([{"mm": 3000, "from": [100, 30], "to": [200, 30]}])
        self.assertIsNone(app.scale_from_dimension_lines([sample], self.walls, (400, 300)))

    def test_each_sample_is_summed_on_its_own(self):
        one = app._clean_dimensions([{"mm": 3000, "from": [100, 30], "to": [200, 30]},
                                     {"mm": 3000, "from": [200, 30], "to": [300, 30]}])
        self.assertAlmostEqual(app.scale_from_dimension_lines([one, one, one], self.walls, (400, 300)),
                               0.03, delta=0.0003)

    def test_trace_uses_it(self):
        reply = {"outline": [[100, 60, 300, 240]], "wall_x": [100, 200, 300], "wall_y": [60, 150, 240],
                 "rooms": [{"name": "Bedroom 2", "label_at": [150, 100], "boxes": [[100, 60, 200, 150]]},
                           {"name": "Kitchen", "label_at": [250, 150], "boxes": [[200, 60, 300, 240]]},
                           {"name": "Bathroom", "label_at": [150, 200], "boxes": [[100, 150, 200, 240]]}],
                 "walkways": [], "furniture_drawn": [],
                 "dimensions": [{"mm": 3000, "from": [100, 30], "to": [200, 30]},
                                {"mm": 3000, "from": [200, 30], "to": [300, 30]}]}
        import json
        with mock.patch.object(app, "call_llm", return_value=json.dumps(reply)):
            geo = app.read_plan_geometry(self.plan, ["Bedroom 2", "Kitchen", "Bathroom"])
        self.assertAlmostEqual(geo["m_per_px_dims"], 0.03, delta=0.0003)
        self.assertGreaterEqual(geo["wall_px"], 3)


class Walkways(unittest.TestCase):
    """Only corridors between rooms are drawn as walkway."""

    def geo(self, walkways):
        box = lambda x, y, w, h: {"x": x, "y": y, "w": w, "h": h}
        return {"image_w": 400, "image_h": 300, "wall_px": 3, "m_per_px": 0.03,
                "rooms": {"Bedroom 2": box(100, 60, 100, 80), "Master Bedroom": box(200, 60, 100, 80),
                          "Bathroom": box(100, 170, 100, 70), "Kitchen": box(200, 170, 100, 70)},
                "walkways": walkways}

    def test_corridor_between_rooms_is_kept(self):
        corridor = {"x": 100, "y": 140, "w": 200, "h": 30}      # rooms above and below
        self.assertEqual(app.tidy_walkways(self.geo([corridor])), [corridor])

    def test_the_part_under_a_room_is_cut_away(self):
        kept = app.tidy_walkways(self.geo([{"x": 100, "y": 120, "w": 200, "h": 50}]))
        self.assertEqual(kept, [{"x": 100, "y": 140, "w": 200, "h": 30}])

    def test_pieces_outside_the_flat_go(self):
        # A notch beside one room, and a ledge below the flat: rooms on one or
        # two neighbouring sides only.
        notch = {"x": 40, "y": 60, "w": 60, "h": 80}
        ledge = {"x": 100, "y": 240, "w": 200, "h": 40}
        self.assertEqual(app.tidy_walkways(self.geo([notch, ledge])), [])

    def test_slivers_go(self):
        self.assertEqual(app.tidy_walkways(self.geo([{"x": 100, "y": 140, "w": 200, "h": 8}])), [])

    def test_drawn_without_outlines_or_stray_shapes(self):
        geo = self.geo([{"x": 40, "y": 60, "w": 60, "h": 80}])
        rooms = [{"label": l, "key": app.room_key(l)} for l in geo["rooms"]]
        svg = app._floor_plan_svg_from_geometry(rooms, geo)
        self.assertNotIn("#EDE8DF", svg)                          # the notch is not drawn
        corridor = self.geo([{"x": 100, "y": 140, "w": 200, "h": 30}])
        self.assertEqual(app._floor_plan_svg_from_geometry(rooms, corridor).count("#EDE8DF"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
