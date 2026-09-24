#!/usr/bin/env python3
"""
FORMA — offline tests for the floor plan trace (app.read_plan_geometry and the
drawings built from it). No gateway calls: the model's reply is a fixture,
traced by hand from a real 2-bedroom HDB plan (700 x 467 px).

Run:  python test_plan_geometry.py
"""

import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

import app

LABELS = ["Living / Dining", "Bedroom 2", "Master Bedroom", "Kitchen",
          "Master Bathroom", "Common Bathroom", "Service Yard", "Household Shelter"]

# What a good trace of the sample plan looks like, in the 0-1000 format the
# prompt asks for.
GOOD_REPLY = {
    "rooms": [
        # L-shaped: the living area, and the dining area stepping out below
        # it towards the kitchen.
        {"name": "Living / Dining", "boxes": [[281, 278, 436, 606], [436, 407, 529, 493]]},
        {"name": "Bedroom 2", "box": [440, 214, 579, 407]},
        {"name": "Master Bedroom", "box": [579, 214, 714, 493]},
        {"name": "Kitchen", "boxes": [[436, 493, 521, 760]]},
        {"name": "Master Bathroom", "box": [621, 493, 714, 600]},
        {"name": "Common Bathroom", "box": [529, 493, 621, 600]},
        {"name": "Service Yard", "box": [521, 600, 586, 760]},
        {"name": "Household Shelter", "box": [281, 606, 364, 685]},
    ],
    "missing": [],
}
SIZE = (700, 467)


def _closed(reply: dict) -> dict:
    out = json.loads(json.dumps(reply))
    for r in out["rooms"]:
        r["boxes"] = r.pop("boxes", None) or [r.pop("box")]
    return app._close_gaps(out)


def _in_pixels(reply: dict) -> dict:
    """The fixture as the model now sends it: boxes in image pixels."""
    out = json.loads(json.dumps(reply))
    for r in out["rooms"]:
        boxes = r.pop("boxes", None) or [r.pop("box")]
        r["boxes"] = [[b[0] * SIZE[0] / 1000, b[1] * SIZE[1] / 1000,
                       b[2] * SIZE[0] / 1000, b[3] * SIZE[1] / 1000] for b in boxes]
    return out


def _png(path: Path, w: int, h: int):
    """A minimal valid PNG of the given size."""
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + b"\xff" * (w * 3) for _ in range(h))
    path.write_bytes(b"\x89PNG\r\n\x1a\n"
                     + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw))
                     + chunk(b"IEND", b""))


class ParseTrace(unittest.TestCase):

    def test_good_trace_is_kept_in_pixels(self):
        g = app.parse_plan_geometry(GOOD_REPLY, LABELS, SIZE)
        self.assertEqual(set(g["rooms"]), set(LABELS))
        self.assertEqual(g["missing"], [])
        kitchen = g["rooms"]["Kitchen"]
        self.assertAlmostEqual(kitchen["x"], 436 / 1000 * 700)
        self.assertAlmostEqual(kitchen["h"], (760 - 493) / 1000 * 467)

    def test_unknown_and_duplicate_rooms_are_dropped(self):
        reply = json.loads(json.dumps(GOOD_REPLY))
        reply["rooms"].append({"name": "Balcony", "box": [0, 0, 100, 100]})
        reply["rooms"].append({"name": "kitchen", "box": [0, 0, 100, 100]})
        g = app.parse_plan_geometry(reply, LABELS, SIZE)
        self.assertNotIn("Balcony", g["rooms"])
        self.assertAlmostEqual(g["rooms"]["Kitchen"]["x"], 436 / 1000 * 700)

    def test_names_match_despite_case_and_spacing(self):
        reply = json.loads(json.dumps(GOOD_REPLY))
        reply["rooms"][0]["name"] = "living  /  dining".replace("  ", " ")
        g = app.parse_plan_geometry(reply, LABELS, SIZE)
        self.assertIn("Living / Dining", g["rooms"])

    def test_missing_rooms_are_reported(self):
        reply = json.loads(json.dumps(GOOD_REPLY))
        reply["rooms"] = reply["rooms"][:6]
        g = app.parse_plan_geometry(reply, LABELS, SIZE)
        self.assertEqual(g["missing"], ["Service Yard", "Household Shelter"])

    def test_too_few_rooms_is_a_failed_read(self):
        reply = {"rooms": GOOD_REPLY["rooms"][:3]}
        with self.assertRaises(ValueError):
            app.parse_plan_geometry(reply, LABELS, SIZE)

    def test_stacked_boxes_are_a_failed_read(self):
        reply = json.loads(json.dumps(GOOD_REPLY))
        for r in reply["rooms"]:
            r["box"] = [100, 100, 900, 900]
        with self.assertRaises(ValueError):
            app.parse_plan_geometry(reply, LABELS, SIZE)

    def test_slivers_are_dropped(self):
        reply = json.loads(json.dumps(GOOD_REPLY))
        reply["rooms"][7]["box"] = [281, 606, 290, 685]
        g = app.parse_plan_geometry(reply, LABELS, SIZE)
        self.assertIn("Household Shelter", g["missing"])


class Shapes(unittest.TestCase):
    """Rooms made of more than one rectangle."""

    def setUp(self):
        self.geo = app.parse_plan_geometry(GOOD_REPLY, LABELS, SIZE)

    def test_l_shape_keeps_both_parts(self):
        living = self.geo["rooms"]["Living / Dining"]
        self.assertEqual(len(living["parts"]), 2)
        # The room's box is the bounding box of its parts.
        self.assertAlmostEqual(living["x"] + living["w"], 529 / 1000 * 700)

    def test_outline_skips_the_seam(self):
        parts = [{"x": 0, "y": 0, "w": 10, "h": 10}, {"x": 10, "y": 5, "w": 5, "h": 5}]
        d = app.union_outline(parts)
        # The shared edge x=10 from y=5 to y=10 is inside the room.
        self.assertNotIn("M10.0,5.0L10.0,10.0", d)
        self.assertIn("M10.0,0.0L10.0,5.0", d)      # the step of the L is a wall
        self.assertAlmostEqual(app.union_area(parts), 125)

    def test_split_finds_the_widest_rectangle(self):
        # A strip plus a block beside it: together a 6 x 5 rectangle with a
        # notch — the strip alone is only 2 wide.
        parts = [{"x": 0, "y": 0, "w": 2, "h": 6}, {"x": 2, "y": 1, "w": 4, "h": 5}]
        rects = app.split_into_rects(parts)
        self.assertEqual(rects[0], {"x": 0, "y": 1, "w": 6, "h": 5})
        self.assertAlmostEqual(sum(r["w"] * r["h"] for r in rects), app.union_area(parts))

    def test_split_prefers_a_usable_block_to_a_long_strip(self):
        # 1.7 x 7.1 strip beside a 1.5 x 3.6 block: the strip is bigger, but
        # the 3.2 x 3.6 they make together holds far more furniture.
        parts = [{"x": 0, "y": 0, "w": 1.7, "h": 7.1}, {"x": 1.7, "y": 0, "w": 1.5, "h": 3.6}]
        best = app.split_into_rects(parts, wide=3.0)[0]
        self.assertAlmostEqual(best["w"], 3.2)
        self.assertAlmostEqual(best["h"], 3.6)

    def test_split_of_a_rectangle_is_itself(self):
        r = {"x": 1, "y": 2, "w": 3, "h": 4}
        self.assertEqual(app.split_into_rects([r]), [r])

    def test_overlapping_parts_count_once(self):
        parts = [{"x": 0, "y": 0, "w": 10, "h": 10}, {"x": 5, "y": 0, "w": 10, "h": 10}]
        self.assertAlmostEqual(app.union_area(parts), 150)

    def test_near_edges_snap_together(self):
        reply = {"rooms": [{"name": l, "boxes": [[i * 100, 0, i * 100 + 90, 90]]}
                           for i, l in enumerate(LABELS)]}
        reply["rooms"][0]["boxes"] = [[0, 0, 90, 90], [95, 40, 160, 88]]
        reply["rooms"][1]["boxes"] = [[500, 500, 590, 590]]
        g = app.parse_plan_geometry(reply, LABELS, (1000, 1000))
        a, b = g["rooms"][LABELS[0]]["parts"]
        self.assertEqual(a["x"] + a["w"], b["x"])   # 90 and 95 joined
        self.assertEqual(a["y"] + a["h"], b["y"] + b["h"])

    def test_l_shape_dimension_is_an_area(self):
        m = app.plan_metres_per_px(self.geo, 67)
        self.assertIn("m²", app._dims_text(self.geo["rooms"]["Living / Dining"], m))
        self.assertIn(" × ", app._dims_text(self.geo["rooms"]["Kitchen"], m))

    def test_trace_saved_before_parts_still_draws(self):
        old = {"rooms": {l: {k: v for k, v in r.items() if k != "parts"}
                         for l, r in self.geo["rooms"].items()}, "missing": []}
        rooms = [{"label": l, "items": []} for l in LABELS]
        svg = app.generate_floor_plan_svg(rooms, geometry=old)
        self.assertIn("approximate", svg)


class OpenPlan(unittest.TestCase):
    """The live model gave Living / Dining one box over the whole open area,
    kitchen and bedroom corner included. This is that reply, in pixels."""

    LIVE = {"rooms": [
        {"name": "Living / Dining", "boxes": [[203, 142, 399, 339], [198, 136, 267, 211]]},
        {"name": "Bedroom 2", "boxes": [[312, 105, 411, 211]]},
        {"name": "Master Bedroom", "boxes": [[411, 99, 503, 224]]},
        {"name": "Kitchen", "boxes": [[303, 244, 372, 361]]},
        {"name": "Master Bathroom", "boxes": [[424, 224, 503, 276]]},
        {"name": "Common Bathroom", "boxes": [[374, 231, 424, 283]]},
        {"name": "Service Yard", "boxes": [[374, 283, 424, 355]]},
        {"name": "Household Shelter", "boxes": [[198, 270, 248, 316]]},
    ], "missing": []}

    def setUp(self):
        self.geo = app.parse_plan_geometry(app._pixels_to_permille(json.loads(json.dumps(self.LIVE)), SIZE),
                                           LABELS, SIZE)

    def test_live_reply_is_accepted(self):
        self.assertEqual(self.geo["missing"], [])

    def test_living_no_longer_covers_other_rooms(self):
        living = self.geo["rooms"]["Living / Dining"]["parts"]
        for label, room in self.geo["rooms"].items():
            if label == "Living / Dining":
                continue
            inter = (app.union_area(living) + app.union_area(room["parts"])
                     - app.union_area(living + room["parts"]))
            self.assertLess(inter, 1.0, label)

    def test_living_is_one_connected_shape(self):
        living = self.geo["rooms"]["Living / Dining"]["parts"]
        self.assertEqual(len(app._connected_to_largest(living)), len(living))

    def test_rect_minus(self):
        r = {"x": 0, "y": 0, "w": 10, "h": 10}
        pieces = app._rect_minus(r, {"x": 3, "y": 3, "w": 4, "h": 4})
        self.assertAlmostEqual(sum(p["w"] * p["h"] for p in pieces), 84)
        self.assertEqual(app._rect_minus(r, {"x": 20, "y": 0, "w": 5, "h": 5}), [r])


class PieceTogether(unittest.TestCase):

    def test_small_gap_between_neighbours_closes(self):
        data = {"rooms": [{"name": "A", "boxes": [[100, 100, 300, 300]]},
                          {"name": "B", "boxes": [[320, 120, 500, 280]]}]}
        out = app._close_gaps(data)
        self.assertEqual(out["rooms"][0]["boxes"][0][2], 320)   # A's right edge meets B

    def test_wide_gap_is_left(self):
        data = {"rooms": [{"name": "A", "boxes": [[100, 100, 300, 300]]},
                          {"name": "B", "boxes": [[400, 100, 500, 300]]}]}
        out = app._close_gaps(json.loads(json.dumps(data)))
        self.assertEqual(out, data)

    def test_rooms_not_side_by_side_are_left(self):
        # B is right of A but entirely below it — they do not face each other.
        data = {"rooms": [{"name": "A", "boxes": [[100, 100, 300, 300]]},
                          {"name": "B", "boxes": [[310, 400, 500, 500]]}]}
        out = app._close_gaps(json.loads(json.dumps(data)))
        self.assertEqual(out, data)

    def test_parts_of_one_room_do_not_pull_each_other(self):
        data = {"rooms": [{"name": "A", "boxes": [[100, 100, 300, 300], [310, 100, 400, 200]]}]}
        out = app._close_gaps(json.loads(json.dumps(data)))
        self.assertEqual(out, data)


class WalkwaysAndScale(unittest.TestCase):

    def _reply(self, walkways=(), refs=()):
        r = json.loads(json.dumps(GOOD_REPLY))
        r["walkways"] = list(walkways)
        r["furniture_drawn"] = list(refs)
        return app._normalise_trace(r)

    def test_walkway_is_kept_and_rooms_win_overlaps(self):
        # A hallway between the bedrooms and the bathrooms, drawn a little
        # into Bedroom 2.
        d = self._reply(walkways=[[436, 400, 621, 493]])
        g = app.parse_plan_geometry(d, LABELS, SIZE)
        self.assertTrue(g["walkways"])
        bed2 = g["rooms"]["Bedroom 2"]["parts"]
        for w in g["walkways"]:
            for p in bed2:
                ix = min(w["x"] + w["w"], p["x"] + p["w"]) - max(w["x"], p["x"])
                iy = min(w["y"] + w["h"], p["y"] + p["h"]) - max(w["y"], p["y"])
                self.assertFalse(ix > 0.5 and iy > 0.5)

    def test_wide_walkway_by_the_living_room_is_its_floor(self):
        # A big "walkway" beside Living / Dining — the open plan, mislabelled.
        d = self._reply(walkways=[[140, 278, 281, 606]])
        g = app.parse_plan_geometry(d, LABELS, SIZE)
        self.assertEqual(g["walkways"], [])
        living = g["rooms"]["Living / Dining"]
        self.assertAlmostEqual(living["x"], 140 / 1000 * 700, places=3)

    def test_narrow_corridor_stays_a_walkway(self):
        d = self._reply(walkways=[[436, 407, 621, 440]])      # long and thin
        g = app.parse_plan_geometry(d, LABELS, SIZE)
        self.assertEqual(len(g["walkways"]), 1)

    def test_walkway_inside_a_room_disappears(self):
        d = self._reply(walkways=[[450, 250, 560, 390]])        # inside Bedroom 2
        g = app.parse_plan_geometry(d, LABELS, SIZE)
        self.assertEqual(g["walkways"], [])

    def test_walkways_are_drawn_unlabelled(self):
        d = self._reply(walkways=[[436, 407, 621, 493]])
        g = app.parse_plan_geometry(d, LABELS, SIZE)
        svg = app.generate_floor_plan_svg([{"label": l, "items": []} for l in LABELS], geometry=g)
        self.assertIn('fill="#E6E0D5"', svg)
        self.assertNotIn("Walkway", svg)

    def test_scale_read_off_a_drawn_bed(self):
        # A 1.52 x 2.0 m bed drawn 38 x 50 px: 0.04 m per pixel.
        d = self._reply(refs=[{"type": "double bed", "box": [500, 250, 538 / 700 * 1000, 350]}])
        # Box in 0-1000 units: convert the intended pixels to that scale.
        d["refs"][0]["box"] = [500, 250, 500 + 38 / 700 * 1000, 250 + 50 / 467 * 1000]
        g = app.parse_plan_geometry(d, LABELS, SIZE)
        self.assertAlmostEqual(g["m_per_px_ref"], 0.04, places=3)

    def test_unknown_or_implausible_references_are_ignored(self):
        d = self._reply(refs=[{"type": "piano", "box": [0, 0, 100, 100]}])
        self.assertIsNone(app.parse_plan_geometry(d, LABELS, SIZE)["m_per_px_ref"])
        # A "bed" 2 px long would make the flat thousands of square metres.
        d = self._reply(refs=[{"type": "double bed", "box": [0, 0, 3, 5]}])
        self.assertIsNone(app.parse_plan_geometry(d, LABELS, SIZE)["m_per_px_ref"])

    def test_references_move_with_the_fitted_layout(self):
        from PIL import Image, ImageDraw
        import tempfile as _t
        tmp = _t.TemporaryDirectory()
        plan = Path(tmp.name) / "w.png"
        img = Image.new("RGB", (600, 400), "white")
        ImageDraw.Draw(img).rectangle([100, 50, 500, 350], outline="black", width=6)
        img.save(plan)
        walls = app.detect_plan_walls(str(plan))
        data = {"rooms": [{"name": "A", "boxes": [[50, 50, 450, 400]]}],
                "walkways": [], "refs": [{"type": "double bed", "box": [50, 50, 150, 150]}]}
        out = app.align_to_walls(data, walls, (600, 400))
        room, ref = out["rooms"][0]["boxes"][0], out["refs"][0]["box"]
        self.assertAlmostEqual(ref[0], room[0], places=6)       # moved with the room
        tmp.cleanup()


class Doors(unittest.TestCase):

    def _reply(self):
        r = json.loads(json.dumps(GOOD_REPLY))
        r["rooms"][3]["doors"] = [{"box": 0, "wall": "top", "at": 500}]          # Kitchen
        r["rooms"][1]["doors"] = [{"box": 0, "wall": "bottom", "at": 850},       # Bedroom 2
                                  {"box": 9, "wall": "north", "at": 10}]          # malformed
        return app._normalise_trace(r)

    def test_doors_are_parsed_and_bad_ones_dropped(self):
        g = app.parse_plan_geometry(self._reply(), LABELS, SIZE)
        # The model's own door first; the yard door the kitchen gains by
        # convention comes after it.
        self.assertEqual(g["rooms"]["Kitchen"]["doors"][0], {"wall": "top", "at": 0.5, "part": 0})
        self.assertEqual(len(g["rooms"]["Bedroom 2"]["doors"]), 1)

    def test_prompt_asks_for_doors_not_windows(self):
        import tempfile as _t
        tmp = _t.TemporaryDirectory()
        plan = Path(tmp.name) / "p.png"
        _png(plan, *SIZE)
        seen, real = [], app.call_llm
        app.call_llm = lambda m, **kw: (seen.append(m[0]["content"]), json.dumps(_in_pixels(GOOD_REPLY)))[1]
        try:
            app.read_plan_geometry(str(plan), LABELS)
        finally:
            app.call_llm = real
            tmp.cleanup()
        self.assertIn('"doors"', seen[0])
        self.assertIn("Ignore windows", seen[0])
        self.assertNotIn('"windows"', seen[0])

    def test_door_follows_the_carve(self):
        rooms = {
            "Living": {"x": 0, "y": 0, "w": 100, "h": 100,
                       "parts": [{"x": 0, "y": 0, "w": 100, "h": 100}],
                       "doors": [{"part": 0, "wall": "left", "at": 0.8}]},
            "Kitchen": {"x": 60, "y": 0, "w": 40, "h": 40,
                        "parts": [{"x": 60, "y": 0, "w": 40, "h": 40}], "doors": []},
        }
        app._carve_open_plan(rooms)
        living = rooms["Living"]
        self.assertEqual(len(living["doors"]), 1)
        door = living["doors"][0]
        x, y = app.door_point(living["parts"][door["part"]], door)
        self.assertAlmostEqual((x, y)[0], 0)
        self.assertAlmostEqual((x, y)[1], 80)

    def test_en_suite_gets_a_door_from_its_bedroom(self):
        # Neither room reported the door they share (fixture: master bedroom
        # sits directly above the master bathroom).
        g = app.parse_plan_geometry(self._reply(), LABELS, SIZE)
        bath, bed = g["rooms"]["Master Bathroom"], g["rooms"]["Master Bedroom"]
        self.assertIn("top", [d["wall"] for d in bath["doors"]])
        self.assertIn("bottom", [d["wall"] for d in bed["doors"]])
        # Both ends are the same point on the plan.
        bp = app.door_point(app.room_parts(bath)[0], next(d for d in bath["doors"] if d["wall"] == "top"))
        dp = app.door_point(app.room_parts(bed)[0], next(d for d in bed["doors"] if d["wall"] == "bottom"))
        self.assertAlmostEqual(bp[0], dp[0], delta=1.5)
        self.assertAlmostEqual(bp[1], dp[1], delta=1.5)

    def test_existing_en_suite_door_is_left_alone(self):
        r = json.loads(json.dumps(GOOD_REPLY))
        r["rooms"][4]["doors"] = [{"box": 0, "wall": "top", "at": 300}]       # Master Bathroom
        g = app.parse_plan_geometry(app._normalise_trace(r), LABELS, SIZE)
        self.assertEqual(g["rooms"]["Master Bathroom"]["doors"],
                         [{"wall": "top", "at": 0.3, "part": 0}])

    def test_service_yard_opens_from_the_kitchen(self):
        g = app.parse_plan_geometry(self._reply(), LABELS, SIZE)
        self.assertIn("left", [d["wall"] for d in g["rooms"]["Service Yard"]["doors"]])

    def test_prompt_describes_how_doors_are_drawn(self):
        import tempfile as _t
        tmp = _t.TemporaryDirectory()
        plan = Path(tmp.name) / "p.png"
        _png(plan, *SIZE)
        seen, real = [], app.call_llm
        app.call_llm = lambda m, **kw: (seen.append(m[0]["content"]), json.dumps(_in_pixels(GOOD_REPLY)))[1]
        try:
            app.read_plan_geometry(str(plan), LABELS)
        finally:
            app.call_llm = real
            tmp.cleanup()
        self.assertIn("quarter-circle arc, often dotted or dashed", seen[0])
        self.assertIn("en suite opens from its", seen[0])

    def test_doors_are_drawn_with_their_swing(self):
        g = app.parse_plan_geometry(self._reply(), LABELS, SIZE)
        svg = app.generate_floor_plan_svg([{"label": l, "items": []} for l in LABELS], geometry=g)
        doors = sum(len(r["doors"]) for r in g["rooms"].values())
        self.assertEqual(svg.count('stroke-dasharray="2 2"'), doors)   # one arc per door


class SizeHints(unittest.TestCase):

    def test_hdb_rooms_get_typical_sizes(self):
        h = app._size_hints(LABELS, "3-Room HDB")
        self.assertIn("Master Bedroom: about 3.4 m x 3.8 m", h)
        self.assertIn("proportions", h)

    def test_private_housing_gets_none(self):
        self.assertEqual(app._size_hints(LABELS, "Condominium"), "")

    def test_prompt_carries_hints_only_when_switched_on(self):
        import tempfile as _t
        tmp = _t.TemporaryDirectory()
        plan = Path(tmp.name) / "p.png"
        _png(plan, *SIZE)
        seen, real = [], app.call_llm
        app.call_llm = lambda m, **kw: (seen.append(m[0]["content"]), json.dumps(_in_pixels(GOOD_REPLY)))[1]
        try:
            for on in (False, True):
                app.PLAN_TRACE_SIZE_HINTS = on
                app.read_plan_geometry(str(plan), LABELS, housing_label="3-Room HDB")
        finally:
            app.PLAN_TRACE_SIZE_HINTS = False
            app.call_llm = real
            tmp.cleanup()
        self.assertNotIn("typically about this size", seen[0])
        self.assertIn("typically about this size", seen[-1])
        self.assertNotIn("{size_hints}", seen[0])


class Walls(unittest.TestCase):
    """Walls found in the image, and a trace fitted onto them."""

    def setUp(self):
        from PIL import Image, ImageDraw
        self.tmp = tempfile.TemporaryDirectory()
        self.plan = Path(self.tmp.name) / "walls.png"
        img = Image.new("RGB", (600, 400), "white")
        d = ImageDraw.Draw(img)
        d.rectangle([100, 50, 500, 350], outline="black", width=6)      # outer walls
        d.line([(300, 50), (300, 350)], fill="black", width=5)         # a middle wall
        d.text((150, 200), "LIVING", fill="black")                     # text is not a wall
        img.save(self.plan)

    def tearDown(self):
        self.tmp.cleanup()

    def test_walls_are_found_and_text_ignored(self):
        w = app.detect_plan_walls(str(self.plan))
        self.assertEqual(len(w["x"]), 3)
        for got, want in zip(w["x"], (102, 300, 497)):
            self.assertAlmostEqual(got, want, delta=4)
        self.assertEqual(len(w["y"]), 2)
        self.assertAlmostEqual(w["extent"][0], 102, delta=4)
        self.assertAlmostEqual(w["extent"][3], 347, delta=4)

    def test_blank_image_has_no_walls(self):
        from PIL import Image
        blank = Path(self.tmp.name) / "blank.png"
        Image.new("RGB", (300, 200), "white").save(blank)
        self.assertIsNone(app.detect_plan_walls(str(blank)))

    def test_squashed_layout_is_refitted_and_snapped(self):
        w = app.detect_plan_walls(str(self.plan))
        size = (600, 400)
        # Two rooms, right side by side, but the model squashed the layout
        # into the top-left of the image.
        data = {"rooms": [{"name": "A", "boxes": [[50, 50, 250, 400]]},
                          {"name": "B", "boxes": [[250, 50, 450, 400]]}]}
        out = app.align_to_walls(data, w, size)
        a, b = out["rooms"][0]["boxes"][0], out["rooms"][1]["boxes"][0]
        to_px = lambda v, n: v / 1000 * n
        self.assertAlmostEqual(to_px(a[0], 600), 102, delta=5)   # onto the outer wall
        self.assertAlmostEqual(to_px(a[2], 600), 300, delta=5)   # onto the middle wall
        self.assertAlmostEqual(to_px(b[2], 600), 497, delta=5)
        self.assertAlmostEqual(to_px(a[3], 400), 347, delta=5)

    def test_close_layout_is_only_snapped(self):
        w = app.detect_plan_walls(str(self.plan))
        near = [102 / 600 * 1000 + 5, 50 / 400 * 1000, 300 / 600 * 1000 - 8, 347 / 400 * 1000]
        data = {"rooms": [{"name": "A", "boxes": [near]},
                          {"name": "B", "boxes": [[300 / 600 * 1000, 50 / 400 * 1000,
                                                   497 / 600 * 1000, 347 / 400 * 1000]]}]}
        out = app.align_to_walls(data, w, (600, 400))
        self.assertAlmostEqual(out["rooms"][0]["boxes"][0][2] / 1000 * 600, 300, delta=3)


class Consensus(unittest.TestCase):

    def _trace(self, kitchen_box, extra=None):
        rooms = [{"name": "Kitchen", "boxes": [kitchen_box]}]
        return {"rooms": rooms + (extra or [])}

    def test_middle_trace_wins_per_room(self):
        runs = [self._trace([100, 100, 200, 200]),
                self._trace([110, 105, 205, 210]),       # the median
                self._trace([400, 400, 600, 700])]       # an outlier
        out = app._trace_consensus(runs)
        self.assertEqual(out["rooms"][0]["boxes"][0], [110, 105, 205, 210])

    def test_room_seen_by_a_minority_is_dropped(self):
        balcony = [{"name": "Balcony", "boxes": [[0, 0, 50, 50]]}]
        runs = [self._trace([100, 100, 200, 200], balcony),
                self._trace([100, 100, 200, 200]),
                self._trace([100, 100, 200, 200])]
        names = [r["name"] for r in app._trace_consensus(runs)["rooms"]]
        self.assertEqual(names, ["Kitchen"])

    def test_live_replies_combine_into_a_valid_trace(self):
        # The saved live reply, three times with jitter, must still parse.
        base = app._pixels_to_permille(json.loads(json.dumps(OpenPlan.LIVE)), SIZE)
        runs = []
        for d in (-6, 0, 6):
            r = json.loads(json.dumps(base))
            for e in r["rooms"]:
                e["boxes"] = [[v + d for v in b] for b in e["boxes"]]
            runs.append(r)
        g = app.parse_plan_geometry(app._trace_consensus(runs), LABELS, SIZE)
        self.assertEqual(g["missing"], [])


class Candidates(unittest.TestCase):
    """read_plan_geometry keeps the candidate that loses the fewest rooms."""

    def setUp(self):
        import tempfile as _t
        self.tmp = _t.TemporaryDirectory()
        self.plan = Path(self.tmp.name) / "plan.png"
        _png(self.plan, *SIZE)
        self._real = app.call_llm

    def tearDown(self):
        app.call_llm = self._real
        self.tmp.cleanup()

    def test_mixing_that_loses_a_room_is_not_used(self):
        good = _in_pixels(GOOD_REPLY)
        # Two traces put Living / Dining over the kitchen and bathrooms: the
        # mixed result carves it away, but the whole good trace keeps it.
        bad = json.loads(json.dumps(good))
        bad["rooms"][0]["boxes"] = [[300, 230, 440, 290]]
        replies = [good, bad, bad]
        import threading
        lock = threading.Lock()

        def answer(*a, **kw):
            with lock:
                return json.dumps(replies.pop(0))
        app.call_llm = answer
        g = app.read_plan_geometry(str(self.plan), LABELS)
        self.assertNotIn("Living / Dining", g["missing"])

    def test_most_typical_trace_is_one_whole_reply(self):
        a = {"rooms": [{"name": "A", "boxes": [[0, 0, 100, 100]]}, {"name": "B", "boxes": [[100, 0, 200, 100]]}]}
        b = {"rooms": [{"name": "A", "boxes": [[5, 0, 105, 100]]}, {"name": "B", "boxes": [[105, 0, 205, 100]]}]}
        c = {"rooms": [{"name": "A", "boxes": [[500, 500, 600, 600]]}, {"name": "B", "boxes": [[0, 0, 10, 10]]}]}
        self.assertIn(app._most_typical_trace([a, b, c]), (a, b))


class Scale(unittest.TestCase):

    def test_rooms_add_up_to_the_floor_area(self):
        g = app.parse_plan_geometry(GOOD_REPLY, LABELS, SIZE)
        m = app.plan_metres_per_px(g, 67)
        total = sum(app.union_area(r["parts"]) * m * m for r in g["rooms"].values())
        self.assertAlmostEqual(total, 67 * app._ROOM_COVERAGE, places=6)

    def test_no_floor_size_means_no_dimensions(self):
        g = app.parse_plan_geometry(GOOD_REPLY, LABELS, SIZE)
        self.assertIsNone(app.plan_metres_per_px(g, ""))
        self.assertIsNone(app.plan_metres_per_px(g, "abc"))


class Drawing(unittest.TestCase):

    def setUp(self):
        self.geo = app.parse_plan_geometry(GOOD_REPLY, LABELS, SIZE)
        self.rooms = [{"label": l, "items": [], "colour": "#C9D4E0"} for l in LABELS]

    def test_traced_plan_keeps_layout(self):
        svg = app.generate_floor_plan_svg(self.rooms, geometry=self.geo)
        for label in LABELS:
            self.assertIn(app.html_escape(label), svg)
        self.assertIn("approximate", svg)
        # Quiet: room names only — no sizes, no furniture names.
        self.assertNotIn("≈", svg)
        for item in ("Bed", "Wardrobe", "Vanity", "Shower", "Cooktop"):
            self.assertNotIn(f">{item}<", svg)
        self.assertEqual(svg.count('class="room-wall"'), 8)       # one outline per room

    def test_traced_plan_matches_the_plan_aspect(self):
        svg = app.generate_floor_plan_svg(self.rooms, geometry=self.geo)
        vb = [float(v) for v in svg.split('viewBox="')[1].split('"')[0].split()]
        # Rooms span 433 x 256 source px, so the drawing is wider than tall.
        self.assertGreater(vb[2], vb[3])

    def test_without_trace_it_is_the_schematic(self):
        svg = app.generate_floor_plan_svg(self.rooms)
        self.assertNotIn("approximate", svg)

    def test_broken_trace_falls_back_to_schematic(self):
        broken = {"rooms": {"Kitchen": {"x": 0}}}
        svg = app.generate_floor_plan_svg(self.rooms, geometry=broken)
        self.assertIn("Kitchen", svg)
        self.assertNotIn("approximate", svg)

    def test_room_visual_keeps_proportions(self):
        geo = self.geo["rooms"]["Kitchen"]           # tall and narrow
        svg = app.generate_room_concept_visual("Kitchen", "japandi",
                                               items=["Cooktop"], geo=geo, px_per_m=0.02)
        d = svg.split('class="room-wall" d="')[1].split('"')[0]
        pts = [tuple(map(float, p.split(","))) for p in d.replace("M", " ").replace("L", " ").split()]
        w = max(x for x, _ in pts) - min(x for x, _ in pts)
        h = max(y for _, y in pts) - min(y for _, y in pts)
        self.assertAlmostEqual(w / h, geo["w"] / geo["h"], places=2)
        self.assertIn("≈", svg)

    def test_room_visual_without_trace_is_unchanged(self):
        svg = app.generate_room_concept_visual("Kitchen", "japandi", items=["Cooktop"])
        self.assertIn('width="372.0" height="206.0"', svg)   # the full plate


class Reader(unittest.TestCase):
    """read_plan_geometry end to end, with the gateway stubbed out."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan = Path(self.tmp.name) / "plan.png"
        _png(self.plan, *SIZE)
        self._real = app.call_llm

    def tearDown(self):
        app.call_llm = self._real
        self.tmp.cleanup()

    def test_image_size_from_header(self):
        self.assertEqual(app.image_size(str(self.plan)), SIZE)
        self.assertIsNone(app.image_size(__file__))

    def test_reads_and_validates(self):
        seen = {}

        def fake(messages, **kw):
            seen.update(kw, prompt=messages[0]["content"], images=messages[0].get("images"))
            return "```json\n" + json.dumps(_in_pixels(GOOD_REPLY)) + "\n```"

        app.call_llm = fake
        g = app.read_plan_geometry(str(self.plan), LABELS, housing_label="3-Room HDB")
        self.assertEqual(len(g["rooms"]), 8)
        self.assertEqual(seen["images_sent"], 1)
        self.assertFalse(seen["fallback_to_mock"])  # never trace from the mock
        self.assertEqual(len(seen["images"]), 1)
        for label in LABELS:
            self.assertIn(f"- {label}", seen["prompt"])
        self.assertNotIn("{names}", seen["prompt"])
        self.assertIn("700 pixels wide and 467 pixels tall", seen["prompt"])
        # Pixels in, the same trace out as the 0-1000 fixture gives (with its
        # small gaps closed, as the reader does).
        want = app.parse_plan_geometry(_closed(GOOD_REPLY), LABELS, SIZE)
        for label, room in want["rooms"].items():
            for a, b in zip(room["parts"], g["rooms"][label]["parts"]):
                for k in "xywh":
                    self.assertAlmostEqual(a[k], b[k], delta=1.0)

    def test_reply_on_the_wrong_scale_is_not_converted_twice(self):
        # Asked for pixels, answered on 0-1000: the x of 714 is past the
        # 700 px image, which gives it away.
        app.call_llm = lambda *a, **kw: json.dumps(GOOD_REPLY)
        g = app.read_plan_geometry(str(self.plan), LABELS)
        want = app.parse_plan_geometry(_closed(GOOD_REPLY), LABELS, SIZE)
        self.assertAlmostEqual(g["rooms"]["Kitchen"]["x"], want["rooms"]["Kitchen"]["x"])

    def test_edges_snap_to_listed_walls(self):
        data = {"wall_x": [100, 300], "wall_y": [50, 200],
                "rooms": [{"name": "Kitchen", "boxes": [[104, 47, 296, 260]]}]}
        out = app._snap_to_walls(data, (700, 467))
        # 104->100, 47->50, 296->300; 260 is 60 px from any wall, left alone.
        self.assertEqual(out["rooms"][0]["boxes"], [[100, 50, 300, 260]])

    def _counting(self, answer):
        """A stub gateway that answers answer(n) on its n-th call, thread-safely."""
        import threading
        lock, calls = threading.Lock(), []

        def fake(*a, **kw):
            with lock:
                calls.append(1)
                n = len(calls)
            return answer(n)
        return fake, calls

    def test_empty_replies_are_retried_once(self):
        empty = json.dumps({"rooms": [], "missing": LABELS})
        good = json.dumps(_in_pixels(GOOD_REPLY))
        n = app.PLAN_TRACE_SAMPLES
        app.call_llm, calls = self._counting(lambda i: empty if i <= n else good)
        g = app.read_plan_geometry(str(self.plan), LABELS)
        self.assertEqual(len(g["rooms"]), 8)
        self.assertEqual(len(calls), n + 1)

    def test_still_empty_after_retry_gives_up(self):
        empty = json.dumps({"rooms": [], "missing": LABELS})
        app.call_llm, calls = self._counting(lambda i: empty)
        with self.assertRaisesRegex(ValueError, "could not see"):
            app.read_plan_geometry(str(self.plan), LABELS)
        self.assertEqual(len(calls), app.PLAN_TRACE_SAMPLES + 1)

    def test_one_failed_sample_does_not_sink_the_rest(self):
        good = json.dumps(_in_pixels(GOOD_REPLY))

        def answer(i):
            if i == 1:
                raise RuntimeError("gateway hiccup")
            return good
        app.call_llm, calls = self._counting(answer)
        g = app.read_plan_geometry(str(self.plan), LABELS)
        self.assertEqual(len(g["rooms"]), 8)

    def test_samples_run_in_parallel(self):
        import time
        good = json.dumps(_in_pixels(GOOD_REPLY))

        def slow(*a, **kw):
            time.sleep(0.3)
            return good
        app.call_llm = slow
        t = time.time()
        app.read_plan_geometry(str(self.plan), LABELS)
        self.assertLess(time.time() - t, 0.3 * app.PLAN_TRACE_SAMPLES - 0.1)

    def test_gateway_failure_raises(self):
        def down(*a, **kw):
            raise RuntimeError("gateway down")
        app.call_llm = down
        with self.assertRaises(RuntimeError):
            app.read_plan_geometry(str(self.plan), LABELS)

    def test_pdf_plan_is_not_traced(self):
        pdf = Path(self.tmp.name) / "plan.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        app.call_llm = lambda *a, **kw: self.fail("must not call the model")
        with self.assertRaises(ValueError):
            app.read_plan_geometry(str(pdf), LABELS)

    def test_cache_key_changes_with_the_trace_version(self):
        k = app.plan_geometry_key(str(self.plan), LABELS)
        real = app.PLAN_TRACE_VERSION
        app.PLAN_TRACE_VERSION = real + 1
        try:
            self.assertNotEqual(k, app.plan_geometry_key(str(self.plan), LABELS))
        finally:
            app.PLAN_TRACE_VERSION = real

    def test_cache_key_follows_plan_and_rooms(self):
        k = app.plan_geometry_key(str(self.plan), LABELS)
        self.assertEqual(k, app.plan_geometry_key(str(self.plan), list(LABELS)))
        self.assertNotEqual(k, app.plan_geometry_key(str(self.plan), LABELS[:-1]))
        _png(self.plan, 10, 10)
        self.assertNotEqual(k, app.plan_geometry_key(str(self.plan), LABELS))


if __name__ == "__main__":
    unittest.main(verbosity=2)
