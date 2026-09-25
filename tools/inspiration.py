"""
tools/inspiration.py — Inspiration image analysis tool.

Exposes:
  analyse_inspiration(...)          — multimodal visual analysis of uploaded images
  inspiration_analysis_fallback(...)— text-only fallback when no images are available

These are thin re-exports from app.py.
"""


def analyse_inspiration(inspiration, rooms):
    """
    Send uploaded inspiration images to Claude (multimodal) and extract
    structured visual characteristics.

    Returns dict with keys:
      dominant_styles, colours, materials, lighting, forms,
      common_patterns, possible_outliers, room_specific,
      summary, source, confidence, image_count
    """
    import app
    return app.analyse_inspiration(inspiration, rooms)


def inspiration_analysis_fallback(style, palette, custom_colour, vibes, image_count):
    """Text-only fallback used when the LLM call fails or no images exist."""
    import app
    return app._inspiration_analysis_fallback(
        style, palette, custom_colour, vibes, image_count
    )
