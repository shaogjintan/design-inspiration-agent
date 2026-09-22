"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useProject } from "@/lib/project-context";
import { ROOM_TYPE_ICON } from "@/lib/data/catalog";
import { ImageDropzone } from "@/components/ImageDropzone";
import { StylePicker } from "@/components/StylePicker";
import { StepFooter } from "@/components/WizardShell";
import { cx } from "@/lib/utils";

export default function InspirationStep() {
  const router = useRouter();
  const { project, setOverallStyle, updateInspo } = useProject();
  const [activeRoomId, setActiveRoomId] = useState<string | null>(null);

  if (project.rooms.length === 0) {
    return (
      <div>
        <p className="text-stone-600">
          No rooms yet — head back to step 1 to upload a floor plan and segment it.
        </p>
        <StepFooter backHref="/project/housing" nextDisabled nextLabel="Continue to Requirements" />
      </div>
    );
  }

  const activeRoom = project.rooms.find((r) => r.id === activeRoomId) ?? project.rooms[0];
  const activeInspo = project.inspoByRoom[activeRoom.id];

  const allRoomsHaveTheme = project.rooms.every((r) => {
    const inspo = project.inspoByRoom[r.id];
    return (inspo?.colorScheme || project.overallColorScheme) && (inspo?.styleTheme || project.overallStyleTheme);
  });

  return (
    <div>
      <p className="text-xs uppercase tracking-widest text-amber-700 font-medium mb-2">
        Step 2 of 4
      </p>
      <h1 className="font-display text-3xl font-medium mb-2">Inspiration & theme</h1>
      <p className="text-stone-600 max-w-xl mb-8">
        Set an overall colour scheme and style — then drop inspo images per room and
        override the theme where a room should feel different.
      </p>

      <div className="rounded-2xl border border-stone-200 bg-white p-6 mb-10">
        <h2 className="text-sm font-medium text-stone-700 mb-4">Overall home theme</h2>
        <StylePicker
          colorScheme={project.overallColorScheme}
          styleTheme={project.overallStyleTheme}
          onColorScheme={(v) => setOverallStyle(v, project.overallStyleTheme)}
          onStyleTheme={(v) => setOverallStyle(project.overallColorScheme, v)}
        />
      </div>

      <div className="flex flex-wrap gap-2 mb-6 border-b border-stone-200 pb-4">
        {project.rooms.map((room) => {
          const has = project.inspoByRoom[room.id]?.images?.length;
          return (
            <button
              key={room.id}
              type="button"
              onClick={() => setActiveRoomId(room.id)}
              className={cx(
                "flex items-center gap-1.5 rounded-full px-3.5 py-2 text-sm border",
                activeRoom.id === room.id
                  ? "border-stone-900 bg-stone-900 text-white"
                  : "border-stone-200 bg-white hover:border-stone-400"
              )}
            >
              <span>{ROOM_TYPE_ICON[room.type]}</span>
              {room.name}
              {!!has && <span className="text-[10px] opacity-70">({has})</span>}
            </button>
          );
        })}
      </div>

      <div className="grid md:grid-cols-2 gap-8">
        <div>
          <h3 className="text-sm font-medium text-stone-700 mb-3">
            Inspo images — {activeRoom.name}
          </h3>
          <ImageDropzone
            images={activeInspo?.images ?? []}
            onChange={(images) => updateInspo(activeRoom.id, { images })}
          />
          <p className="mt-3 text-xs text-stone-400">
            Uploaded images help ground the AI&apos;s room concepts in step 4 — the real
            Bedrock call passes these to Sonnet 4.5 as multimodal context.
          </p>
        </div>
        <div>
          <h3 className="text-sm font-medium text-stone-700 mb-3">
            Room theme override{" "}
            <span className="text-stone-400 font-normal">(optional — defaults to overall)</span>
          </h3>
          <StylePicker
            colorScheme={activeInspo?.colorScheme || project.overallColorScheme}
            styleTheme={activeInspo?.styleTheme || project.overallStyleTheme}
            onColorScheme={(v) => updateInspo(activeRoom.id, { colorScheme: v })}
            onStyleTheme={(v) => updateInspo(activeRoom.id, { styleTheme: v })}
          />
        </div>
      </div>

      <StepFooter
        backHref="/project/housing"
        nextLabel="Continue to Requirements"
        nextDisabled={!allRoomsHaveTheme}
        onNext={() => router.push("/project/requirements")}
      />
    </div>
  );
}
