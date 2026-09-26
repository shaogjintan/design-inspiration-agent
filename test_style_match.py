#!/usr/bin/env python3
"""
FORMA — offline tests for step 4, style match (style_match.py and the routes
and prompts around it in app.py). The model is stubbed; no gateway calls, and
the project store is a temporary file, never data.json.

Run:  python test_style_match.py
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app
import clients
import style_match as S

ROOMS = [{"key": k, "label": l} for k, l in (
    ("living_room", "Living Room"), ("master_bedroom", "Master Bedroom"),
    ("bedroom_2", "Bedroom 2"), ("kitchen", "Kitchen"),
    ("master_bathroom", "Master Bathroom"), ("service_yard", "Service Yard"))]


class Library(unittest.TestCase):

    def test_library_loads_with_vocabulary(self):
        self.assertGreater(len(S.load_library()["images"]), 50)
        self.assertIn("Japandi", S.vocabulary()["style"])

    def test_clean_tags_keeps_only_the_vocabulary(self):
        tags = S.clean_tags({"style": ["japandi", "Wabi-sabi"], "palette_family": "Warm Neutral",
                             "materials": ["light wood", "oak", "light wood"],
                             "mood": ["calm", "cosy"], "layout": "enormous"})
        self.assertEqual(tags["style"], ["Japandi"])
        self.assertEqual(tags["palette_family"], "warm neutral")
        self.assertEqual(tags["materials"], ["light wood"])
        self.assertEqual(tags["mood"], "calm")
        self.assertNotIn("layout", tags)
        self.assertEqual(S.clean_tags("not a dict"), {})

    def test_default_theme_from_step_3(self):
        self.assertEqual(S.default_tags("japandi", "Cool Greige"),
                         {"style": ["Japandi"], "palette_family": "cool neutral"})
        boho = S.default_tags("bohemian", "Custom")
        self.assertNotIn("style", boho)                  # no bohemian set
        self.assertEqual(boho["texture"], "woven")
        self.assertTrue(S.style_gap("bohemian"))
        self.assertEqual(S.style_gap("japandi"), "")

    def test_rooms_map_to_library_rooms(self):
        self.assertEqual(S.library_rooms("Master Bedroom"), ["master bedroom"])
        self.assertEqual(S.library_rooms("Bedroom 2")[0], "secondary bedroom")
        self.assertEqual(S.library_rooms("Bedroom"), ["secondary bedroom", "master bedroom"])
        self.assertEqual(S.library_rooms("Common Bathroom"), ["bathroom"])
        self.assertEqual(S.library_rooms("Living / Dining"), ["living", "dining"])
        self.assertEqual(S.library_rooms("Service Yard"), [])
        self.assertEqual(S.library_rooms("Household Shelter"), [])


class Ranking(unittest.TestCase):

    def test_best_match_first_and_alternates_last(self):
        tags = {"style": ["industrial"], "palette_family": "monochrome"}
        refs = S.rank_for_room("Living Room", tags, "HDB", "Mid-range", count=6, alternates=2)
        self.assertEqual(len(refs), 6)
        self.assertTrue(all(r["room"] == "living" for r in refs))
        self.assertEqual(refs[0]["style"], "industrial")
        self.assertIn("industrial", refs[0]["match_why"])
        alts = [r for r in refs if r.get("alternate")]
        # Two industrial living rooms in the library: the rest are other styles.
        self.assertEqual(len(alts), 4)
        self.assertEqual(len({r["style"] for r in alts}), 4)      # varied
        self.assertEqual(refs[2:], alts)
        self.assertTrue(all(r["style"] != "industrial" for r in alts))
        self.assertEqual(refs[-1], alts[-1])

    def test_few_matches_are_topped_up_as_alternates(self):
        refs = S.rank_for_room("Bedroom 2", {"style": ["Japandi"]}, count=6)
        self.assertEqual(len(refs), 6)
        self.assertEqual(len({r["id"] for r in refs}), 6)
        self.assertEqual(refs[0]["style"], "Japandi")
        self.assertTrue(all(r.get("alternate") for r in refs if r["style"] != "Japandi"))

    def test_no_style_ranks_on_the_rest(self):
        refs = S.rank_for_room("Living Room", {"texture": "woven", "materials": ["rattan"]})
        self.assertTrue(refs)
        self.assertFalse(any(r.get("alternate") for r in refs))
        self.assertIn("rattan", refs[0]["materials"])

    def test_uncovered_room_gets_nothing(self):
        self.assertEqual(S.rank_for_room("Service Yard", {"style": ["Japandi"]}), [])

    def test_picks_are_described_in_full(self):
        img = S.load_library()["images"][0]
        text = S.picks_summary({"living_room": [img["id"], "FL-NOPE"]},
                               {"living_room": "Living Room"})["living_room"]
        self.assertIn("Living Room", text)
        self.assertIn(img["style"], text)
        self.assertIn(img["palette"]["family"], text)
        self.assertEqual(S.picks_summary({"x": ["FL-NOPE"]}, {}), {})


class Extraction(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.photo = self.tmp / "a.jpg"
        self.photo.write_bytes(b"\xff\xd8\xff fake jpeg")
        self.insp = {"design_style": "japandi", "colour_name": "Warm Neutral",
                     "inspo_paths": {"overall": [str(self.photo)],
                                     "bedroom_2": [str(self.photo)]}}

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_no_photos_uses_the_default_theme_without_a_call(self):
        with mock.patch.object(app, "call_llm") as llm:
            p = app.extract_style({"design_style": "industrial", "colour_name": "Midnight"}, ROOMS)
        llm.assert_not_called()
        self.assertEqual(p["source"], "default")
        self.assertEqual(p["overall"], {"style": ["industrial"], "palette_family": "bold"})

    def test_photos_are_read_into_the_vocabulary(self):
        reply = json.dumps({
            "overall": {"style": ["industrial", "made-up"], "palette_family": "monochrome",
                        "materials": ["concrete", "metal"], "mood": "dramatic"},
            "rooms": {"bedroom_2": {"style": ["tropical"], "materials": ["rattan"]},
                      "not_a_room": {"style": ["Japandi"]}},
            "summary": "Raw concrete and black metal throughout."})
        with mock.patch.object(app, "call_llm", return_value=reply) as llm:
            p = app.extract_style(self.insp, ROOMS)
        kwargs = llm.call_args.kwargs
        self.assertEqual(kwargs["images_sent"], 2)
        self.assertFalse(kwargs["fallback_to_mock"])
        msg = llm.call_args.args[0][0]
        self.assertEqual(len(msg["images"]), 2)
        self.assertIn("Bedroom 2 (room key bedroom_2)", msg["content"])
        self.assertIn("Japandi | modern minimalist", msg["content"])   # the vocabulary
        self.assertNotIn("{MANIFEST}", msg["content"])

        self.assertEqual(p["source"], "images")
        # The photos lead; the style picked in step 3 stays behind them.
        self.assertEqual(p["overall"]["style"], ["industrial", "Japandi"])
        self.assertEqual(p["overall"]["palette_family"], "monochrome")
        self.assertEqual(set(p["rooms"]), {"bedroom_2"})
        self.assertEqual(p["rooms"]["bedroom_2"]["style"], ["tropical"])
        self.assertEqual(p["rooms"]["bedroom_2"]["palette_family"], "monochrome")
        self.assertEqual(p["key"], app.style_profile_key(self.insp, ROOMS))

    def test_a_failed_read_falls_back_to_the_chosen_style(self):
        for effect in (RuntimeError("down"), app.VisionUnavailable("dropped")):
            with mock.patch.object(app, "call_llm", side_effect=effect):
                p = app.extract_style(self.insp, ROOMS)
            self.assertEqual(p["source"], "default")
            self.assertEqual(p["overall"]["style"], ["Japandi"])
            self.assertIn("could not read your photos", p["summary"])
        with mock.patch.object(app, "call_llm", return_value="no json here"):
            self.assertEqual(app.extract_style(self.insp, ROOMS)["source"], "default")
        with mock.patch.object(app, "call_llm", return_value='{"overall": {"style": ["gothic"]}}'):
            self.assertEqual(app.extract_style(self.insp, ROOMS)["source"], "default")

    def test_key_follows_photo_contents_and_style(self):
        k1 = app.style_profile_key(self.insp, ROOMS)
        self.assertEqual(k1, app.style_profile_key(dict(self.insp), ROOMS))
        self.photo.write_bytes(b"\xff\xd8\xff another")
        k2 = app.style_profile_key(self.insp, ROOMS)
        self.assertNotEqual(k1, k2)
        self.assertNotEqual(k2, app.style_profile_key({**self.insp, "design_style": "tropical"}, ROOMS))


class Prompts(unittest.TestCase):

    def test_brief_and_room_concept_carry_the_picks(self):
        img = S.load_library()["images"][0]
        with mock.patch.object(app, "call_llm", return_value="<h4>x</h4>") as llm:
            app.generate_design_brief({"rooms": ROOMS[:1], "design_style": "japandi",
                                       "style_picks": {"living_room": [img["id"]]}})
        prompt = llm.call_args.args[0][0]["content"]
        self.assertIn("REFERENCE PHOTOS THE HOMEOWNER PICKED", prompt)
        self.assertIn(S.describe(img), prompt)

        with mock.patch.object(app, "call_llm", return_value="<h4>x</h4>") as llm:
            app.generate_design_brief({"rooms": ROOMS[:1], "design_style": "japandi"})
        self.assertNotIn("REFERENCE PHOTOS THE HOMEOWNER PICKED",
                         llm.call_args.args[0][0]["content"])

        with mock.patch.object(app, "call_llm", return_value="A room.") as llm:
            app.generate_room_concept(ROOMS[0], "japandi", "Warm Neutral", "",
                                      picked_refs="Industrial living; concrete")
        self.assertIn("REFERENCE PHOTOS PICKED FOR THIS ROOM", llm.call_args.args[0][0]["content"])


class Routes(unittest.TestCase):
    """The page itself, against a throwaway store."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patch = mock.patch.object(clients, "DATA_FILE", self.tmp / "data.json")
        self.patch.start()
        app.app.config["TESTING"] = True
        self.c = app.app.test_client()
        with self.c.session_transaction() as s:
            s["client_id"] = "a_test"
        clients.save_brief("a_test", {
            "step1": {"housing_type": "hdb_3room", "housing_type_label": "HDB 3-Room"},
            "requirements": {"living_room_budget": "mid"},
            "inspiration": {"design_style": "scandinavian", "colour_name": "Warm Neutral",
                            "inspo_paths": {}},
            "agent_result": {"stale": True},
        })

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp)

    def state(self):
        return clients.load_brief("a_test")

    def test_step3_now_leads_to_step4(self):
        with self.c.session_transaction() as s:
            s["client_id"] = "a_test"
        r = self.c.post("/step3", data={"design_style": "scandinavian",
                                        "colour_palette": "#F5F0EB|Warm Neutral"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/step4"))

    def test_page_without_photos_shows_the_default_theme(self):
        with mock.patch.object(app, "call_llm") as llm:
            r = self.c.get("/step4")
        llm.assert_not_called()
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Your style: Scandinavian", html)
        self.assertIn('name="pick_living_room"', html)
        self.assertNotIn('name="pick_service_yard"', html)
        self.assertIn("/ Unsplash", html)
        self.assertIn("They are not your home", html)
        self.assertEqual(self.state()["style_profile"]["source"], "default")

    def test_page_with_photos_asks_for_the_read_first(self):
        photo = self.tmp / "p.jpg"
        photo.write_bytes(b"\xff\xd8\xff x")
        st = self.state()
        st["inspiration"]["inspo_paths"] = {"overall": [str(photo)]}
        clients.save_brief("a_test", st)
        html = self.c.get("/step4").get_data(as_text=True)
        self.assertIn("Reading your photos", html)
        self.assertIn("/step4/extract", html)
        reply = json.dumps({"overall": {"style": ["tropical"]}, "rooms": {}, "summary": "Green."})
        with mock.patch.object(app, "call_llm", return_value=reply) as llm:
            self.assertTrue(self.c.post("/step4/extract").get_json()["ok"])
            self.assertTrue(self.c.post("/step4/extract").get_json()["cached"])
        self.assertEqual(llm.call_count, 1)                          # cached after
        html = self.c.get("/step4").get_data(as_text=True)
        self.assertIn("What your photos share", html)
        self.assertIn("Green.", html)

    def test_picks_are_saved_and_the_brief_redone(self):
        lib_ids = [r["id"] for r in S.rank_for_room("Living Room", {"style": ["Scandinavian"]})]
        r = self.c.post("/step4", data={"pick_living_room": lib_ids[:5] + ["FL-NOPE"],
                                        "pick_bedroom_2": [lib_ids[0]]})
        self.assertTrue(r.headers["Location"].endswith("/step5"))
        st = self.state()
        self.assertEqual(st["style_picks"]["living_room"], lib_ids[:3])   # capped
        self.assertIn("bedroom_2", st["style_picks"])
        self.assertNotIn("agent_result", st)

        # Same picks again: nothing to redo.
        st["agent_result"] = {"kept": True}
        clients.save_brief("a_test", st)
        self.c.post("/step4", data={"pick_living_room": lib_ids[:3],
                                    "pick_bedroom_2": [lib_ids[0]]})
        self.assertIn("agent_result", self.state())

    def test_picks_show_on_the_final_page_and_in_the_export(self):
        ids = [r["id"] for r in S.rank_for_room("Living Room", {"style": ["Scandinavian"]})][:2]
        st = self.state()
        st["style_picks"] = {"living_room": ids + ["FL-NOPE"]}
        st["agent_result"] = {"inspiration_analysis": {}, "conflicts": [], "ai_brief": "<p>x</p>",
                              "room_results": [{"key": "living_room", "label": "Living Room",
                                                "concept": "c", "visual": "", "items": []}],
                              "floor_plan_svg": "", "agent_trace": [], "needs_input": False}
        clients.save_brief("a_test", st)
        html = self.c.get("/step5").get_data(as_text=True)
        # In their own section, grouped by room — not inside the room cards.
        refs = html[html.index('id="references"'):html.index('<!-- 2D Floor Plan -->')]
        self.assertEqual(refs.count('ref-photo--library'), 2)
        self.assertIn("Living Room", refs)
        self.assertIn("/step4#style-living_room", refs)
        cards = html[html.index('id="rooms"'):html.index('id="references"')]
        self.assertNotIn('ref-photo', cards)
        self.assertIn("not your home", html)
        text = self.c.get("/export-brief").get_data(as_text=True)
        self.assertEqual(text.count("Picked      :"), 2)
        self.assertNotIn("Sonnet", text)

    def test_wait_shows_a_gallery_of_the_references(self):
        ids = [r["id"] for r in S.rank_for_room("Living Room", {"style": ["Scandinavian"]})][:2]
        st = self.state()
        st.pop("agent_result")
        st["style_picks"] = {"living_room": ids}
        clients.save_brief("a_test", st)
        html = self.c.get("/step5").get_data(as_text=True)
        self.assertIn('class="gallery"', html)
        lib = S.images_by_id()
        for i in ids:                                   # the picks come first, twice for the loop
            self.assertEqual(html.count(lib[i]["image"]["thumb_url"].replace("&", "&amp;")), 2)
        # Topped up from the library to at least four photos.
        self.assertGreaterEqual(html.count('class="gallery__item"'), 8)

    def test_results_moved_to_step5(self):
        st = self.state()
        st.pop("agent_result")
        clients.save_brief("a_test", st)
        r = self.c.get("/step5")
        self.assertEqual(r.status_code, 200)
        self.assertRegex(r.get_data(as_text=True), r"nav__step--active\s*\">\s*<span class=\"nav__step-num\">5<")
        self.assertEqual(self.c.get("/step5/progress").status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
