#!/usr/bin/env python3
"""
FORMA — offline tests for the step-1 floor-plan read: HDB flats are checked
against their standard layouts, without the template adding rooms the plan
does not print. The model is stubbed; replies below are shaped on real ones.

Run:  python test_floorplan_read.py
"""

import json
import unittest
from unittest import mock

import app



def read(housing_type, reply: dict):
    with mock.patch.object(app, "call_llm", return_value=json.dumps(reply)) as llm, \
         mock.patch.object(app, "image_to_base64", return_value=("x", "image/png")):
        result = app.read_floorplan_rooms(housing_type, "plan.png")
    return result, llm.call_args.args[0][0]["content"]


class Prompt(unittest.TestCase):

    def test_hdb_types_get_their_standard_layouts(self):
        _, prompt = read("hdb_3room", {"rooms": ["KITCHEN"]})
        self.assertIn("Work in three steps", prompt)
        self.assertIn("A — newer (1990s on, BTO): Living/Dining, Master Bedroom", prompt)
        self.assertIn("B — older (1970s-80s): Living Room, Bedroom 1, Bedroom 2, Kitchen, Bath, WC", prompt)
        self.assertIn('"checklist"', prompt)
        self.assertNotIn("{", prompt.split("Reply with ONLY")[0])      # no stray placeholders

    def test_other_types_keep_the_plain_reference(self):
        _, prompt = read("condo", {"rooms": ["KITCHEN"]})
        self.assertIn("Work in two steps", prompt)
        self.assertIn("For reference, this housing type usually has", prompt)
        self.assertNotIn('"checklist"', prompt)

    def test_every_hdb_layout_is_named_for_its_type(self):
        for key, layouts in app.HDB_LAYOUTS.items():
            self.assertIn(key, app.ROOM_CATALOGUE)
            self.assertGreaterEqual(len(layouts), 2)


class Checklist(unittest.TestCase):

    MODERN = {"readable": True, "layout": "A",
              "labels_read": ["LIVING / DINING", "MAIN BEDROOM", "BEDROOM", "KITCHEN",
                              "BATH / WC", "BATH / WC", "SERVICE YARD"],
              "checklist": {"Living/Dining": "LIVING / DINING", "Master Bedroom": "MAIN BEDROOM",
                            "Bedroom 2": "BEDROOM", "Kitchen": "KITCHEN",
                            "Master Bathroom": "BATH / WC", "Common Bathroom": "BATH / WC",
                            "Household Shelter": None, "Service Yard": "SERVICE YARD"},
              "rooms": ["LIVING / DINING", "MAIN BEDROOM", "BEDROOM", "KITCHEN",
                        "BATH / WC", "BATH / WC", "SERVICE YARD"],
              "summary": "A 3-room flat."}

    def test_a_template_room_not_on_the_plan_is_reported_not_added(self):
        result, _ = read("hdb_3room", self.MODERN)
        self.assertNotIn("Household Shelter", result["rooms"])
        self.assertIn("household shelter", result["summary"])
        self.assertIn("could not find on your plan", result["summary"])

    def test_a_full_match_adds_nothing_to_the_summary(self):
        reply = json.loads(json.dumps(self.MODERN))
        reply["checklist"]["Household Shelter"] = "HOUSEHOLD SHELTER"
        reply["rooms"].append("HOUSEHOLD SHELTER")
        result, _ = read("hdb_3room", reply)
        self.assertEqual(result["summary"], "A 3-room flat.")
        self.assertEqual(result["rooms"], ["Living / Dining", "Master Bedroom", "Bedroom 2",
                                           "Kitchen", "Master Bathroom", "Common Bathroom",
                                           "Service Yard", "Household Shelter"])

    def test_no_standard_layout_means_nothing_to_compare(self):
        self.assertEqual(app.template_rooms_missing(
            app.HDB_LAYOUTS["hdb_3room"], {"layout": "none", "checklist": {"Kitchen": None}}), [])
        self.assertEqual(app.template_rooms_missing(
            app.HDB_LAYOUTS["hdb_3room"], {"layout": "Z", "checklist": {}}), [])
        self.assertEqual(app.template_rooms_missing(None, {"layout": "A"}), [])

    def test_older_flat_keeps_bath_and_wc_apart(self):
        result, _ = read("hdb_3room", {
            "readable": True, "layout": "B",
            "checklist": {"Living Room": "LIVING ROOM", "Bedroom 1": "BEDROOM 1",
                          "Bedroom 2": "BEDROOM 2", "Kitchen": "KITCHEN", "Bath": "BATH",
                          "WC": "W.C.", "Balcony": "BALCONY"},
            "rooms": ["LIVING ROOM", "BEDROOM 1", "BEDROOM 2", "KITCHEN", "BATH", "W.C.", "BALCONY"]})
        self.assertEqual(result["rooms"], ["Living Room", "Bedroom 1", "Bedroom 2", "Kitchen",
                                           "Bathroom", "WC", "Balcony"])

    def test_unreadable_plan_still_raises(self):
        with self.assertRaises(ValueError):
            read("hdb_3room", {"readable": False, "rooms": []})


if __name__ == "__main__":
    unittest.main(verbosity=2)
