"""
tools/floorplan.py — Floor plan analysis tool.

Exposes:
  generate_room_summary(...)  — identify rooms from housing type or floor plan image
  generate_floor_plan_svg(...)— produce a schematic SVG overview of the spaces

These are thin re-exports from app.py. The implementations live in app.py
because they share the call_llm() gateway wrapper and catalogue constants.
Moving them here physically is a Phase 2 refactor after the hackathon.
"""

# Late import to avoid circular dependency at module load time.
def generate_room_summary(housing_type, floor_size, notes,
                          num_floors="1", floor_plan_path=None):
    """Identify the rooms in this home.

    Returns dict with keys: rooms, summary, observations, source, confidence.
    """
    import app
    return app.generate_room_summary(
        housing_type, floor_size, notes,
        num_floors=num_floors, floor_plan_path=floor_plan_path
    )


def generate_floor_plan_svg(rooms):
    """Generate a schematic 2D floor plan as inline SVG."""
    import app
    return app.generate_floor_plan_svg(rooms)


def stub_read_floorplan(housing_type, floor_size="", num_floors="1",
                        notes="", floor_plan_path=None):
    """Text-only fallback — derives rooms from housing type without LLM."""
    import app
    return app.stub_read_floorplan(
        housing_type, floor_size, num_floors, notes, floor_plan_path
    )
