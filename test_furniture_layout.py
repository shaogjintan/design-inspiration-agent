#!/usr/bin/env python3
"""
FORMA — offline tests for furniture layout (furniture_layout.py) and the
furniture plan around it in app.py. No gateway calls.

Run:  python test_furniture_layout.py
"""

import json
import unittest

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
