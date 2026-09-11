import { HousingType, HousingTypeId, RoomBBox, RoomType } from "@/lib/types";

export const HOUSING_TYPES: HousingType[] = [
  { id: "hdb-3room", label: "HDB 3-Room", description: "Living/dining, kitchen, 2 bedrooms, 1 bathroom" },
  { id: "hdb-4room", label: "HDB 4-Room", description: "Living/dining, kitchen, 3 bedrooms, 2 bathrooms" },
  { id: "hdb-5room", label: "HDB 5-Room", description: "Living, dining, kitchen, 3 bedrooms, 2 bathrooms, balcony" },
  { id: "condo", label: "Condominium", description: "Living, dining, kitchen, 2 bedrooms, 2 bathrooms, balcony" },
  { id: "landed", label: "Landed / Terrace House", description: "Multi-storey layout with study & utility areas" },
  { id: "custom", label: "Other / Custom", description: "I'll describe my own layout" },
];

export const ROOM_TYPE_LABEL: Record<RoomType, string> = {
  "living-room": "Living Room",
  "dining-room": "Dining Room",
  kitchen: "Kitchen",
  "master-bedroom": "Master Bedroom",
  bedroom: "Bedroom",
  bathroom: "Bathroom",
  study: "Study",
  balcony: "Balcony",
  utility: "Utility Area",
  other: "Other Room",
};

export const ROOM_TYPE_ICON: Record<RoomType, string> = {
  "living-room": "🛋️",
  "dining-room": "🍽️",
  kitchen: "🍳",
  "master-bedroom": "🛏️",
  bedroom: "🛌",
  bathroom: "🛁",
  study: "📚",
  balcony: "🌿",
  utility: "🧺",
  other: "🚪",
};

interface RoomTemplate {
  type: RoomType;
  name: string;
  bbox: RoomBBox;
}

// Hand-authored schematic layouts (normalized 0-1 coordinates).
// These stand in for what Bedrock's vision segmentation would return
// after reading the uploaded floor plan image — see lib/ai/bedrock.ts
export const HOUSING_LAYOUTS: Record<HousingTypeId, RoomTemplate[]> = {
  "hdb-3room": [
    { type: "living-room", name: "Living / Dining", bbox: { x: 0.02, y: 0.04, w: 0.56, h: 0.46 } },
    { type: "kitchen", name: "Kitchen", bbox: { x: 0.6, y: 0.04, w: 0.38, h: 0.28 } },
    { type: "bathroom", name: "Bathroom", bbox: { x: 0.6, y: 0.34, w: 0.38, h: 0.16 } },
    { type: "master-bedroom", name: "Master Bedroom", bbox: { x: 0.02, y: 0.52, w: 0.46, h: 0.44 } },
    { type: "bedroom", name: "Bedroom 2", bbox: { x: 0.5, y: 0.52, w: 0.48, h: 0.44 } },
  ],
  "hdb-4room": [
    { type: "living-room", name: "Living / Dining", bbox: { x: 0.02, y: 0.04, w: 0.5, h: 0.46 } },
    { type: "kitchen", name: "Kitchen", bbox: { x: 0.54, y: 0.04, w: 0.44, h: 0.24 } },
    { type: "bathroom", name: "Bathroom 1", bbox: { x: 0.54, y: 0.3, w: 0.2, h: 0.2 } },
    { type: "bathroom", name: "Bathroom 2 (En-suite)", bbox: { x: 0.76, y: 0.3, w: 0.22, h: 0.2 } },
    { type: "master-bedroom", name: "Master Bedroom", bbox: { x: 0.02, y: 0.52, w: 0.34, h: 0.44 } },
    { type: "bedroom", name: "Bedroom 2", bbox: { x: 0.38, y: 0.52, w: 0.3, h: 0.44 } },
    { type: "bedroom", name: "Bedroom 3", bbox: { x: 0.7, y: 0.52, w: 0.28, h: 0.44 } },
  ],
  "hdb-5room": [
    { type: "living-room", name: "Living Room", bbox: { x: 0.02, y: 0.04, w: 0.4, h: 0.32 } },
    { type: "dining-room", name: "Dining Room", bbox: { x: 0.02, y: 0.38, w: 0.4, h: 0.2 } },
    { type: "kitchen", name: "Kitchen", bbox: { x: 0.44, y: 0.04, w: 0.28, h: 0.28 } },
    { type: "balcony", name: "Balcony", bbox: { x: 0.74, y: 0.04, w: 0.24, h: 0.28 } },
    { type: "bathroom", name: "Bathroom 1", bbox: { x: 0.44, y: 0.34, w: 0.24, h: 0.24 } },
    { type: "bathroom", name: "Bathroom 2 (En-suite)", bbox: { x: 0.7, y: 0.34, w: 0.28, h: 0.24 } },
    { type: "master-bedroom", name: "Master Bedroom", bbox: { x: 0.02, y: 0.6, w: 0.34, h: 0.36 } },
    { type: "bedroom", name: "Bedroom 2", bbox: { x: 0.38, y: 0.6, w: 0.3, h: 0.36 } },
    { type: "bedroom", name: "Bedroom 3", bbox: { x: 0.7, y: 0.6, w: 0.28, h: 0.36 } },
  ],
  condo: [
    { type: "living-room", name: "Living Room", bbox: { x: 0.02, y: 0.04, w: 0.46, h: 0.34 } },
    { type: "dining-room", name: "Dining Room", bbox: { x: 0.5, y: 0.04, w: 0.22, h: 0.34 } },
    { type: "kitchen", name: "Kitchen", bbox: { x: 0.74, y: 0.04, w: 0.24, h: 0.34 } },
    { type: "balcony", name: "Balcony", bbox: { x: 0.02, y: 0.4, w: 0.46, h: 0.14 } },
    { type: "bathroom", name: "Bathroom 1 (En-suite)", bbox: { x: 0.5, y: 0.4, w: 0.24, h: 0.16 } },
    { type: "bathroom", name: "Bathroom 2 (Common)", bbox: { x: 0.76, y: 0.4, w: 0.22, h: 0.16 } },
    { type: "master-bedroom", name: "Master Bedroom", bbox: { x: 0.02, y: 0.58, w: 0.46, h: 0.38 } },
    { type: "bedroom", name: "Bedroom 2", bbox: { x: 0.5, y: 0.58, w: 0.48, h: 0.38 } },
  ],
  landed: [
    { type: "living-room", name: "Living Room", bbox: { x: 0.02, y: 0.04, w: 0.32, h: 0.3 } },
    { type: "dining-room", name: "Dining Room", bbox: { x: 0.36, y: 0.04, w: 0.28, h: 0.3 } },
    { type: "kitchen", name: "Kitchen", bbox: { x: 0.66, y: 0.04, w: 0.32, h: 0.3 } },
    { type: "study", name: "Study", bbox: { x: 0.02, y: 0.36, w: 0.22, h: 0.2 } },
    { type: "utility", name: "Utility Area", bbox: { x: 0.26, y: 0.36, w: 0.2, h: 0.2 } },
    { type: "bathroom", name: "Bathroom 1", bbox: { x: 0.48, y: 0.36, w: 0.2, h: 0.2 } },
    { type: "balcony", name: "Balcony", bbox: { x: 0.7, y: 0.36, w: 0.28, h: 0.2 } },
    { type: "master-bedroom", name: "Master Bedroom", bbox: { x: 0.02, y: 0.58, w: 0.32, h: 0.38 } },
    { type: "bedroom", name: "Bedroom 2", bbox: { x: 0.36, y: 0.58, w: 0.28, h: 0.38 } },
    { type: "bedroom", name: "Bedroom 3", bbox: { x: 0.66, y: 0.58, w: 0.32, h: 0.19 } },
    { type: "bathroom", name: "Bathroom 2", bbox: { x: 0.66, y: 0.79, w: 0.32, h: 0.17 } },
  ],
  custom: [
    { type: "living-room", name: "Living Room", bbox: { x: 0.02, y: 0.04, w: 0.5, h: 0.46 } },
    { type: "kitchen", name: "Kitchen", bbox: { x: 0.54, y: 0.04, w: 0.44, h: 0.46 } },
    { type: "bedroom", name: "Bedroom", bbox: { x: 0.02, y: 0.52, w: 0.48, h: 0.44 } },
    { type: "bathroom", name: "Bathroom", bbox: { x: 0.52, y: 0.52, w: 0.46, h: 0.44 } },
  ],
};

export const COLOR_SCHEMES = [
  "Warm Neutrals",
  "Cool Minimalist",
  "Earthy Tones",
  "Monochrome",
  "Pastel Soft",
  "Bold & Contrast",
  "Coastal Blues",
  "Botanical Green",
];

export const STYLE_THEMES = [
  "Scandinavian",
  "Japandi",
  "Modern Minimalist",
  "Industrial",
  "Mid-Century Modern",
  "Contemporary Luxury",
  "Rustic",
  "Coastal",
];

// Swatch hexes purely for UI preview chips — keyed to COLOR_SCHEMES above.
export const COLOR_SCHEME_SWATCHES: Record<string, string[]> = {
  "Warm Neutrals": ["#E8DCC8", "#C9A87C", "#7A6552", "#F5EFE6"],
  "Cool Minimalist": ["#F4F6F8", "#D6DEE3", "#8FA3AD", "#2E3A45"],
  "Earthy Tones": ["#A9744F", "#C98B4A", "#6B4F3B", "#E4C9A4"],
  Monochrome: ["#111213", "#4B4E52", "#B7BABE", "#FFFFFF"],
  "Pastel Soft": ["#F7D9E3", "#D9EAF7", "#EAF7D9", "#FFF6DA"],
  "Bold & Contrast": ["#161616", "#E63946", "#F1FAEE", "#1D3557"],
  "Coastal Blues": ["#E9F2F5", "#8FBFCB", "#3E7C97", "#1B3A4B"],
  "Botanical Green": ["#E4EEE0", "#8FAE8B", "#4B6B4E", "#2C3E2E"],
};

export const ROOM_ITEM_CATALOG: Record<RoomType, string[]> = {
  kitchen: ["Oven", "Microwave", "Kitchen Island", "Gas Hob", "Range Hood", "Fridge Space", "Dishwasher", "Pantry Storage", "Bar Counter", "Wet & Dry Kitchen Split"],
  "master-bedroom": ["King Bed", "Walk-in Wardrobe", "Study Desk", "Reading Nook", "TV Console", "Dressing Table", "En-suite Access", "Blackout Curtains"],
  bedroom: ["Queen Bed", "Single Bed", "Wardrobe", "Study Desk", "Bunk Bed", "Storage Bench", "Bookshelf"],
  "living-room": ["3-Seater Sofa", "TV Console", "Coffee Table", "Bookshelf", "Feature Wall", "Display Cabinet", "Home Office Corner", "Extra Storage"],
  "dining-room": ["6-Seater Dining Table", "Sideboard", "Pendant Lighting", "Bar Cart", "Display Shelving"],
  bathroom: ["Rain Shower", "Bathtub", "Vanity Counter", "Storage Cabinet", "Bidet", "Heated Towel Rack"],
  study: ["Built-in Desk", "Bookshelves", "Office Chair", "Storage Cabinet", "Second Monitor Setup"],
  balcony: ["Outdoor Seating", "Planters", "Drying Rack", "Outdoor Flooring", "Small Table"],
  utility: ["Washer/Dryer", "Storage Shelving", "Utility Sink", "Ironing Station"],
  other: ["Custom Storage", "Feature Lighting", "Built-in Shelving"],
};
