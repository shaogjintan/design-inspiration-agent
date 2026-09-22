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
    # Every step reports a confidence. If the caller didn't set one, derive it
    # from the status so the Agent Activity panel always shows a signal:
    #   success -> high   |   needs_input -> medium   |   failed -> low
    #   skipped -> keeps whatever was passed (usually the cached confidence)
    if confidence is None:
        confidence = {
            "success":     "high",
            "needs_input": "medium",
            "failed":      "low",
            "skipped":     "medium",
        }.get(status, "medium")
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

    # Rebuild the trace FRESH each run. The Agent Activity panel must reflect the
    # CURRENT state — carrying old entries left stale "needs you" / "waiting for
    # homeowner" lines around even after the homeowner had answered. We ignore
    # existing_trace on purpose.
    trace: list[dict] = []

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
    # REASON + ACT: Floor plan
    # ─────────────────────────────────────────────────────────────────────────
    # Floor plan analysis already ran in step1 POST — we record it in the trace
    # so the judge can see it happened, but we don't re-run it here.
    room_source   = "AI floor plan analysis" if has_floor_plan else "housing type catalogue"
    room_confidence = "high" if has_floor_plan else "medium"
    trace.append(_trace_entry(
        step    = f"{'Analysed floor plan' if has_floor_plan else 'Inferred rooms from housing type'}",
        action  = "analyse_floor_plan",
        reason  = "Identify all spaces in the home before building the brief.",
        status  = "success",
        summary = f"Identified {len(rooms)} spaces via {room_source}.",
        confidence = room_confidence,
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
                inspiration, rooms,
                memory={"step1": step1, "requirements": requirements},
            )
            trace.append(_trace_entry(
                step    = f"Analysed {total_images} inspiration image{'s' if total_images != 1 else ''}",
                action  = "analyse_inspiration",
                reason  = reason,
                status  = "success",
                summary = inspo_analysis.get("summary", ""),
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

    # Merge policy:
    #  - Any conflict the homeowner ALREADY RESOLVED is kept forever (so the
    #    decision is never lost and the question is never asked again), even if
    #    it is no longer re-detected this run.
    #  - Newly detected, still-open conflicts are added.
    #  - A previously-open (unresolved) conflict that is no longer detected is
    #    dropped (the underlying issue went away).
    detected_ids = {c["id"] for c in all_detected}
    merged_conflicts: list[dict] = []
    seen_ids: set[str] = set()

    # 1) carry over every resolved decision first
    for cid, c in existing_by_id.items():
        if c.get("resolved"):
            merged_conflicts.append(c)
            seen_ids.add(cid)

    # 2) add newly detected conflicts that aren't already resolved
    for c in all_detected:
        if c["id"] in seen_ids:
            continue  # already carried as a resolved decision
        merged_conflicts.append(c)
        seen_ids.add(c["id"])

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
        if closed_conflicts:
            # All questions answered — show WHICH decisions were applied so the
            # homeowner can see their answers were taken into account.
            applied = "; ".join(
                f"{c['title']} → {c['decision']}" for c in closed_conflicts[:3]
            )
            trace.append(_trace_entry(
                step    = "Applied your decisions",
                action  = "detect_conflicts",
                reason  = "Incorporating the homeowner's answers into the brief.",
                status  = "success",
                summary = applied,
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
                budget          = requirements.get(f"{key}_budget", ""),
                priority        = requirements.get(f"{key}_priority", ""),
                constraints     = requirements.get(f"{key}_constraints", ""),
            )
        except Exception as e:
            logger.warning(f"Room concept failed for {room['label']}: {e}")
            concept = f"Design concept for {room['label']} could not be generated. Please regenerate."
            room_errors += 1

        # Build a data-driven concept visual for this room (SVG, no external
        # assets — the gateway has no image-generation model).
        selected_items = requirements.get(f"{key}_items", []) or []
        try:
            visual = _app.generate_room_concept_visual(
                room["label"],
                style       = inspiration.get("design_style", ""),
                palette_hex = inspiration.get("colour_hex", ""),
                materials   = inspo_analysis.get("materials", []),
                items       = selected_items,
            )
        except Exception as e:
            logger.warning(f"Concept visual failed for {room['label']}: {e}")
            visual = ""

        room_results.append({
            "key":      key,
            "label":    room["label"],
            "concept":  concept,
            "visual":   visual,
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

    # Overall run confidence: "low" if any step failed, "medium" if anything
    # needs input or a low-confidence step exists, else "high".
    statuses = [t.get("status") for t in trace]
    confs    = [t.get("confidence") for t in trace]
    if "failed" in statuses:
        overall_confidence = "low"
    elif "needs_input" in statuses or "low" in confs:
        overall_confidence = "medium"
    else:
        overall_confidence = "high"

    return {
        "inspiration_analysis": inspo_analysis,
        "conflicts":            merged_conflicts,
        "ai_brief":             ai_brief,
        "room_results":         room_results,
        "floor_plan_svg":       floor_plan_svg,
        "agent_trace":          trace,
        "needs_input":          needs_input,
        "overall_confidence":   overall_confidence,
    }
