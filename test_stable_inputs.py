#!/usr/bin/env python3
"""
FORMA — offline tests that an unchanged submission keeps what was already
worked out: the room list (and its step-2 edits) stays unless the floor plan
changed, and the finished result stays unless an input changed. The model is
stubbed out; the store and uploads are temporary.

Run:  python test_stable_inputs.py
"""

import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app
import clients

EDITED_ROOMS = ["Living Room", "Master Bedroom", "Study", "Kitchen", "Master Bathroom"]
PLAN = b"\x89PNG\r\n\x1a\n plan one"


class Stable(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patches = [mock.patch.object(clients, "DATA_FILE", self.tmp / "data.json"),
                        mock.patch.object(app, "UPLOAD_FOLDER", self.tmp / "uploads"),
                        mock.patch.object(app, "call_llm",
                                          side_effect=AssertionError("no model calls"))]
        for p in self.patches:
            p.start()
        app.app.config["TESTING"] = True
        self.c = app.app.test_client()
        with self.c.session_transaction() as s:
            s["client_id"] = "a_test"

        plan = self.tmp / "plan.png"
        plan.write_bytes(PLAN)
        self.plan = str(plan)
        self.step1 = {"housing_type": "hdb_4room", "housing_type_label": app.HOUSING_LABELS["hdb_4room"],
                      "floor_size": "90", "num_floors": "1", "space_notes": "",
                      "floor_plan_path": self.plan}
        clients.save_brief("a_test", {
            "step1": dict(self.step1),
            "ai_rooms": list(EDITED_ROOMS), "ai_room_source": "floorplan",
            "requirements": {"living_room_prompt": "cosy", "project_notes": ""},
            "inspiration": {"design_style": "japandi", "colour_palette": "#F5F0EB|Warm Neutral",
                            "colour_hex": "#F5F0EB", "colour_name": "Warm Neutral",
                            "custom_colour": "", "inspo_paths": {},
                            "vibes": {}},
            "inspiration_analysis": {"kept": True},
            "rooms_summarised": True,
            "agent_result": {"kept": True},
        })

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp)

    def state(self):
        return clients.load_brief("a_test")

    def post_step1(self, plan_bytes=None, **changes):
        form = {k: v for k, v in self.step1.items()
                if k in ("housing_type", "floor_size", "num_floors", "space_notes")}
        form.update(changes)
        if plan_bytes is not None:
            form["floor_plan"] = (io.BytesIO(plan_bytes), "plan.png")
        return self.c.post("/step1", data=form, content_type="multipart/form-data")

    # ── Step 1 ────────────────────────────────────────────────────────────────
    def test_resubmitting_step1_keeps_rooms_and_result(self):
        r = self.post_step1()
        self.assertTrue(r.headers["Location"].endswith("/step2"))    # not re-read
        st = self.state()
        self.assertEqual(st["ai_rooms"], EDITED_ROOMS)
        self.assertEqual(st["ai_room_source"], "floorplan")
        self.assertIn("agent_result", st)
        self.assertIn("inspiration_analysis", st)

    def test_reuploading_the_same_plan_is_no_change(self):
        r = self.post_step1(plan_bytes=PLAN)
        self.assertTrue(r.headers["Location"].endswith("/step2"))
        st = self.state()
        self.assertEqual(st["step1"]["floor_plan_path"], self.plan)
        self.assertEqual(st["ai_rooms"], EDITED_ROOMS)
        self.assertIn("agent_result", st)
        # The duplicate copy is not left behind.
        self.assertEqual(list((self.tmp / "uploads").rglob("*.png")), [])

    def test_a_new_plan_rereads_the_rooms(self):
        r = self.post_step1(plan_bytes=b"\x89PNG\r\n\x1a\n a different plan")
        self.assertTrue(r.headers["Location"].endswith("/step1/reading"))
        st = self.state()
        self.assertNotEqual(st["step1"]["floor_plan_path"], self.plan)
        self.assertNotEqual(st["ai_room_source"], "floorplan")
        self.assertNotIn("agent_result", st)

    def test_other_step1_changes_keep_rooms_but_redo_the_result(self):
        self.post_step1(floor_size="110")
        st = self.state()
        self.assertEqual(st["step1"]["floor_size"], "110")
        self.assertEqual(st["ai_rooms"], EDITED_ROOMS)
        self.assertNotIn("agent_result", st)
        self.assertIn("inspiration_analysis", st)

    def test_with_a_plan_the_housing_type_does_not_reset_rooms(self):
        self.post_step1(housing_type="hdb_5room")
        self.assertEqual(self.state()["ai_rooms"], EDITED_ROOMS)

    def test_without_a_plan_a_new_housing_type_resets_rooms(self):
        st = self.state()
        st["step1"]["floor_plan_path"] = None
        st["ai_room_source"] = "housing_type_only"
        clients.save_brief("a_test", st)
        self.step1["floor_plan_path"] = None

        self.post_step1()                                       # unchanged
        self.assertEqual(self.state()["ai_rooms"], EDITED_ROOMS)
        self.post_step1(housing_type="hdb_3room")               # changed
        self.assertEqual(self.state()["ai_rooms"], app.ROOM_CATALOGUE["hdb_3room"])

    # ── Steps 2 and 3 ─────────────────────────────────────────────────────────
    def step2_form(self, **changes):
        form = {"kept_rooms": EDITED_ROOMS, "project_notes": ""}
        for room in EDITED_ROOMS:
            key = room.lower().replace(" ", "_")
            form[f"{key}_priority"] = "medium"
        form["living_room_prompt"] = "cosy"
        form.update(changes)
        return form

    def test_resubmitting_step2_keeps_the_result(self):
        self.c.post("/step2", data=self.step2_form())            # settles the saved shape
        st = self.state()
        st["agent_result"] = {"kept": True}
        st["rooms_summarised"] = True
        clients.save_brief("a_test", st)

        self.c.post("/step2", data=self.step2_form())
        st = self.state()
        self.assertIn("agent_result", st)
        self.assertIn("rooms_summarised", st)

        self.c.post("/step2", data=self.step2_form(living_room_prompt="bright"))
        self.assertNotIn("agent_result", self.state())

    def test_resubmitting_step3_keeps_the_result(self):
        form = {"design_style": "japandi", "colour_palette": "#F5F0EB|Warm Neutral"}
        self.c.post("/step3", data=form)                         # settles the saved shape
        st = self.state()
        st["agent_result"] = {"kept": True}
        st["inspiration_analysis"] = {"kept": True}
        clients.save_brief("a_test", st)

        r = self.c.post("/step3", data=form)
        self.assertTrue(r.headers["Location"].endswith("/step4"))
        st = self.state()
        self.assertIn("agent_result", st)
        self.assertIn("inspiration_analysis", st)

        self.c.post("/step3", data={**form, "design_style": "tropical"})
        self.assertNotIn("agent_result", self.state())

    def test_regenerate_still_redoes_it(self):
        self.c.post("/regenerate")
        self.assertNotIn("agent_result", self.state())


if __name__ == "__main__":
    unittest.main(verbosity=2)
