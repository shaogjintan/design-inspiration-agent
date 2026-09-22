// -----------------------------------------------------------------------
// MOCK AI LAYER — stands in for AWS Bedrock until the team's API key/access
// is provisioned. Every exported function here has the exact shape a real
// call would have (async, same input/output types) so swapping the body
// for a real `BedrockRuntimeClient` call is a drop-in change — nothing
// else in the app needs to know the difference.
//
// Intended real architecture (fill in when Bedrock access is granted):
//
//   1. segmentFloorPlan()
//      -> Bedrock Converse API, model "anthropic.claude-sonnet-4-5"
//      -> multimodal input: the uploaded floor plan image + housing type
//      -> ask Claude to return room polygons/bboxes + labels as JSON
//         (use a tool/function-call schema to force structured output)
//
//   2. summarizeInspiration()
//      -> Bedrock Converse API, Sonnet 4.5, multimodal
//      -> input: inspo images + consumer's colour/theme picks
//      -> ask Claude to produce a short design brief per room (used to
//         condition the image generation prompt in step 4)
//
//   3. generateRoomConcepts()
//      -> Sonnet 4.5 is text/vision only — it CANNOT generate images.
//         This step needs an image-generation model also served over
//         Bedrock, e.g. "amazon.titan-image-generator-v2" or
//         "amazon.nova-canvas-v1". Sonnet 4.5's job here is to turn the
//         room brief + required-items prompt into a strong image-gen
//         prompt (prompt engineering), which is then passed to the
//         image model. Keep both calls — don't assume one model does both.
//
//   4. generateFloorPlan2D()
//      -> Either Sonnet 4.5 reasoning over the room list to emit an
//         updated layout as structured JSON (rendered client-side, as
//         this mock already does), or a dedicated CAD/layout model if
//         precision matters more than speed for the hackathon judges.
// -----------------------------------------------------------------------

import { HOUSING_LAYOUTS } from "@/lib/data/catalog";
import {
  DetectedRoom,
  GeneratedImage,
  HousingTypeId,
  RoomInspo,
  RoomRequirement,
} from "@/lib/types";

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function uid(prefix: string) {
  return `${prefix}_${Math.random().toString(36).slice(2, 9)}`;
}

/**
 * MOCK of Bedrock Sonnet 4.5 vision call.
 * Real version sends the floor plan image + housingType to Claude and
 * parses a structured room-segmentation JSON response.
 */
export async function segmentFloorPlan(
  housingType: HousingTypeId
): Promise<DetectedRoom[]> {
  await delay(1400 + Math.random() * 600);
  const template = HOUSING_LAYOUTS[housingType];
  return template.map((room) => ({
    id: uid("room"),
    name: room.name,
    type: room.type,
    bbox: room.bbox,
    confidence: 0.86 + Math.random() * 0.12,
  }));
}

/**
 * MOCK of Bedrock Sonnet 4.5 text call that turns a room's inspo images +
 * required-items prompt into a design brief / image-gen prompt.
 */
export async function buildRoomBrief(
  room: DetectedRoom,
  inspo: RoomInspo | undefined,
  requirement: RoomRequirement | undefined
): Promise<string> {
  await delay(300 + Math.random() * 200);
  const parts = [
    `${room.name} (${room.type})`,
    inspo?.styleTheme ? `style: ${inspo.styleTheme}` : null,
    inspo?.colorScheme ? `palette: ${inspo.colorScheme}` : null,
    requirement?.mustHaveItems?.length
      ? `must include: ${requirement.mustHaveItems.join(", ")}`
      : null,
    requirement?.prompt ? `consumer notes: "${requirement.prompt}"` : null,
    inspo?.images?.length ? `${inspo.images.length} inspo reference(s) attached` : null,
  ].filter(Boolean);
  return parts.join(" · ");
}

/**
 * MOCK of the Bedrock image-generation call (Titan Image Generator /
 * Nova Canvas). Returns lightweight seeds/metadata only — the UI renders
 * a generated-looking concept card client-side from these seeds so the
 * demo has no external network/image dependency.
 */
export async function generateRoomConcepts(
  room: DetectedRoom,
  promptSummary: string,
  count = 3
): Promise<GeneratedImage[]> {
  await delay(1600 + Math.random() * 900);
  return Array.from({ length: count }).map(() => ({
    id: uid("gen"),
    seed: Math.floor(Math.random() * 100000),
    promptSummary,
  }));
}

export const MAX_ITERATIONS_PER_ROOM = 3;
