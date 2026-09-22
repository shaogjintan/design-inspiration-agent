"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useProject } from "@/lib/project-context";
import { HOUSING_TYPES } from "@/lib/data/catalog";
import { HousingTypeId } from "@/lib/types";
import { ImageUploadBox } from "@/components/ImageUploadBox";
import { RoomOverlay, RoomList } from "@/components/RoomSegmentation";
import { StepFooter } from "@/components/WizardShell";
import { cx } from "@/lib/utils";
import { segmentFloorPlan } from "@/lib/ai/bedrock";

export default function HousingStep() {
  const router = useRouter();
  const {
    project,
    setProjectName,
    setHousingType,
    setFloorPlanImage,
    setRooms,
    updateRoom,
    removeRoom,
    setSegmented,
  } = useProject();
  const [segmenting, setSegmenting] = useState(false);

  async function handleSegment() {
    if (!project.housingType) return;
    setSegmenting(true);
    try {
      const rooms = await segmentFloorPlan(project.housingType);
      setRooms(rooms);
      setSegmented(true);
    } finally {
      setSegmenting(false);
    }
  }

  const canSegment = !!project.housingType && !!project.floorPlanImage;
  const canContinue = project.segmented && project.rooms.length > 0;

  return (
    <div>
      <p className="text-xs uppercase tracking-widest text-amber-700 font-medium mb-2">
        Step 1 of 4
      </p>
      <h1 className="font-display text-3xl font-medium mb-2">Housing type & floor plan</h1>
      <p className="text-stone-600 max-w-xl mb-8">
        Tell us the housing type and upload a floor plan. AI (Bedrock / Claude Sonnet 4.5)
        will read it and segregate it into individual rooms.
      </p>

      <label className="block text-sm font-medium text-stone-700 mb-2">Project name</label>
      <input
        value={project.projectName}
        onChange={(e) => setProjectName(e.target.value)}
        className="mb-8 w-full max-w-md rounded-xl border border-stone-200 bg-white px-3 py-2 text-sm focus:border-stone-400 focus:outline-none"
        placeholder="e.g. Tan Family — Punggol 4-Room"
      />

      <h2 className="text-sm font-medium text-stone-700 mb-3">Housing type</h2>
      <div className="grid sm:grid-cols-2 gap-3 mb-8">
        {HOUSING_TYPES.map((h) => (
          <button
            key={h.id}
            type="button"
            onClick={() => setHousingType(h.id as HousingTypeId)}
            className={cx(
              "text-left rounded-xl border px-4 py-3 transition-colors",
              project.housingType === h.id
                ? "border-stone-900 bg-stone-900 text-white"
                : "border-stone-200 bg-white hover:border-stone-400"
            )}
          >
            <div className="font-medium text-sm">{h.label}</div>
            <div
              className={cx(
                "text-xs mt-0.5",
                project.housingType === h.id ? "text-stone-300" : "text-stone-500"
              )}
            >
              {h.description}
            </div>
          </button>
        ))}
      </div>

      <h2 className="text-sm font-medium text-stone-700 mb-3">Floor plan</h2>
      <ImageUploadBox image={project.floorPlanImage} onChange={setFloorPlanImage} />

      <div className="mt-6 flex items-center gap-3">
        <button
          type="button"
          disabled={!canSegment || segmenting}
          onClick={handleSegment}
          className="inline-flex items-center gap-2 rounded-full bg-amber-700 px-5 py-2.5 text-sm font-medium text-white hover:bg-amber-800 disabled:opacity-40 disabled:pointer-events-none"
        >
          {segmenting ? (
            <>
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
              Segmenting rooms…
            </>
          ) : project.segmented ? (
            "Re-segment rooms"
          ) : (
            "Segment rooms with AI"
          )}
        </button>
        {!canSegment && (
          <span className="text-xs text-stone-400">
            Pick a housing type and upload a floor plan first
          </span>
        )}
      </div>

      {project.rooms.length > 0 && (
        <div className="mt-10 grid md:grid-cols-2 gap-6">
          <div>
            <h3 className="text-sm font-medium text-stone-700 mb-3">Segmentation preview</h3>
            <RoomOverlay image={project.floorPlanImage} rooms={project.rooms} />
            <p className="mt-2 text-xs text-stone-400">
              Schematic overlay from AI segmentation — adjust room names/types alongside.
            </p>
          </div>
          <div>
            <h3 className="text-sm font-medium text-stone-700 mb-3">
              Detected rooms ({project.rooms.length})
            </h3>
            <RoomList
              rooms={project.rooms}
              onUpdate={updateRoom}
              onRemove={removeRoom}
              onAdd={(room) => setRooms([...project.rooms, room])}
            />
          </div>
        </div>
      )}

      <StepFooter
        nextLabel="Continue to Inspiration"
        nextDisabled={!canContinue}
        onNext={() => router.push("/project/inspiration")}
      />
    </div>
  );
}
