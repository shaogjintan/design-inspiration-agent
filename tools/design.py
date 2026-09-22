"""
tools/design.py — Design generation and conflict detection tools.

Exposes:
  generate_design_brief(...)  — overall design brief HTML
  generate_room_concept(...)  — per-room concept paragraph
  detect_conflicts(...)       — style, budget, and spatial conflict detection

These are thin re-exports from app.py.
"""


def generate_design_brief(project):
    """
    Generate an HTML design brief grounded in inspiration analysis,
    requirements, and homeowner decisions.
    """
    import app
    return app.generate_design_brief(project)


def generate_room_concept(room, style, palette, prompt_text,
                          inspo_analysis=None, room_inspo_note="",
                          budget="", priority="", constraints=""):
    """Generate an 80–120 word design concept for a single room."""
    import app
    return app.generate_room_concept(
        room, style, palette, prompt_text,
        inspo_analysis=inspo_analysis,
        room_inspo_note=room_inspo_note,
        budget=budget, priority=priority, constraints=constraints,
    )


def detect_conflicts(step1, requirements, inspiration,
                     inspiration_analysis, rooms):
    """
    Analyse project state and return a list of conflict dicts.

    Detects:
      - style:   visually incompatible inspiration directions
      - budget:  scope exceeds realistic budget expectations
      - spatial: too many large items for the home's floor size

    Each conflict has: id, type, severity, title, description,
    question, options, resolved, decision.
    """
    import app
    return app.detect_conflicts(
        step1, requirements, inspiration, inspiration_analysis, rooms
    )
