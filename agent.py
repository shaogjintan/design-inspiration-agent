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
from datetime import datetime, timezone

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

def run_agent(
    step1: dict,
    requirements: dict,
    inspiration: dict,
    rooms: list[dict],
    existing_inspiration_analysis: dict | None,
    existing_conflicts: list[dict] | None,
    existing_trace: list[dict] | None,
    force_reanalyse: bool = False,
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
    # ACT: Generate per-room concepts
    # ─────────────────────────────────────────────────────────────────────────
    room_results: list[dict] = []
    room_errors = 0

    for i, room in enumerate(rooms):
        key = room["key"]
        room_inspo_note = inspo_analysis.get("room_specific", {}).get(key, "")
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

        room_results.append({
            "key":      key,
            "label":    room["label"],
            "concept":  concept,
            "direction": room_inspo_note if isinstance(room_inspo_note, dict) else {},
            "items":    requirements.get(f"{key}_items", []),
            "priority": requirements.get(f"{key}_priority", "medium"),
            "budget":   requirements.get(f"{key}_budget", ""),
            "colour":   _app.ROOM_COLOURS[i % len(_app.ROOM_COLOURS)],
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
    floor_plan_svg = _app.generate_floor_plan_svg(room_results)
    trace.append(_trace_entry(
        step    = "Generated schematic space overview",
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
        "agent_trace":          trace,
        "needs_input":          needs_input,
    }
