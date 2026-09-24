"""
FORMA — Design Inspiration Agent
agent.py: The reasoning loop.

This module is the BRAIN of FORMA. It does NOT handle HTTP, sessions, or
templates — that stays in app.py. It does NOT call the LLM directly — that
stays in the tool functions in app.py.

What it DOES:
  1. Receive the current project state as plain dicts.
  2. Decide what needs to be done (plan).
  3. Call the appropriate tools in order.
  4. Evaluate the results and decide what's next.
  5. Return a structured result: brief, room concepts, conflicts, agent trace.

The reasoning loop:
    OBSERVE  — read project state, check what exists and what's missing
    REASON   — determine which tools to run and in what order
    ACT      — call tools, collect results
    EVALUATE — check quality, detect conflicts
    RESPOND  — return result + any clarification questions

This loop runs end-to-end in run_agent(). app.py calls run_agent() from
the step4 route; it no longer calls each AI function individually.

Agent trace format (each entry):
    {
      "timestamp":  ISO string,
      "step":       human label shown in the UI trace,
      "action":     tool/function name,
      "reason":     WHY the agent decided to do this,
      "status":     "success" | "skipped" | "failed" | "needs_input",
      "summary":    short result description (shown in UI),
      "confidence": "high" | "medium" | "low" | None,
    }
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import furniture_layout

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trace_entry(step: str, action: str, reason: str,
                 status: str, summary: str,
                 confidence: str | None = None) -> dict:
    return {
        "timestamp":  _now(),
        "step":       step,
        "action":     action,
        "reason":     reason,
        "status":     status,
        "summary":    summary,
        "confidence": confidence,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main agent entry point
# ─────────────────────────────────────────────────────────────────────────────

def _prepare_space(_app, rooms, step1, requirements,
                   existing_geometry, existing_furniture) -> dict:
    """Trace the plan, size the rooms, and plan their furniture. Runs in the
    background while the inspiration analysis does; never raises — failures
    come back as errors for the caller to report and fall back from."""
    out = {"geometry": None, "geo_reused": False, "geo_error": None,
           "px_per_m": None, "sizes": {}, "measured": {}, "outline": {},
           "furniture": None, "furn_key": None, "furn_error": None}
    plan_path = step1.get("floor_plan_path")
    labels = [r["label"] for r in rooms]

    if plan_path:
        key = _app.plan_geometry_key(plan_path, labels)
        if existing_geometry and existing_geometry.get("key") == key:
            out["geometry"], out["geo_reused"] = existing_geometry, True
        else:
            try:
                geo = _app.read_plan_geometry(
                    plan_path, labels, housing_label=step1.get("housing_type_label", ""))
                geo["key"] = key
                out["geometry"] = geo
            except Exception as e:                    # noqa: BLE001
                out["geo_error"] = e

    geo = out["geometry"]
    if geo:
        # The plan's scale, most trustworthy first: the floor area the
        # homeowner gave; the standard furniture drawn on the plan itself;
        # a typical flat of this type; typical rooms of these kinds.
        m = None
        if step1.get("floor_size"):
            m = _app.plan_metres_per_px(geo, step1["floor_size"])
        if not m:
            m = geo.get("m_per_px_ref")
        if not m:
            m = _app.plan_metres_per_px(geo, _app.TYPICAL_FLOOR_SQM.get(step1.get("housing_type")))
        if not m:
            # No floor area to scale by: scale so the traced rooms add up to
            # what rooms of their kinds typically measure.
            typical = sum(furniture_layout.typical_room_size(l)[0]
                          * furniture_layout.typical_room_size(l)[1] for l in geo["rooms"])
            px = sum(_app.union_area(_app.room_parts(g)) for g in geo["rooms"].values())
            m = (typical / px) ** 0.5 if px else None
        out["px_per_m"] = m
        geo["m_per_px"] = m                  # for drawing doors at their real width

    for room in rooms:
        g = (geo or {}).get("rooms", {}).get(room["label"])
        m = out["px_per_m"]
        if g and m:
            main = _app._main_part(g)
            out["sizes"][room["key"]] = (main["w"] * m, main["h"] * m)
            out["measured"][room["key"]] = True
            # The room's outline in metres, from its own top-left: its bounding
            # box, and its parts largest first for the layout to fill in turn.
            parts = _app.split_into_rects(_app.room_parts(g), wide=3.0 / m)
            doors = []
            for door in g.get("doors") or []:
                src = _app.room_parts(g)
                px, py = _app.door_point(src[door["part"]] if door["part"] < len(src) else src[0], door)
                doors.append({"point": ((px - g["x"]) * m, (py - g["y"]) * m),
                              "wall": door["wall"], "width": _app.door_width_m(room["label"])})
            out["outline"][room["key"]] = {
                "W": g["w"] * m, "D": g["h"] * m,
                "parts": [((p["x"] - g["x"]) * m, (p["y"] - g["y"]) * m, p["w"] * m, p["h"] * m)
                          for p in parts[:3]],
                "doors": doors,
            }
        else:
            w, d = furniture_layout.typical_room_size(room["label"])
            out["sizes"][room["key"]] = (w, d)
            out["measured"][room["key"]] = False
            # No plan to read a door off: one door, where the drawing shows it.
            drawn = dict(furniture_layout.DEFAULT_DOOR)
            out["outline"][room["key"]] = {
                "W": w, "D": d, "parts": [(0.0, 0.0, w, d)],
                "doors": [{"point": (drawn["at"] * w, d), "wall": drawn["wall"],
                           "width": _app.door_width_m(room["label"])}],
                "doors_drawn": [drawn],
            }

    rooms_info = [{
        "key":         r["key"],
        "label":       r["label"],
        "size_m":      [round(v, 1) for v in out["sizes"][r["key"]]],
        "ticked":      list(requirements.get(f"{r['key']}_items", []) or []),
        "description": (requirements.get(f"{r['key']}_prompt") or "").strip(),
        "avoid":       (requirements.get(f"{r['key']}_constraints") or "").strip(),
    } for r in rooms]
    # Overall notes carry applied refinements ("add a piano to the living
    # room"), so they plan the furniture too, and a new one re-plans it.
    notes = (requirements.get("project_notes") or "").strip()
    fkey = _app.furniture_key(rooms_info, notes)
    out["furn_key"] = fkey
    if existing_furniture and existing_furniture.get("key") == fkey:
        out["furniture"] = existing_furniture.get("rooms") or {}
    else:
        try:
            out["furniture"] = _app.plan_furniture(rooms_info, notes)
        except Exception as e:                        # noqa: BLE001
            out["furn_error"] = e
    return out


def run_agent(
    step1: dict,
    requirements: dict,
    inspiration: dict,
    rooms: list[dict],
    existing_inspiration_analysis: dict | None,
    existing_conflicts: list[dict] | None,
    existing_trace: list[dict] | None,
    force_reanalyse: bool = False,
    existing_plan_geometry: dict | None = None,
    existing_furniture_plan: dict | None = None,
) -> dict:
    """
    Run the FORMA reasoning loop over the current project state.

    Parameters
    ----------
    step1                       : session["step1"]
    requirements                : session["requirements"]
    inspiration                 : session["inspiration"]
    rooms                       : list of room dicts from get_rooms_for_type()
    existing_inspiration_analysis: session.get("inspiration_analysis") — reused
                                  if still valid and force_reanalyse is False
    existing_conflicts          : session.get("conflicts") — resolved decisions
                                  are preserved across runs
    existing_trace              : session.get("agent_trace") — appended to, not
                                  replaced, so history is preserved
    force_reanalyse             : if True, re-run inspiration analysis even if a
                                  cached result exists (e.g. homeowner uploaded
                                  new images)
    existing_plan_geometry      : session.get("plan_geometry") — the last plan
                                  trace, reused while the plan file and room
                                  list are unchanged
    existing_furniture_plan     : session.get("furniture_plan") — the last
                                  furniture list, reused while rooms, sizes
                                  and requirements are unchanged

    Returns
    -------
    {
      "inspiration_analysis": dict,
      "conflicts":            list[dict],
      "ai_brief":             str (HTML),
      "room_results":         list[dict],
      "floor_plan_svg":       str,
      "agent_trace":          list[dict],
      "needs_input":          bool,   # True if open conflicts exist
    }
    """
    # Import app tools here to avoid circular imports at module load time.
    # agent.py is pure logic; app.py owns the tool implementations.
    import app as _app

    trace: list[dict] = list(existing_trace or [])

    # ─────────────────────────────────────────────────────────────────────────
    # OBSERVE: What do we know about this project?
    # ─────────────────────────────────────────────────────────────────────────
    housing_type   = step1.get("housing_type", "")
    floor_size     = step1.get("floor_size", "")
    floor_plan_path = step1.get("floor_plan_path")
    has_floor_plan  = bool(floor_plan_path)

    inspo_paths     = inspiration.get("inspo_paths") or {}
    total_images    = sum(
        len([p for p in (paths or []) if p])
        for paths in inspo_paths.values()
    )
    has_images = total_images > 0

    trace.append(_trace_entry(
        step    = "Loaded project memory",
        action  = "load_project_state",
        reason  = "Agent starts by reading the current project state.",
        status  = "success",
        summary = (
            f"Housing: {step1.get('housing_type_label', housing_type)}, "
            f"{len(rooms)} rooms, "
            f"floor plan: {'yes' if has_floor_plan else 'no'}, "
            f"inspiration images: {total_images}."
        ),
    ))

    # ─────────────────────────────────────────────────────────────────────────
    # REASON: Where the room list came from
    # ─────────────────────────────────────────────────────────────────────────
    # The rooms are the homeowner's own confirmed list, seeded from the housing
    # type in step 1 without a model call. The floor plan is read below, as part
    # of the single analysis pass, and can flag mismatches but never rewrites
    # the list the homeowner already wrote requirements against.
    trace.append(_trace_entry(
        step    = f"Working from {len(rooms)} confirmed spaces",
        action  = "load_room_list",
        reason  = "The homeowner confirmed the room list in step 2.",
        status  = "success",
        summary = (
            f"{len(rooms)} spaces, seeded from the housing type catalogue"
            + (" — the uploaded floor plan is read in the analysis below."
               if has_floor_plan else " (no floor plan uploaded).")
        ),
        confidence = "medium",
    ))

    # Tracing the plan and planning the furniture need only the plan, the
    # rooms and the requirements, and together take the best part of half a
    # minute. Start them now, alongside the analysis, and collect them where
    # the drawings need them.
    pool = ThreadPoolExecutor(max_workers=1)
    space_future = pool.submit(_prepare_space, _app, rooms, step1, requirements,
                               existing_plan_geometry, existing_furniture_plan)
    pool.shutdown(wait=False)

    # ─────────────────────────────────────────────────────────────────────────
    # REASON + ACT: Inspiration analysis
    # ─────────────────────────────────────────────────────────────────────────
    inspo_analysis = existing_inspiration_analysis or {}

    # Decide whether to (re-)run the analysis
    # Re-run only if:
    # - force_reanalyse is explicitly requested, OR
    # - there is no analysis at all, OR
    # - there are real images on disk but the cached analysis shows 0 images
    #   (meaning analysis ran before images were uploaded)
    cached_image_count = inspo_analysis.get("image_count", 0) if inspo_analysis else 0
    images_added_since_cache = (total_images > 0 and cached_image_count == 0)

    should_analyse = (
        force_reanalyse
        or not inspo_analysis
        or images_added_since_cache
    )

    if should_analyse:
        reason = (
            "New inspiration images uploaded — running visual analysis."
            if (has_images and (not inspo_analysis or force_reanalyse))
            else "No prior inspiration analysis found — running now."
        )
        try:
            inspo_analysis = _app.analyse_inspiration(
                inspiration, rooms, step1=step1, requirements=requirements,
            )
            read_plan = inspo_analysis.get("read_floor_plan")
            trace.append(_trace_entry(
                step    = (
                    f"Analysed {'the floor plan and ' if read_plan else ''}"
                    f"{total_images} inspiration image{'s' if total_images != 1 else ''}"
                ),
                action  = "analyse_inspiration",
                reason  = reason,
                status  = "success",
                summary = inspo_analysis.get("summary", ""),
                confidence = inspo_analysis.get("confidence"),
            ))
            for mismatch in inspo_analysis.get("room_list_mismatches", []):
                trace.append(_trace_entry(
                    step    = "Floor plan differs from the confirmed room list",
                    action  = "flag_room_mismatch",
                    reason  = "The homeowner's room list stands — this is flagged, not applied.",
                    status  = "success",
                    summary = mismatch,
                    confidence = inspo_analysis.get("confidence"),
                ))
        except Exception as e:
            logger.warning(f"Inspiration analysis failed: {e}")
            inspo_analysis = _app._inspiration_analysis_fallback(
                inspiration.get("design_style", ""),
                inspiration.get("colour_name", ""),
                inspiration.get("custom_colour", ""),
                inspiration.get("vibes", {}),
                total_images,
            )
            trace.append(_trace_entry(
                step    = "Inspiration analysis — fallback used",
                action  = "analyse_inspiration",
                reason  = reason,
                status  = "failed",
                summary = f"Analysis failed ({e}). Using text-based fallback.",
                confidence = "low",
            ))
    else:
        trace.append(_trace_entry(
            step    = "Inspiration analysis (cached)",
            action  = "analyse_inspiration",
            reason  = "Inspiration analysis is current — reusing cached result.",
            status  = "skipped",
            summary = inspo_analysis.get("summary", ""),
            confidence = inspo_analysis.get("confidence"),
        ))

    # Log extracted patterns
    styles_found = inspo_analysis.get("dominant_styles", [])
    outliers     = inspo_analysis.get("possible_outliers", [])
    if styles_found:
        trace.append(_trace_entry(
            step    = f"Extracted {len(styles_found)} recurring pattern{'s' if len(styles_found) != 1 else ''}",
            action  = "extract_patterns",
            reason  = "Summarise the visual characteristics for the brief.",
            status  = "success",
            summary = f"Styles: {', '.join(styles_found[:3])}. "
                      + (f"Outliers noted: {', '.join(outliers[:2])}." if outliers else "No outliers."),
            confidence = inspo_analysis.get("confidence"),
        ))

    # ─────────────────────────────────────────────────────────────────────────
    # REASON + ACT: Conflict detection
    # ─────────────────────────────────────────────────────────────────────────
    existing_by_id = {c["id"]: c for c in (existing_conflicts or [])}

    try:
        all_detected = _app.detect_conflicts(
            step1, requirements, inspiration, inspo_analysis, rooms
        )
    except Exception as e:
        logger.warning(f"Conflict detection failed: {e}")
        all_detected = []

    # Merge: preserve resolved decisions, absorb new conflicts
    merged_conflicts: list[dict] = []
    for c in all_detected:
        if c["id"] in existing_by_id:
            merged_conflicts.append(existing_by_id[c["id"]])
        else:
            merged_conflicts.append(c)

    open_conflicts   = [c for c in merged_conflicts if not c.get("resolved")]
    closed_conflicts = [c for c in merged_conflicts if c.get("resolved")]

    if open_conflicts:
        conflict_titles = "; ".join(c["title"] for c in open_conflicts[:3])
        trace.append(_trace_entry(
            step    = f"Found {len(open_conflicts)} decision{'s' if len(open_conflicts) != 1 else ''} that need{'s' if len(open_conflicts) == 1 else ''} you",
            action  = "detect_conflicts",
            reason  = "Before generating the brief, check for unresolved ambiguities.",
            status  = "needs_input",
            summary = conflict_titles,
        ))
    else:
        if all_detected:
            # All previously detected conflicts are resolved
            trace.append(_trace_entry(
                step    = "All conflicts resolved",
                action  = "detect_conflicts",
                reason  = "Checking for unresolved ambiguities.",
                status  = "success",
                summary = f"{len(closed_conflicts)} homeowner decision(s) incorporated.",
            ))
        else:
            trace.append(_trace_entry(
                step    = "No conflicts detected",
                action  = "detect_conflicts",
                reason  = "Checking for unresolved ambiguities before generating the brief.",
                status  = "success",
                summary = "Project inputs are consistent — proceeding to brief generation.",
            ))

    # ─────────────────────────────────────────────────────────────────────────
    # EVALUATE: Should we generate the brief now, or pause for homeowner input?
    #
    # We always generate the brief — even with open conflicts — so the
    # homeowner sees something useful. We note the outstanding conflicts in the
    # trace and surface them prominently in the UI above the brief.
    # ─────────────────────────────────────────────────────────────────────────
    needs_input = bool(open_conflicts)

    # ─────────────────────────────────────────────────────────────────────────
    # ACT: Generate design brief
    # ─────────────────────────────────────────────────────────────────────────

    # Build a project dict that includes all decisions made so far
    decisions_text = ""
    if closed_conflicts:
        decisions_text = "\n".join(
            f"- {c['title']}: Homeowner chose → {c['decision']}"
            for c in closed_conflicts
        )

    project_for_brief = {
        **step1,
        **inspiration,
        "rooms":               rooms,
        "inspiration_analysis": inspo_analysis,
        "homeowner_decisions":  decisions_text,
    }
    project_for_brief.update(requirements)

    try:
        ai_brief = _app.generate_design_brief(project_for_brief)
        trace.append(_trace_entry(
            step    = "Generated design brief",
            action  = "generate_design_direction",
            reason  = (
                "All available information has been analysed. Generating the "
                "overall design direction, incorporating homeowner decisions."
                if closed_conflicts
                else "Generating overall design direction."
            ),
            status  = "success",
            summary = "Design brief generated successfully.",
        ))
    except Exception as e:
        logger.warning(f"Brief generation failed: {e}")
        ai_brief = "<p>Brief generation encountered an error. Please regenerate.</p>"
        trace.append(_trace_entry(
            step    = "Design brief — error",
            action  = "generate_design_direction",
            reason  = "Generating overall design direction.",
            status  = "failed",
            summary = str(e),
        ))

    # ─────────────────────────────────────────────────────────────────────────
    # ACT: The plan trace and the furniture (started at the top)
    # ─────────────────────────────────────────────────────────────────────────
    # Any trace failure leaves plan_geometry None and the drawings fall back
    # to the schematic — a wrong plan is worse than an honest diagram. A
    # furniture failure falls back to the ticked items at standard sizes.
    space = space_future.result()
    plan_geometry = space["geometry"]
    px_per_m = space["px_per_m"]
    if has_floor_plan:
        if space["geo_reused"]:
            trace.append(_trace_entry(
                step    = "Reused the floor plan trace",
                action  = "trace_floor_plan",
                reason  = "Same plan and room list as the last run.",
                status  = "success",
                summary = f"{len(plan_geometry['rooms'])} of {len(rooms)} rooms located.",
            ))
        elif plan_geometry:
            missing = plan_geometry["missing"]
            trace.append(_trace_entry(
                step    = "Traced the floor plan",
                action  = "trace_floor_plan",
                reason  = "Find each labelled room on the plan and fit them together.",
                status  = "success",
                summary = (f"{len(plan_geometry['rooms'])} of {len(rooms)} rooms located"
                           + (f"; not found: {', '.join(missing)}." if missing else ".")),
            ))
        else:
            logger.warning(f"Floor plan trace failed: {space['geo_error']}")
            trace.append(_trace_entry(
                step    = "Floor plan trace — fell back to schematic",
                action  = "trace_floor_plan",
                reason  = "Find each labelled room on the plan and fit them together.",
                status  = "failed",
                summary = f"{str(space['geo_error'])[:120]}. Drawing a schematic layout instead.",
            ))

    furniture = space["furniture"]
    layouts: dict[str, dict] = {}
    for room in rooms:
        key = room["key"]
        ticked = requirements.get(f"{key}_items", []) or []
        outline = space["outline"][key]
        if furniture is not None:
            pieces = furniture_layout.clean_pieces(furniture.get(key), ticked)
        else:
            pieces = furniture_layout.pieces_from_names(ticked)
        if not pieces:
            # Nothing chosen: the essentials for a room of its kind.
            pieces = furniture_layout.pieces_from_names(
                [g["label"] for g in _app._items_to_glyphs([], room["label"])])
        layout = furniture_layout.place_parts(outline["parts"], pieces, outline.get("doors", []))
        layout.update(W=outline["W"], D=outline["D"], measured=space["measured"][key],
                      doors_drawn=outline.get("doors_drawn", []))
        layouts[key] = layout

    placed = sum(len(l["placed"]) for l in layouts.values())
    described = sum(1 for l in layouts.values() for q in l["placed"]
                    if q.get("source") == "described")
    no_fit = [f"{name} ({room['label']})" for room in rooms
              for name in layouts[room["key"]]["skipped"]]
    trace.append(_trace_entry(
        step    = ("Laid out the furniture" if furniture is not None
                   else "Laid out the furniture — standard sizes"),
        action  = "plan_furniture",
        reason  = ("Size each piece the homeowner ticked or described, then place it "
                   "by general design guides: clearances, walkways, what faces what."),
        status  = "success" if furniture is not None else "failed",
        summary = (f"{placed} pieces placed"
                   + (f", {described} read from their descriptions" if described else "")
                   + (f"; did not fit: {', '.join(no_fit)}" if no_fit else "")
                   + ("." if furniture is not None
                      else f". Model unavailable ({str(space['furn_error'])[:80]}) — "
                           "ticked items at standard sizes.")),
    ))

    # ─────────────────────────────────────────────────────────────────────────
    # ACT: Generate per-room concepts
    # ─────────────────────────────────────────────────────────────────────────
    room_results: list[dict] = []
    room_errors = 0

    for i, room in enumerate(rooms):
        key = room["key"]
        room_inspo_note = inspo_analysis.get("room_specific", {}).get(key, "")
        # A room the homeowner gave references to but that came back without a
        # direction means the analysis keyed it under a name we did not match.
        # That used to fail silently and the concept fell back to the style label.
        if not room_inspo_note and (inspiration.get("inspo_paths") or {}).get(key):
            logger.warning(
                "No direction for %s though it has its own references — "
                "analysis returned keys %s",
                key, list(inspo_analysis.get("room_specific", {}))
            )
        try:
            concept = _app.generate_room_concept(
                {**room, "items_selected": requirements.get(f"{key}_items", [])},
                style           = inspiration.get("design_style", ""),
                palette         = inspiration.get("colour_name", ""),
                prompt_text     = requirements.get(f"{key}_prompt", ""),
                inspo_analysis  = inspo_analysis,
                room_inspo_note = room_inspo_note,
            )
        except Exception as e:
            logger.warning(f"Room concept failed for {room['label']}: {e}")
            concept = f"Design concept for {room['label']} could not be generated. Please regenerate."
            room_errors += 1

        # A drawn concept visual for the room — the gateway has no image model,
        # so every shape here is generated from the style, palette and items.
        try:
            visual = _app.generate_room_concept_visual(
                room["label"],
                style       = inspiration.get("design_style", ""),
                palette_hex = inspiration.get("colour_hex", ""),
                # The room's own materials where the analysis gave it some —
                # the project-wide list put the same caption under every room,
                # oak and laminate included in the bathrooms.
                materials   = ((room_inspo_note.get("materials")
                                if isinstance(room_inspo_note, dict) else None)
                               or inspo_analysis.get("materials", [])),
                items       = requirements.get(f"{key}_items", []) or [],
                geo         = (plan_geometry or {}).get("rooms", {}).get(room["label"]),
                px_per_m    = px_per_m,
                layout      = layouts.get(key),
            )
        except Exception as e:
            logger.warning(f"Concept visual failed for {room['label']}: {e}")
            visual = ""

        room_results.append({
            "key":      key,
            "label":    room["label"],
            "concept":  concept,
            "visual":   visual,
            "direction": room_inspo_note if isinstance(room_inspo_note, dict) else {},
            "items":    requirements.get(f"{key}_items", []),
            "priority": requirements.get(f"{key}_priority", "medium"),
            "budget":   requirements.get(f"{key}_budget", ""),
            "colour":   _app.ROOM_COLOURS[i % len(_app.ROOM_COLOURS)],
            "layout":   layouts.get(key),
        })

    if room_errors == 0:
        trace.append(_trace_entry(
            step    = f"Generated {len(rooms)} room concept{'s' if len(rooms) != 1 else ''}",
            action  = "generate_room_concepts",
            reason  = "Create room-by-room design directions tied to requirements and inspiration.",
            status  = "success",
            summary = f"All {len(rooms)} room concepts generated.",
        ))
    else:
        trace.append(_trace_entry(
            step    = "Room concepts — partial",
            action  = "generate_room_concepts",
            reason  = "Create room-by-room design directions.",
            status  = "failed",
            summary = f"{len(rooms) - room_errors}/{len(rooms)} concepts generated. "
                      f"{room_errors} failed.",
        ))

    # ─────────────────────────────────────────────────────────────────────────
    # ACT: Floor plan schematic
    # ─────────────────────────────────────────────────────────────────────────
    floor_plan_svg = _app.generate_floor_plan_svg(room_results, geometry=plan_geometry)
    trace.append(_trace_entry(
        step    = ("Drew the floor plan from the trace" if plan_geometry
                   else "Generated schematic space overview"),
        action  = "generate_floor_plan_svg",
        reason  = "Visual summary of the home's spaces.",
        status  = "success",
        summary = f"{len(room_results)} spaces represented.",
    ))

    # ─────────────────────────────────────────────────────────────────────────
    # FINAL: Log if we're pausing for homeowner input
    # ─────────────────────────────────────────────────────────────────────────
    if needs_input:
        trace.append(_trace_entry(
            step    = f"Waiting for homeowner — {len(open_conflicts)} question{'s' if len(open_conflicts) != 1 else ''} outstanding",
            action  = "request_clarification",
            reason  = "Important decisions need homeowner input before the brief can be finalised.",
            status  = "needs_input",
            summary = "Brief shown with caveats. Regenerate after answering the questions above.",
        ))
    else:
        trace.append(_trace_entry(
            step    = "Brief complete",
            action  = "complete",
            reason  = "All analysis done, no unresolved conflicts.",
            status  = "success",
            summary = "Design direction ready for homeowner review and designer sharing.",
        ))

    return {
        "inspiration_analysis": inspo_analysis,
        "conflicts":            merged_conflicts,
        "ai_brief":             ai_brief,
        "room_results":         room_results,
        "floor_plan_svg":       floor_plan_svg,
        "plan_geometry":        plan_geometry,
        "furniture_plan":       ({"key": space["furn_key"], "rooms": furniture}
                                 if furniture is not None else None),
        "agent_trace":          trace,
        "needs_input":          needs_input,
    }
