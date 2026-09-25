# Forma reference library

This folder holds the curated style library that Forma's agent uses during Stage 3 theme selection. It contains 102 interior images across nine room types and eight styles. Every image is tagged with the same vocabulary the agent uses to read a homeowner's own inspiration photos, so a client's confirmed tags can rank library images directly.

Library images are for style selection only. They must never be shown as the client's room, and generated renders of the client's room are a separate asset type.

## What is in the pack

| File | Who it is for | What it does |
|---|---|---|
| `forma-library.json` | Developers | The main data file. Load it straight into the agent or front end. |
| `forma-library.csv` | Anyone importing into a database or Google Sheets | The same records flattened into one row per image. List fields are joined with `\|`. |
| `Forma_reference_library.xlsx` | Teammates reviewing tags | Human-readable version with coverage counts, budget tiers, tag vocabulary and known gaps. |
| `download_images.py` | Anyone who wants local copies | Saves every image as `images/FL-0001.jpg` and so on. |

The Excel workbook is the master copy. If anyone changes a tag, change it there and regenerate the JSON and CSV so the files do not drift apart.

## Record structure

Each entry in `images` looks like this.

```json
{
  "id": "FL-0001",
  "room": "living",
  "housing_fit": ["HDB", "condo"],
  "style": "Japandi",
  "palette": { "family": "warm neutral", "description": "warm neutral", "colours": ["grey", "walnut"] },
  "materials": ["dark wood", "fabric-heavy"],
  "lighting": ["natural-led", "feature pendant"],
  "fixtures": [],
  "layout": "open concept",
  "texture": "soft layered",
  "furniture_style": "low-profile",
  "mood": "calm",
  "budget_tier": "Mid-range",
  "likely_render": false,
  "notes": "living-dining layout close to a SG condo",
  "image": {
    "url": "https://images.unsplash.com/photo-1712928247899-2932f4c7dea3?w=1080&q=80&fm=jpg&fit=max",
    "thumb_url": "https://images.unsplash.com/photo-1712928247899-2932f4c7dea3?w=400&q=80&fm=jpg&fit=max",
    "width": 3200, "height": 2133, "dominant_colour": "#c0c0c0"
  },
  "source": {
    "provider": "Unsplash", "photo_id": "RDg0Xz_KBdY",
    "page_url": "https://unsplash.com/photos/RDg0Xz_KBdY",
    "photographer": "Clay Banks", "photographer_url": "https://unsplash.com/@claybanks",
    "licence": "Unsplash License", "licence_url": "https://unsplash.com/license"
  }
}
```

The file also carries `tag_vocabulary`, which lists every allowed value per field, and `budget_tiers`, which gives the SGD boundaries. Every record has been checked against the vocabulary, so the front end can build filters from `tag_vocabulary` without cleaning the data first.

## Field notes

`room`, `style`, `layout`, `texture`, `furniture_style`, `mood` and `budget_tier` hold one value each. `housing_fit`, `materials` and `lighting` are lists. `palette.family` is the matchable value, while `palette.colours` lists the dominant colours in plain words for display. `fixtures` records extras such as a ceiling fan or floor lamp that sit outside the lighting vocabulary. `dominant_colour` comes from Unsplash and works well as a placeholder background while an image loads.

`housing_fit` and `budget_tier` are visual estimates and are the least reliable fields. `budget_tier` describes the finish level in the photo rather than a price for the client's home. The homeowner's Stage 2 bracket maps onto it as follows.

| Tier | Whole-home budget (SGD) |
|---|---|
| Essential | Under 40,000 |
| Mid-range | 40,000 to 80,000 |
| Premium | Above 80,000 |

These boundaries are indicative. They come from 2026 Singapore contractor and interior design firm guides, which agree with each other but are not independent survey data. Sources are listed in the workbook.

`likely_render` is true for 36 images that appear to be 3D renders rather than photographs. The flag comes from visual cues and from the uploader being a 3D or design studio, so treat it as a strong hint rather than a certainty.

## Using the images

The image URLs point to Unsplash's own servers, so the site can display them without hosting anything. Unsplash's API guidelines ask apps to link to its image URLs in this way, and the `w` parameter in each URL can be changed to request a different width. If a photo is ever removed from Unsplash, its tile will stop loading, so run `download_images.py` if the demo must work offline or must not depend on Unsplash.

To download, run `python3 download_images.py` from this folder on any computer with normal internet access. Add `--thumbs` for 400px copies. The script needs no extra packages and skips files it has already saved.

All images are free Unsplash images, with Unsplash+ content excluded. The Unsplash License allows commercial use without asking permission. It does not allow compiling Unsplash photos to replicate a similar or competing service. A curated style library inside a renovation platform is probably fine for a competition demo, but a production version should move to its own licensed library. Credit is not required, but showing "Photo by [photographer] on Unsplash" beside each image is good practice, and every record carries the name and profile link for that.

## Coverage

| Room | Scandinavian | Japandi | modern minimalist | industrial | mid-century | contemporary | tropical | modern luxe | Total |
|---|---|---|---|---|---|---|---|---|---|
| living | 2 | 2 | 3 | 2 | 2 | 3 | 2 | 3 | 19 |
| master bedroom | 1 | 1 | 3 | 3 | 2 | 2 | 2 | 2 | 16 |
| secondary bedroom | 2 | 0 | 1 | 0 | 1 | 1 | 0 | 0 | 5 |
| kitchen | 2 | 2 | 4 | 2 | 2 | 2 | 2 | 2 | 18 |
| dining | 1 | 1 | 1 | 1 | 2 | 1 | 1 | 1 | 9 |
| bathroom | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 16 |
| study | 2 | 2 | 2 | 2 | 2 | 1 | 2 | 1 | 14 |
| balcony | 0 | 0 | 1 | 1 | 0 | 1 | 0 | 0 | 3 |
| entryway | 1 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 2 |

The five core rooms have at least one image in every style. Secondary bedroom, balcony and entryway are thin and not split by style, so the agent should fall back to the nearest style and name the gap, as the project instructions already require. Few images show HDB-specific spaces such as bomb shelters or service yards. Rows whose notes mention an HDB-like footprint are the closest matches.

## How the tags were made

Tags were assigned by eye from the images, using the controlled vocabulary above, on 25 September 2026. Budget tier and housing fit should be spot-checked before the library is shown to judges.
