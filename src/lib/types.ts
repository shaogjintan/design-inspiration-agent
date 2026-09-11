// Core data model for the design-inspiration wizard.
// Kept framework-agnostic so it can be reused by both the client state
// and (later) real Bedrock request/response shapes.

export type HousingTypeId =
  | "hdb-3room"
  | "hdb-4room"
  | "hdb-5room"
  | "condo"
  | "landed"
  | "custom";

export interface HousingType {
  id: HousingTypeId;
  label: string;
  description: string;
}

export type RoomType =
  | "living-room"
  | "dining-room"
  | "kitchen"
  | "master-bedroom"
  | "bedroom"
  | "bathroom"
  | "study"
  | "balcony"
  | "utility"
  | "other";

export interface UploadedImage {
  id: string;
  name: string;
  dataUrl: string;
}

// Normalized (0-1) rectangle used to draw the schematic segmentation
// overlay on top of the uploaded floor plan image.
export interface RoomBBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface DetectedRoom {
  id: string;
  name: string;
  type: RoomType;
  bbox: RoomBBox;
  confidence: number; // 0-1, mocked
}

export interface RoomInspo {
  roomId: string;
  images: UploadedImage[];
  colorScheme: string;
  styleTheme: string;
}

export interface RoomRequirement {
  roomId: string;
  mustHaveItems: string[];
  prompt: string;
}

export interface GeneratedImage {
  id: string;
  seed: number;
  promptSummary: string;
}

export interface RoomGeneration {
  roomId: string;
  iteration: number; // 0 = not generated yet
  maxIterations: number;
  images: GeneratedImage[];
  status: "idle" | "generating" | "done" | "error";
}

export interface ProjectState {
  projectName: string;
  housingType: HousingTypeId | null;
  floorPlanImage: UploadedImage | null;
  overallColorScheme: string | null;
  overallStyleTheme: string | null;
  rooms: DetectedRoom[];
  segmented: boolean;
  inspoByRoom: Record<string, RoomInspo>;
  requirementsByRoom: Record<string, RoomRequirement>;
  generationsByRoom: Record<string, RoomGeneration>;
}

export const STORAGE_KEY = "dia:project:v1";
