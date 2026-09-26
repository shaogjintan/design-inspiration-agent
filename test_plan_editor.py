#!/usr/bin/env python3
"""
FORMA — offline tests for page 2's plan editor: the trace it starts, the
homeowner's edge edits applied to it, and page 5 using the confirmed rooms
instead of tracing again. The model is stubbed; the store and uploads are
temporary.

Run:  python test_plan_editor.py
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import agent
import app
import clients

SRC_PLAN = Path("uploads/floorplans/ea48decd456145fc88b2acb6fa38c403_700-width.jpeg")
LABELS = ["Living / Dining", "Master Bedroom", "Bedroom 2", "Kitchen"]


def traced(labels=LABELS):
    """A trace shaped like read_plan_geometry's, in plan pixels."""
    rooms = {}
    for i, label in enumerate(labels):
        x = 200 + 70 * i
        rooms[label] = {"x": x, "y": 100, "w": 60, "h": 120,
                        "parts": [{"x": x, "y": 100, "w": 60, "h": 120}],
                        "doors": [{"wall": "bottom", "at": 0.5, "part": 0}]}
    return {"image_w": 700, "image_h": 450, "rooms": rooms,
            "outline": [{"x": 200, "y": 100, "w": 280, "h": 120}],
            "walkways": [], "missing": []}


@unittest.skipUnless(SRC_PLAN.exists(), "needs the sample floor plan in uploads/")
class PlanEditor(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        uploads = self.tmp / "uploads"
        (uploads / "floorplans").mkdir(parents=True)
        self.plan = str(uploads / "floorplans" / "plan.jpeg")
        shutil.copy(SRC_PLAN, self.plan)
        self.patches = [mock.patch.object(clients, "DATA_FILE", self.tmp / "data.json"),
                        mock.patch.object(app, "UPLOAD_FOLDER", uploads),
                        mock.patch.object(app, "call_llm",
                                          side_effect=AssertionError("no model calls"))]
        for p in self.patches:
            p.start()
        app.app.config["TESTING"] = True
        self.c = app.app.test_client()
        with self.c.session_transaction() as s:
            s["client_id"] = "a_test"
        clients.save_brief("a_test", {
            "step1": {"housing_type": "hdb_3room", "housing_type_label": "3-Room HDB",
                      "floor_size": "", "num_floors": "1", "space_notes": "",
                      "floor_plan_path": self.plan},
            "ai_rooms": list(LABELS), "ai_room_source": "floorplan",
            "requirements": {}, "agent_result": {"kept": True},
        })

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp)

    def state(self):
        return clients.load_brief("a_test")

    def save_trace(self):
        st = self.state()
        st["plan_geometry"] = app.stamp_plan_geometry(traced(), self.plan, LABELS)
        clients.save_brief("a_test", st)
        return st["plan_geometry"]

    def edit(self, rooms, frm=None):
        return json.dumps({"rooms": rooms, "from": frm or {}})

    def step2_form(self, plan_edit="", labels=LABELS):
        form = {"kept_rooms": labels, "project_notes": "", "plan_edit": plan_edit}
        for label in labels:
            form[f"{app.room_key(label)}_priority"] = "medium"
        return form

    # ── The page and the trace ────────────────────────────────────────────────
    def test_page_starts_the_trace_when_there_is_none(self):
        html = self.c.get("/step2").get_data(as_text=True)
        self.assertIn('id="plan-editor"', html)
        self.assertIn('data-status="pending"', html)
        self.assertIn("/step2/trace", html)
        self.assertIn('data-uid="Master Bedroom"', html)

    def test_trace_is_saved_once_and_then_reused(self):
        with mock.patch.object(app, "read_plan_geometry", return_value=traced()) as read:
            first = self.c.post("/step2/trace").get_json()
            again = self.c.post("/step2/trace").get_json()
        self.assertEqual(read.call_count, 1)
        self.assertTrue(first["ok"] and again["ok"])
        self.assertEqual(first["rooms"]["Kitchen"], [[410.0, 100.0, 60.0, 120.0]])
        geo = self.state()["plan_geometry"]
        self.assertEqual(geo["key"], app.plan_geometry_key(self.plan, LABELS))
        html = self.c.get("/step2").get_data(as_text=True)
        self.assertIn('data-status="ready"', html)
        self.assertIn('"walls"', html)                      # edges snap to real walls

    def test_a_failed_trace_is_remembered_for_the_page(self):
        with mock.patch.object(app, "read_plan_geometry", side_effect=ValueError("no")):
            self.assertFalse(self.c.post("/step2/trace").get_json()["ok"])
        self.assertIn('data-status="failed"', self.c.get("/step2").get_data(as_text=True))

    # ── Edits ─────────────────────────────────────────────────────────────────
    def test_moving_a_wall_is_saved_with_the_doors(self):
        self.save_trace()
        rooms = {l: app._parts_list(r) for l, r in traced()["rooms"].items()}
        rooms["Kitchen"] = [[410.0, 100.0, 80.0, 120.0]]        # right wall out 20px
        self.c.post("/step2", data=self.step2_form(self.edit(rooms)))
        st = self.state()
        kitchen = st["plan_geometry"]["rooms"]["Kitchen"]
        self.assertEqual(kitchen["w"], 80.0)
        self.assertEqual(kitchen["doors"], [{"wall": "bottom", "at": 0.5, "part": 0}])
        self.assertTrue(st["plan_geometry"]["edited"])
        self.assertNotIn("agent_result", st)

    def test_an_unchanged_plan_changes_nothing(self):
        self.save_trace()
        self.c.post("/step2", data=self.step2_form())           # settle requirements
        st = self.state()
        st["agent_result"] = {"kept": True}
        clients.save_brief("a_test", st)
        rooms = {l: app._parts_list(r) for l, r in traced()["rooms"].items()}
        self.c.post("/step2", data=self.step2_form(self.edit(rooms)))
        st = self.state()
        self.assertIn("agent_result", st)
        self.assertNotIn("edited", st["plan_geometry"])

    def test_a_renamed_room_keeps_its_place_and_doors(self):
        self.save_trace()
        labels = ["Living / Dining", "Master Bedroom", "Study", "Kitchen"]
        rooms = {l: app._parts_list(r) for l, r in traced()["rooms"].items()}
        rooms["Study"] = rooms.pop("Bedroom 2")
        self.c.post("/step2", data=self.step2_form(
            self.edit(rooms, {"Study": "Bedroom 2"}), labels=labels))
        geo = self.state()["plan_geometry"]
        self.assertIn("Study", geo["rooms"])
        self.assertNotIn("Bedroom 2", geo["rooms"])
        self.assertEqual(geo["rooms"]["Study"]["doors"][0]["wall"], "bottom")
        self.assertEqual(geo["key"], app.plan_geometry_key(self.plan, labels))

    def test_a_room_taken_off_the_plan_is_missing(self):
        self.save_trace()
        rooms = {l: app._parts_list(r) for l, r in traced()["rooms"].items()}
        del rooms["Kitchen"]
        self.c.post("/step2", data=self.step2_form(self.edit(rooms)))
        geo = self.state()["plan_geometry"]
        self.assertNotIn("Kitchen", geo["rooms"])
        self.assertEqual(geo["missing"], ["Kitchen"])

    def test_rooms_marked_out_by_hand_without_a_trace_are_kept(self):
        self.c.post("/step2", data=self.step2_form(self.edit(
            {"Kitchen": [[400, 90, 90, 130]], "Bedroom 2": [[300, 90, 90, 130]]})))
        geo = self.state()["plan_geometry"]
        self.assertEqual(set(geo["rooms"]), {"Kitchen", "Bedroom 2"})
        self.assertEqual(geo["key"], app.plan_geometry_key(self.plan, LABELS))
        self.assertIn('data-status="ready"', self.c.get("/step2").get_data(as_text=True))

    def test_edits_are_clamped_to_the_plan(self):
        geo = app.stamp_plan_geometry(traced(), self.plan, LABELS)
        new = app.apply_plan_edit(geo, self.edit({"Kitchen": [[-50, 400, 9000, 200]]}),
                                  LABELS, self.plan)
        p = new["rooms"]["Kitchen"]["parts"][0]
        self.assertGreaterEqual(p["x"], 0)
        self.assertLessEqual(p["x"] + p["w"], 700)
        self.assertLessEqual(p["y"] + p["h"], 450)
        # A sliver beside a room's part is dropped, never widened into a room.
        new = app.apply_plan_edit(geo, self.edit({"Kitchen": [[410, 100, 60, 120], [404, 100, 0.5, 120]]}),
                                  LABELS, self.plan)
        self.assertEqual(len(new["rooms"]["Kitchen"]["parts"]), 1)
        self.assertIsNone(app.apply_plan_edit(geo, "not json", LABELS, self.plan))

    # ── Page 5 ────────────────────────────────────────────────────────────────
    def test_page5_uses_the_confirmed_rooms_without_tracing(self):
        geo = self.save_trace()
        rooms = [{"key": app.room_key(l), "label": l} for l in LABELS]
        with mock.patch.object(app, "read_plan_geometry",
                               side_effect=AssertionError("traced again")), \
             mock.patch.object(app, "plan_furniture", return_value={}):
            out = agent._prepare_space(app, rooms, self.state()["step1"], {}, geo, None)
        self.assertTrue(out["geo_reused"])
        self.assertTrue(out["measured"]["kitchen"])

    def test_a_new_plan_drops_the_old_trace(self):
        self.save_trace()
        import io
        self.c.post("/step1", data={"housing_type": "hdb_3room", "floor_size": "", "num_floors": "1",
                                    "space_notes": "",
                                    "floor_plan": (io.BytesIO(b"\x89PNG\r\n\x1a\n other"), "p.png")},
                    content_type="multipart/form-data")
        self.assertNotIn("plan_geometry", self.state())


if __name__ == "__main__":
    unittest.main(verbosity=2)
