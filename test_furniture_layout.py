#!/usr/bin/env python3
"""
FORMA — offline tests for furniture layout (furniture_layout.py) and the
furniture plan around it in app.py. No gateway calls.

Run:  python test_furniture_layout.py
"""

import json
import unittest
from pathlib import Path

import app
import furniture_layout as F


def _rect(q):
    return (q["x"], q["y"], q["bw"], q["bd"])


def _overlap(a, b, tol=0.005):
    return (a[0] < b[0] + b[2] - tol and b[0] < a[0] + a[2] - tol and
            a[1] < b[1] + b[3] - tol and b[1] < a[1] + a[3] - tol)


def _layout(W, D, names):
    return F.place_room(W, D, F.pieces_from_names(names))


class Guarantees(unittest.TestCase):
    """What must hold for every layout, whatever the room."""

    ROOMS = [
        (3.0, 3.2, ["Queen Bed", "Wardrobe", "Bedside Table", "Desk"]),
        (3.4, 3.8, ["King Bed", "Wardrobe", "Bedside Table", "Dresser"]),
        (4.5, 5.5, ["Sofa", "Coffee Table", "TV Console", "Armchair", "Rug",
                    "Dining Table", "Sideboard"]),
        (2.4, 3.6, ["Fridge", "Hob", "Sink", "Storage"]),
        (1.6, 2.2, ["Vanity", "Toilet", "Shower"]),
        (1.5, 2.4, ["Washing Machine", "Drying Rack"]),
    ]

    def test_nothing_overlaps_and_everything_is_inside(self):
        for W, D, names in self.ROOMS:
            placed = [q for q in _layout(W, D, names)["placed"] if q["place"] != "under"]
            for q in placed:
                r = _rect(q)
                self.assertTrue(r[0] >= -1e-6 and r[1] >= -1e-6 and
                                r[0] + r[2] <= W + 1e-6 and r[1] + r[3] <= D + 1e-6,
                                f"{q['name']} outside {W}x{D}")
            for i, a in enumerate(placed):
                for b in placed[i + 1:]:
                    self.assertFalse(_overlap(_rect(a), _rect(b)),
                                     f"{a['name']} overlaps {b['name']} in {W}x{D}")

    def test_every_piece_is_placed_or_reported(self):
        for W, D, names in self.ROOMS:
            res = _layout(W, D, names)
            want = {p["name"] for p in F.pieces_from_names(names)}
            got = {q["name"] for q in res["placed"]} | set(res["skipped"])
            self.assertEqual(want, got)

    def test_deterministic(self):
        W, D, names = self.ROOMS[2]
        self.assertEqual(_layout(W, D, names), _layout(W, D, names))

    def test_wall_pieces_back_onto_their_wall(self):
        for W, D, names in self.ROOMS:
            for q in _layout(W, D, names)["placed"]:
                r, wall = _rect(q), q["wall"]
                if wall == "top":
                    self.assertAlmostEqual(r[1], 0, places=6)
                elif wall == "bottom":
                    self.assertAlmostEqual(r[1] + r[3], D, places=6)
                elif wall == "left":
                    self.assertAlmostEqual(r[0], 0, places=6)
                elif wall == "right":
                    self.assertAlmostEqual(r[0] + r[2], W, places=6)

    def test_minimum_clearance_in_front_of_wardrobe(self):
        res = _layout(3.0, 3.2, ["Queen Bed", "Wardrobe", "Desk"])
        ward = next(q for q in res["placed"] if q["name"] == "Wardrobe")
        need = F._min_clearance(0.9)
        W, D = 3.0, 3.2
        zone = {"top": (ward["x"], ward["bd"], ward["bw"], need),
                "bottom": (ward["x"], D - ward["bd"] - need, ward["bw"], need),
                "left": (ward["bw"], ward["y"], need, ward["bd"]),
                "right": (W - ward["bw"] - need, ward["y"], need, ward["bd"])}[ward["wall"]]
        for q in res["placed"]:
            if q is not ward:
                self.assertFalse(_overlap(zone, _rect(q)), f"{q['name']} blocks the wardrobe")


class Relations(unittest.TestCase):

    def setUp(self):
        self.res = _layout(4.5, 5.5, ["Sofa", "Coffee Table", "TV Console", "Rug", "Dining Table"])
        self.by = {q["name"]: q for q in self.res["placed"]}

    def test_coffee_table_sits_in_front_of_the_sofa(self):
        sofa, table = self.by["Sofa"], self.by["Coffee table"]
        sx, sy = sofa["x"] + sofa["bw"] / 2, sofa["y"] + sofa["bd"] / 2
        tx, ty = table["x"] + table["bw"] / 2, table["y"] + table["bd"] / 2
        if sofa["wall"] in ("left", "right"):
            self.assertAlmostEqual(sy, ty, places=6)          # centred on it
            gap = table["x"] - (sofa["x"] + sofa["bw"]) if sofa["wall"] == "left" \
                else sofa["x"] - (table["x"] + table["bw"])
        else:
            self.assertAlmostEqual(sx, tx, places=6)
            gap = table["y"] - (sofa["y"] + sofa["bd"]) if sofa["wall"] == "top" \
                else sofa["y"] - (table["y"] + table["bd"])
        self.assertAlmostEqual(gap, 0.45, places=6)

    def test_tv_is_on_the_opposite_wall(self):
        self.assertEqual(self.by["TV console"]["wall"], F._opposite(self.by["Sofa"]["wall"]))

    def test_nothing_blocks_the_view(self):
        view = F._between(_rect(self.by["Sofa"]), _rect(self.by["TV console"]))
        self.assertFalse(_overlap(view, _rect(self.by["Dining table"])))

    def test_rug_lies_under_the_coffee_table(self):
        rug, table = self.by["Rug"], self.by["Coffee table"]
        self.assertLessEqual(rug["x"], table["x"])
        self.assertGreaterEqual(rug["x"] + rug["bw"], table["x"] + table["bw"])
        self.assertEqual(self.res["placed"][0]["name"], "Rug")    # drawn first

    def test_bedside_tables_flank_the_bed(self):
        pieces = F.clean_pieces([
            {"name": "Queen Bed", "w": 1.52, "d": 2.03, "place": "wall", "side": 0.6},
            {"name": "Bedside Table", "qty": 2, "w": 0.45, "d": 0.4, "place": "beside",
             "anchor": "Queen Bed"}], [])
        res = F.place_room(3.4, 3.8, pieces)
        bed = next(q for q in res["placed"] if q["name"] == "Queen Bed")
        sides = [q for q in res["placed"] if q["label"] == "Bedside Table"]
        self.assertEqual(len(sides), 2)
        for q in sides:
            self.assertEqual(q["wall"], bed["wall"])
        if bed["wall"] in ("top", "bottom"):
            xs = sorted(q["x"] for q in sides)
            self.assertLess(xs[0], bed["x"])
            self.assertGreater(xs[1], bed["x"])

    def test_anchor_matches_a_longer_name(self):
        pieces = F.clean_pieces([
            {"name": "L-shaped Sofa", "w": 2.4, "d": 1.6, "place": "wall"},
            {"name": "Coffee Table", "w": 1.1, "d": 0.6, "place": "front", "anchor": "sofa"}], [])
        res = F.place_room(4.5, 5.0, pieces)
        table = next(q for q in res["placed"] if q["name"] == "Coffee Table")
        self.assertIsNone(table["wall"])                           # placed in front, not on a wall


class Fitting(unittest.TestCase):

    def test_too_big_is_reported_not_squeezed(self):
        res = _layout(1.4, 1.8, ["King Bed"])
        self.assertEqual(res["placed"], [])
        self.assertEqual(res["skipped"], ["King bed"])

    def test_tight_room_uses_minimum_clearance_before_shrinking(self):
        # 2.03 m bed + 0.6 m wardrobe leave 0.77 m: short of the 0.9 m
        # recommended, enough for the minimum — so no smaller wardrobe.
        res = _layout(3.0, 3.4, ["Queen Bed", "Wardrobe"])
        ward = next(q for q in res["placed"] if q["name"] == "Wardrobe")
        self.assertTrue(ward["tight"])
        self.assertFalse(ward["scaled"])

    def test_second_part_takes_what_the_first_cannot(self):
        # An L: a small living end and a separate dining end.
        pieces = F.pieces_from_names(["Sofa", "Coffee Table", "Dining Table"])
        res = F.place_parts([(0, 0, 3.2, 3.0), (3.2, 0, 3.0, 3.0)], pieces)
        table = next(q for q in res["placed"] if q["name"] == "Dining table")
        self.assertGreaterEqual(table["x"], 3.2)
        self.assertEqual(res["skipped"], [])


class DoorRules(unittest.TestCase):

    def test_nothing_sits_in_a_door_swing(self):
        doors = [{"point": (1.5, 3.2), "wall": "bottom", "width": 0.85},
                 {"point": (0.0, 1.0), "wall": "left", "width": 0.85}]
        res = F.place_parts([(0, 0, 3.0, 3.2)], F.pieces_from_names(
            ["Queen Bed", "Wardrobe", "Desk", "Bedside Table"]), doors)
        for dr in doors:
            zone = F.door_zone(dr["point"], dr["wall"], dr["width"])
            for q in res["placed"]:
                self.assertFalse(_overlap(zone, _rect(q)), f"{q['name']} blocks a door")

    def test_bed_keeps_off_the_door_wall(self):
        # Door in the middle of the top wall: the bed goes elsewhere.
        doors = [{"point": (2.2, 0.0), "wall": "top", "width": 0.85}]
        res = F.place_parts([(0, 0, 3.6, 4.0)], F.pieces_from_names(["Queen Bed"]), doors)
        self.assertNotEqual(res["placed"][0]["wall"], "top")

    def test_door_zone_opens_into_the_room(self):
        self.assertEqual(F.door_zone((1.0, 0.0), "top", 0.8), (0.6, 0.0, 0.8, 0.8))
        self.assertEqual(F.door_zone((3.0, 1.0), "right", 0.8), (2.2, 0.6, 0.8, 0.8))

    def test_door_on_another_part_still_blocks_its_swing(self):
        # An L: the door is on the second part's wall; its swing is kept clear.
        doors = [{"point": (4.0, 1.5), "wall": "right", "width": 0.85}]
        res = F.place_parts([(0, 0, 3.0, 3.0), (3.0, 0, 1.0, 3.0)],
                            F.pieces_from_names(["Sideboard", "Shelving"]), doors)
        zone = F.door_zone(doors[0]["point"], "right", 0.85)
        for q in res["placed"]:
            self.assertFalse(_overlap(zone, _rect(q)))


class SizeList(unittest.TestCase):

    def setUp(self):
        import shutil, tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sizes.json"
        shutil.copy(F.CATALOGUE_PATH, self.path)
        self.real = F.CATALOGUE_PATH
        F.load_catalogue(self.path)

    def tearDown(self):
        F.load_catalogue(self.real)
        self.tmp.cleanup()

    def test_listed_size_wins_over_the_models(self):
        out = F.clean_pieces([{"name": "Queen Bed", "w": 1.4, "d": 1.9}], [])
        self.assertEqual((out[0]["w"], out[0]["d"]), (1.52, 2.03))
        self.assertFalse(out[0]["estimated"])

    def test_new_piece_is_sized_by_the_model_then_remembered(self):
        out = F.clean_pieces([{"name": "Upright Piano", "w": 1.5, "d": 0.6,
                               "place": "wall", "clearance": 0.9}], [])
        self.assertTrue(out[0]["estimated"] and out[0]["sized_by_model"])
        self.assertEqual(F.remember(out), ["Upright Piano"])
        saved = json.loads(self.path.read_text())["items"][-1]
        self.assertEqual((saved["name"], saved["w"], saved["d"], saved["source"]),
                         ("Upright Piano", 1.5, 0.6, "model estimate"))
        # Next time: the saved size, whatever the model says — and still
        # marked as an estimate on the drawing.
        again = F.clean_pieces([{"name": "Upright Piano", "w": 2.5, "d": 1.2}], [])
        self.assertEqual((again[0]["w"], again[0]["d"]), (1.5, 0.6))
        self.assertTrue(again[0]["estimated"])
        self.assertFalse(again[0]["sized_by_model"])
        self.assertEqual(F.remember(again), [])               # not saved twice

    def test_standard_sizes_are_not_saved_as_estimates(self):
        out = F.pieces_from_names(["Wardrobe", "Aquarium Stand"])
        self.assertEqual(F.remember(out), [])                  # generic block: no model size

    def test_file_is_readable_and_complete(self):
        doc = json.loads(self.real.read_text())
        self.assertIn("_about", doc)
        names = [i["name"] for i in doc["items"] if "name" in i]
        for bed in F.BED_LADDER:
            self.assertIn(bed, names)


class Beds(unittest.TestCase):

    def test_bed_steps_down_a_size_rather_than_go_missing(self):
        res = F.place_room(2.0, 4.1, F.pieces_from_names(["Queen Bed", "Wardrobe"]))
        self.assertEqual(res["skipped"], [])
        bed = next(q for q in res["placed"] if "bed" in q["label"].lower())
        self.assertIn("(smaller, to fit)", bed["label"])
        self.assertLess(bed["bw"], 1.52)

    def test_bed_lies_side_on_in_a_small_room(self):
        res = F.place_room(1.9, 2.3, F.pieces_from_names(["Single Bed"]))
        bed = res["placed"][0]
        self.assertEqual(res["skipped"], [])
        self.assertAlmostEqual(max(bed["bw"], bed["bd"]), 1.9)
        # Long side along the wall: turned a quarter from headboard-to-wall.
        self.assertEqual(bed["rot"] % 180, 90 if bed["wall"] in ("top", "bottom") else 0)

    def test_side_on_headboard_is_in_the_corner(self):
        # For every wall a side-on bed can take, its headboard (the icon's
        # top, turned by rot) must point at the corner end of the wall.
        heading = {0: (0, -1), 90: (1, 0), 180: (0, 1), 270: (-1, 0)}
        for W, D in ((1.9, 2.3), (2.3, 1.9)):
            res = F.place_room(W, D, F.pieces_from_names(["Single Bed"]))
            bed = res["placed"][0]
            hx, hy = heading[bed["rot"]]
            cx, cy = bed["x"] + bed["bw"] / 2, bed["y"] + bed["bd"] / 2
            # The headboard end sits at the room's edge along the bed's length.
            end = (cx + hx * max(bed["bw"], bed["bd"]) / 2, cy + hy * max(bed["bw"], bed["bd"]) / 2)
            self.assertTrue(min(abs(end[0]), abs(end[0] - W), abs(end[1]), abs(end[1] - D)) < 1e-6,
                            f"headboard not at a wall in {W}x{D}: rot {bed['rot']} on {bed['wall']}")

    def test_bedside_table_goes_at_the_head_of_a_side_on_bed(self):
        pieces = F.clean_pieces([
            {"name": "Single Bed", "place": "wall"},
            {"name": "Bedside Table", "place": "beside", "anchor": "Single Bed"}], [])
        res = F.place_room(1.9, 2.4, pieces)
        bed = next(q for q in res["placed"] if q["label"].lower() == "single bed")
        table = next(q for q in res["placed"] if q["label"].lower() == "bedside table")
        # The table is at the head end: within a table's width of the corner
        # the headboard is in, on the wall that makes that corner.
        head = {0: "top", 180: "bottom", 270: "left", 90: "right"}[bed["rot"]]
        self.assertEqual(table["wall"], head)
        tx, ty = table["x"] + table["bw"] / 2, table["y"] + table["bd"] / 2
        if head in ("left", "right"):
            self.assertLess(abs(ty - (bed["y"] + bed["bd"] + 0.25)), 0.3)
        else:
            self.assertLess(abs(tx - (bed["x"] + bed["bw"] + 0.25)), 0.3)

    def test_what_counts_as_a_bed(self):
        for name in ("Queen Bed", "Single bed", "Bunk Bed", "Bed"):
            self.assertTrue(F._is_bed(name), name)
        for name in ("Bedside Table", "Sofa Bed", "Flower Bed"):
            self.assertFalse(F._is_bed(name), name)


class Cleaning(unittest.TestCase):

    def test_model_pieces_are_validated(self):
        raw = [
            {"name": "Queen Bed", "w": "wide", "d": 99, "place": "floating"},   # bad numbers
            {"name": "Pendant Light", "w": 0.5, "d": 0.5},                        # not floor
            {"name": "Dining Chairs", "qty": 6},                                  # drawn with table
            {"name": "Record Player Stand", "w": 0.6, "d": 0.45, "place": "wall",
             "source": "described"},
            {"name": "Bedside Table", "qty": 2, "place": "beside", "anchor": "Queen Bed"},
            "not a dict",
        ]
        out = F.clean_pieces(raw, [])
        names = [p["name"] for p in out]
        self.assertEqual(names, ["Queen Bed", "Record Player Stand", "Bedside Table", "Bedside Table (2)"])
        bed = out[0]
        self.assertEqual((bed["w"], bed["d"], bed["place"]), (1.52, 2.03, "wall"))
        cab = out[1]
        self.assertTrue(cab["estimated"])                      # no standard for it
        self.assertEqual(cab["source"], "described")
        self.assertFalse(bed["estimated"])
        self.assertEqual(out[3]["label"], "Bedside Table")

    def test_standard_placement_beats_a_plain_guess(self):
        out = F.clean_pieces([{"name": "Drying Rack", "w": 0.9, "d": 0.5, "place": "centre"}], [])
        self.assertEqual(out[0]["place"], "wall")

    def test_model_relation_is_kept(self):
        out = F.clean_pieces([{"name": "Armchair", "place": "beside", "anchor": "sofa"}], [])
        self.assertEqual(out[0]["place"], "beside")

    def test_nothing_usable_falls_back_to_ticked(self):
        out = F.clean_pieces([{"name": "Ceiling Fan"}], ["Wardrobe"])
        self.assertEqual([p["name"] for p in out], ["Wardrobe"])

    def test_unknown_ticked_item_is_a_generic_estimated_block(self):
        out = F.pieces_from_names(["Aquarium Stand"])
        self.assertEqual(out[0]["name"], "Aquarium Stand")
        self.assertTrue(out[0]["estimated"])


class ModelCall(unittest.TestCase):

    INFO = [{"key": "bedroom_2", "label": "Bedroom 2", "size_m": [3.2, 3.0],
             "ticked": ["Desk"], "description": "a sofa bed {and} a tall bookshelf",
             "avoid": "open shelving"}]

    def setUp(self):
        self._real = app.call_llm

    def tearDown(self):
        app.call_llm = self._real

    def test_prompt_carries_requirements_and_guides(self):
        seen = {}

        def fake(messages, **kw):
            seen["prompt"] = messages[0]["content"]
            seen.update(kw)
            return '```json\n{"rooms": {"bedroom_2": [{"name": "Sofa Bed"}]}}\n```'
        app.call_llm = fake
        out = app.plan_furniture(self.INFO)
        self.assertEqual(out, {"bedroom_2": [{"name": "Sofa Bed"}]})
        p = seen["prompt"]
        self.assertIn("a sofa bed {and} a tall bookshelf", p)       # braces survive
        self.assertIn("Must avoid: open shelving", p)
        self.assertIn("about 3.2 m x 3.0 m", p)
        self.assertIn("900 mm", p)                                   # the guides
        self.assertFalse(seen["fallback_to_mock"])

    def test_garbage_raises(self):
        app.call_llm = lambda *a, **kw: "Sorry, I can't help with that."
        with self.assertRaises(Exception):
            app.plan_furniture(self.INFO)

    def test_notes_reach_the_prompt_and_the_key(self):
        seen = {}

        def fake(messages, **kw):
            seen["prompt"] = messages[0]["content"]
            return '{"rooms": {"bedroom_2": [{"name": "Piano"}]}}'
        app.call_llm = fake
        app.plan_furniture(self.INFO, "[Refinement] Add an upright piano to the living room")
        self.assertIn("Add an upright piano", seen["prompt"])
        self.assertNotEqual(app.furniture_key(self.INFO, ""),
                            app.furniture_key(self.INFO, "[Refinement] Add a piano"))

    def test_key_follows_requirements(self):
        a = app.furniture_key(self.INFO)
        b = app.furniture_key([{**self.INFO[0], "description": "just a desk"}])
        self.assertNotEqual(a, b)
        self.assertEqual(a, app.furniture_key(json.loads(json.dumps(self.INFO))))


class Drawing(unittest.TestCase):

    def test_icons_turn_to_face_the_room_and_unknowns_are_blocks(self):
        pieces = F.clean_pieces([
            {"name": "Queen Bed", "w": 1.52, "d": 2.03, "place": "wall"},
            {"name": "Aquarium Stand", "w": 1.0, "d": 0.4, "place": "wall"}], [])
        layout = F.place_room(3.0, 3.2, pieces)
        layout.update(W=3.0, D=3.2)
        svg = "".join(app._draw_layout(layout, 0, 0, 100, "#ccc"))
        bed = next(q for q in layout["placed"] if q["name"] == "Queen Bed")
        self.assertIn(f"rotate({bed['rot']})", svg)
        self.assertIn('stroke-dasharray="4 2"', svg)                # the unknown's block
        self.assertIn("Aquarium Stand (est. size)", svg)
        self.assertNotIn("Queen Bed (est. size)", svg)
        self.assertIn("<title>Queen Bed", svg)                      # rule on hover

    def test_every_piece_is_labelled_on_the_card(self):
        layout = F.place_room(3.4, 3.8, F.clean_pieces([
            {"name": "King Bed", "w": 1.83, "d": 2.03, "place": "wall", "side": 0.6},
            {"name": "Bedside Table", "qty": 2, "w": 0.45, "d": 0.4, "place": "beside",
             "anchor": "King Bed"},
            {"name": "Floor Lamp", "w": 0.3, "d": 0.3, "place": "corner"}], []))
        layout.update(W=3.4, D=3.8, measured=True)
        svg = app.generate_room_concept_visual("Master Bedroom", "japandi", layout=layout)
        self.assertEqual(svg.count(">Bedside Table<"), 2)          # small, still named
        self.assertIn(">Floor Lamp<", svg)
        self.assertIn(">King Bed<", svg)

    def test_overview_drawing_can_leave_labels_off(self):
        layout = F.place_room(3.0, 3.2, F.pieces_from_names(["Bed", "Wardrobe"]))
        layout.update(W=3.0, D=3.2)
        svg = "".join(app._draw_layout(layout, 0, 0, 100, "#ccc", labels=False))
        self.assertNotIn("<text", svg)
        self.assertIn("<title>Bed", svg)                             # still on hover

    def test_room_visual_without_a_plan_uses_a_typical_room(self):
        layout = F.place_room(3.0, 3.2, F.pieces_from_names(["Bed"]))
        layout.update(W=3.0, D=3.2, measured=False, doors_drawn=[dict(F.DEFAULT_DOOR)])
        svg = app.generate_room_concept_visual("Bedroom 2", "japandi", layout=layout)
        self.assertIn("(typical size)", svg)
        self.assertIn(">Bed<", svg)
        self.assertIn('stroke-dasharray="2 2"', svg)                 # its door

    def test_room_visual_reports_what_did_not_fit(self):
        layout = F.place_room(1.4, 1.8, F.pieces_from_names(["King Bed"]))
        layout.update(W=1.4, D=1.8, measured=True)
        svg = app.generate_room_concept_visual("Store", "japandi", layout=layout)
        self.assertIn("Did not fit: King bed", svg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
