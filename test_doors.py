#!/usr/bin/env python3
"""
FORMA — offline tests that furniture never blocks a door, and that doors are
drawn at a realistic size. No gateway calls.

Run:  python test_doors.py
"""

import itertools
import json
import unittest
from unittest import mock

import agent
import app
import furniture_layout as F


def _rect(q):
    return (q["x"], q["y"], q["bw"], q["bd"])


def _overlap(a, b, tol=0.005):
    return (a[0] < b[0] + b[2] - tol and b[0] < a[0] + a[2] - tol and
            a[1] < b[1] + b[3] - tol and b[1] < a[1] + a[3] - tol)


class DoorSizes(unittest.TestCase):

    def test_hdb_door_leaves(self):
        self.assertEqual(app.door_width_m("Master Bedroom"), 0.8)
        self.assertEqual(app.door_width_m("Bedroom 2"), 0.8)
        self.assertEqual(app.door_width_m("Kitchen"), 0.8)
        self.assertEqual(app.door_width_m("Household Shelter"), 0.8)
        self.assertEqual(app.door_width_m("Common Bathroom"), 0.7)
        self.assertEqual(app.door_width_m("WC"), 0.7)

    def test_way_in_is_kept_only_where_there_is_room_for_it(self):
        self.assertEqual(agent.door_approach("Bedroom 2"), 0.3)
        self.assertEqual(agent.door_approach("Living Room"), 0.3)
        self.assertEqual(agent.door_approach("Common Bathroom"), 0.0)
        self.assertEqual(agent.door_approach("Household Shelter"), 0.0)

    def test_zone_grows_into_the_room_only(self):
        self.assertEqual(F.door_zone((1.0, 0.0), "top", 0.8, 0.3), (0.6, 0.0, 0.8, 1.1))
        self.assertEqual(F.door_zone((3.0, 1.0), "right", 0.8, 0.3), (1.9, 0.6, 1.1, 0.8))
        zone = F.door_zone((1.0, 3.0), "bottom", 0.8, 0.3)
        self.assertAlmostEqual(zone[1], 1.9)
        self.assertAlmostEqual(zone[3], 1.1)


class NothingBlocksADoor(unittest.TestCase):
    """Across many rooms and door positions: no piece in a door's swing or in
    the way in past it."""

    ROOMS = {
        "Bedroom 2":       ["Queen Bed", "Wardrobe", "Desk", "Bedside Table"],
        "Master Bedroom":  ["King Bed", "Wardrobe", "Bedside Table", "Dresser"],
        "Living Room":     ["Sofa", "Coffee Table", "TV Console", "Armchair", "Sideboard"],
        "Study":           ["Desk", "Bookshelf", "Storage"],
    }

    def test_sweep(self):
        checked = 0
        for (label, names), (W, D), wall, at in itertools.product(
                self.ROOMS.items(), [(2.8, 3.0), (3.2, 3.6), (3.6, 4.2), (4.5, 5.5)],
                ["top", "bottom", "left", "right"], [0.15, 0.5, 0.85]):
            L = W if wall in ("top", "bottom") else D
            point = {"top": (at * W, 0.0), "bottom": (at * W, D),
                     "left": (0.0, at * D), "right": (W, at * D)}[wall]
            door = {"point": point, "wall": wall, "width": app.door_width_m(label),
                    "approach": agent.door_approach(label)}
            res = F.place_parts([(0.0, 0.0, W, D)], F.pieces_from_names(names), [door])
            zone = F.door_zone(point, wall, door["width"], door["approach"])
            for q in res["placed"]:
                self.assertFalse(_overlap(zone, _rect(q)),
                                 f"{q['name']} blocks the door in {label} {W}x{D} {wall}@{at}")
            checked += 1
            del L
        self.assertEqual(checked, 4 * 4 * 4 * 3)

    def test_l_shaped_room_keeps_its_door_clear(self):
        door = {"point": (4.0, 1.5), "wall": "right", "width": 0.8, "approach": 0.3}
        res = F.place_parts([(0, 0, 4.0, 3.0), (0, 3.0, 2.5, 2.0)],
                            F.pieces_from_names(["Sofa", "Coffee Table", "Sideboard", "Shelving"]),
                            [door])
        zone = F.door_zone(door["point"], "right", 0.8, 0.3)
        for q in res["placed"]:
            self.assertFalse(_overlap(zone, _rect(q)), f"{q['name']} blocks the door")


class InferredDoors(unittest.TestCase):
    """A traced room with no door on the plan still gets its way in kept clear."""

    GEO = {"image_w": 400, "image_h": 300,
           "rooms": {"Living Room": {"x": 0, "y": 0, "w": 200, "h": 300},
                     "Bedroom 2": {"x": 200, "y": 0, "w": 150, "h": 120},
                     "Study": {"x": 200, "y": 180, "w": 150, "h": 120}},
           "walkways": [{"x": 200, "y": 120, "w": 150, "h": 60}]}

    def test_door_faces_the_corridor(self):
        door = app.infer_door(self.GEO, "Bedroom 2")
        self.assertEqual(door["wall"], "bottom")               # onto the walkway below
        self.assertAlmostEqual(door["at"], 0.5)

    def test_door_faces_the_living_room_when_no_corridor_touches(self):
        geo = {**self.GEO, "walkways": []}
        self.assertEqual(app.infer_door(geo, "Study")["wall"], "left")

    def test_unknown_room_has_none(self):
        self.assertIsNone(app.infer_door(self.GEO, "Garage"))

    def test_prepare_space_uses_it_but_never_draws_it(self):
        geo = {**self.GEO, "outline": [{"x": 0, "y": 0, "w": 350, "h": 300}]}
        rooms = [{"key": "bedroom_2", "label": "Bedroom 2"}]
        step1 = {"floor_plan_path": None, "floor_size": "90", "housing_type": "hdb_4room"}
        out = agent._prepare_space(app, rooms, {**step1, "floor_plan_path": "x"}, {},
                                   {**geo, "key": app.plan_geometry_key("x", ["Bedroom 2"])}, None)
        doors = out["outline"]["bedroom_2"]["doors"]
        self.assertEqual(len(doors), 1)
        self.assertEqual(doors[0]["wall"], "bottom")
        self.assertEqual(doors[0]["approach"], 0.3)
        self.assertNotIn("doors", geo["rooms"]["Bedroom 2"])     # the plan is not drawn on


class Scale(unittest.TestCase):

    def test_a_shrunken_reference_gives_way_to_the_typical_flat(self):
        geo = {"image_w": 400, "image_h": 300,
               "rooms": {"Bedroom 2": {"x": 0, "y": 0, "w": 100, "h": 100}},
               "outline": [{"x": 0, "y": 0, "w": 300, "h": 300}],
               # This reference makes the flat 300px * 0.02 = 6 m square: 36 m2
               # for a 3-room HDB that is typically 67 m2.
               "m_per_px_ref": 0.02}
        key = app.plan_geometry_key("x", ["Bedroom 2"])
        out = agent._prepare_space(app, [{"key": "bedroom_2", "label": "Bedroom 2"}],
                                   {"floor_plan_path": "x", "housing_type": "hdb_3room"}, {},
                                   {**geo, "key": key}, {"key": "none"})
        typical = app.plan_metres_per_px(geo, 67)
        self.assertAlmostEqual(out["px_per_m"], typical)

    def test_a_believable_reference_is_kept(self):
        geo = {"image_w": 400, "image_h": 300,
               "rooms": {"Bedroom 2": {"x": 0, "y": 0, "w": 100, "h": 100}},
               "outline": [{"x": 0, "y": 0, "w": 300, "h": 300}]}
        typical = app.plan_metres_per_px(geo, 67)
        geo["m_per_px_ref"] = typical * 1.03
        key = app.plan_geometry_key("x", ["Bedroom 2"])
        out = agent._prepare_space(app, [{"key": "bedroom_2", "label": "Bedroom 2"}],
                                   {"floor_plan_path": "x", "housing_type": "hdb_3room"}, {},
                                   {**geo, "key": key}, {"key": "none"})
        self.assertAlmostEqual(out["px_per_m"], typical * 1.03)


class Swing(unittest.TestCase):
    """Doors keep which end they hinge at and which way they open."""

    GEO = {"image_w": 400, "image_h": 300, "wall_px": 4,
           "rooms": {"Bedroom 2": {"x": 100, "y": 0, "w": 100, "h": 100,
                                   "parts": [{"x": 100, "y": 0, "w": 100, "h": 100}], "doors": []},
                     "Bathroom": {"x": 100, "y": 100, "w": 60, "h": 50,
                                  "parts": [{"x": 100, "y": 100, "w": 60, "h": 50}],
                                  # Hinged at the right, swinging OUT — up into the bedroom.
                                  "doors": [{"part": 0, "wall": "top", "at": 0.5,
                                             "hinge": "end", "opens": "out"}]}}}

    def test_drawn_from_its_hinge_and_the_way_it_opens(self):
        svg = "".join(app._door_svg(self.GEO["rooms"]["Bathroom"], "#fff", 20))
        # Gap 120..140 on y=100; hinge at the right end (140); leaf swings up (out).
        self.assertIn('x1="140.0" y1="100.0" x2="140.0" y2="80.0"', svg)
        into = {**self.GEO["rooms"]["Bathroom"],
                "doors": [{"part": 0, "wall": "top", "at": 0.5, "hinge": "start", "opens": "in"}]}
        self.assertIn('x1="120.0" y1="100.0" x2="120.0" y2="120.0"',
                      "".join(app._door_svg(into, "#fff", 20)))

    def test_a_neighbours_door_opening_out_is_this_rooms_to_keep_clear(self):
        bed = app.room_door_swings(self.GEO, "Bedroom 2")
        self.assertEqual(len(bed), 1)
        self.assertEqual(bed[0]["wall"], "bottom")
        self.assertTrue(bed[0]["swings_in"])
        bath = app.room_door_swings(self.GEO, "Bathroom")
        self.assertFalse(bath[0]["swings_in"])

    def test_editor_doors_round_trip(self):
        doors = app.plan_doors(self.GEO)
        self.assertEqual(doors[0]["dir"], -1)                 # swings up
        self.assertEqual(doors[0]["hinge"], "high")
        geo = json.loads(json.dumps(self.GEO))
        app.attach_doors(geo, doors)
        # Kept once, on the bedroom it swings into, opening in.
        self.assertEqual(geo["rooms"]["Bathroom"]["doors"], [])
        self.assertEqual(geo["rooms"]["Bedroom 2"]["doors"],
                         [{"part": 0, "wall": "bottom", "at": 0.3, "hinge": "end", "opens": "in"}])
        self.assertEqual([{k: v for k, v in d.items() if k != "room"} for d in app.plan_doors(geo)],
                         [{k: v for k, v in d.items() if k != "room"} for d in doors])

    def test_a_door_in_no_wall_is_dropped(self):
        geo = json.loads(json.dumps(self.GEO))
        app.attach_doors(geo, [{"x": 300, "y": 250, "axis": "h", "dir": 1, "hinge": "low"}])
        self.assertTrue(all(not r["doors"] for r in geo["rooms"].values()))

    def test_a_door_swinging_away_keeps_its_doorway_clear(self):
        # A wardrobe against the bottom wall, where a door swings OUT of the room.
        door = {"point": (1.5, 3.0), "wall": "bottom", "width": 0.8, "swings_in": False}
        res = F.place_parts([(0, 0, 3.0, 3.0)], F.pieces_from_names(["Wardrobe", "Desk", "Bookshelf"]), [door])
        zone = (1.1, 3.0 - F.DOORWAY_DEPTH, 0.8, F.DOORWAY_DEPTH)
        for q in res["placed"]:
            self.assertFalse(_overlap(zone, _rect(q)), f"{q['name']} stands in the doorway")


class PrintedDimensions(unittest.TestCase):

    WALLS = {"x": [100.0, 200.5, 300.0], "y": [50.0, 250.0], "thickness": 6}

    def test_ends_snap_onto_walls_and_readings_agree(self):
        dims = [{"mm": 3000, "from": (103, 30), "to": (198, 30)},      # 100 -> 200.5 px
                {"mm": 3000, "from": (202, 30), "to": (297, 30)},      # 200.5 -> 300
                {"mm": 6000, "from": (20, 52), "to": (20, 248)}]       # 50 -> 250
        m = app.scale_from_dimensions(dims, self.WALLS, (400, 300))
        self.assertAlmostEqual(m, 0.03, delta=0.0006)

    def test_a_misread_number_is_outvoted(self):
        dims = [{"mm": 3000, "from": (100, 30), "to": (200, 30)},
                {"mm": 3000, "from": (200, 30), "to": (300, 30)},
                {"mm": 9000, "from": (100, 40), "to": (200, 40)}]
        self.assertAlmostEqual(app.scale_from_dimensions(dims, self.WALLS, (400, 300)), 0.03, delta=0.001)

    def test_slanted_or_tiny_lines_are_ignored(self):
        self.assertIsNone(app.scale_from_dimensions(
            [{"mm": 3000, "from": (100, 30), "to": (200, 90)},
             {"mm": 3000, "from": (100, 30), "to": (105, 30)}], self.WALLS, (400, 300)))

    def test_clean_dimensions(self):
        self.assertEqual(app._clean_dimensions([{"mm": "3,048.0", "from": [1, 2], "to": [3, 4]},
                                                {"mm": 12, "from": [0, 0], "to": [1, 1]}, "x"]),
                         [{"mm": 3048.0, "from": (1.0, 2.0), "to": (3.0, 4.0)}])

    def test_printed_scale_comes_first(self):
        geo = {"image_w": 400, "image_h": 300, "wall_px": 5,
               "rooms": {"Bedroom 2": {"x": 0, "y": 0, "w": 100, "h": 100}},
               "outline": [{"x": 0, "y": 0, "w": 300, "h": 300}],
               "m_per_px_dims": 0.03, "m_per_px_ref": 0.05}
        key = app.plan_geometry_key("x", ["Bedroom 2"])
        out = agent._prepare_space(app, [{"key": "bedroom_2", "label": "Bedroom 2"}],
                                   {"floor_plan_path": "x", "housing_type": "hdb_3room",
                                    "floor_size": "999"}, {}, {**geo, "key": key}, {"key": "none"})
        self.assertEqual(out["px_per_m"], 0.03)


class WallFaces(unittest.TestCase):
    """Rooms are measured and furnished to the wall's face, not its centre."""

    def test_room_loses_half_a_wall_each_side(self):
        geo = {"image_w": 400, "image_h": 300, "wall_px": 5,
               "rooms": {"Bedroom 2": {"x": 0, "y": 0, "w": 100, "h": 100}},
               "outline": [{"x": 0, "y": 0, "w": 300, "h": 300}], "m_per_px_dims": 0.03}
        key = app.plan_geometry_key("x", ["Bedroom 2"])
        out = agent._prepare_space(app, [{"key": "bedroom_2", "label": "Bedroom 2"}],
                                   {"floor_plan_path": "x", "housing_type": "hdb_3room"}, {},
                                   {**geo, "key": key}, {"key": "none"})
        # 100 px = 3.0 m centre to centre; a 5 px (0.15 m) wall takes 0.075 m a side.
        self.assertAlmostEqual(out["inset"], 0.075)
        w, d = out["sizes"]["bedroom_2"]
        self.assertAlmostEqual(w, 2.85)
        self.assertAlmostEqual(out["outline"]["bedroom_2"]["W"], 2.85)

    def test_drawing_puts_the_layout_inside_the_walls(self):
        ox, oy, k = app.layout_frame({"W": 2.85, "inset": 0.075}, {"x": 10, "y": 20, "w": 300})
        self.assertAlmostEqual(k, 100.0)                     # 300 px over 3.0 m
        self.assertAlmostEqual(ox, 17.5)
        self.assertAlmostEqual(oy, 27.5)


def setUpModule():
    # SOCLAAS may be configured in .env: never let these tests reach it.
    global _patches
    _patches = [mock.patch.object(app, "call_llm", side_effect=AssertionError("no model calls")),
                mock.patch.object(app, "plan_furniture", return_value={})]
    for p in _patches:
        p.start()


def tearDownModule():
    for p in _patches:
        p.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
