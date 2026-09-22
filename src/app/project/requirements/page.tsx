"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useProject } from "@/lib/project-context";
import { ROOM_ITEM_CATALOG, ROOM_TYPE_ICON } from "@/lib/data/catalog";
import { StepFooter } from "@/components/WizardShell";
import { Tag } from "@/components/ui/Chip";
import { cx } from "@/lib/utils";

export default function RequirementsStep() {
  const router = useRouter();
  const { project, updateRequirement } = useProject();
  const [activeRoomId, setActiveRoomId] = useState<string | null>(null);

  if (project.rooms.length === 0) {
    return (
      <div>
        <p className="text-stone-600">No rooms yet — head back to step 1.</p>
        <StepFooter backHref="/project/housing" nextDisabled nextLabel="Continue to Results" />
      </div>
    );
  }

  const activeRoom = project.rooms.find((r) => r.id === activeRoomId) ?? project.rooms[0];
  const activeReq = project.requirementsByRoom[activeRoom.id];
  const itemOptions = ROOM_ITEM_CATALOG[activeRoom.type] ?? [];

  const allRoomsReady = project.rooms.every(
    (r) => (project.requirementsByRoom[r.id]?.prompt ?? "").trim().length > 0
  );

  function toggleItem(item: string) {
    const current = activeReq?.mustHaveItems ?? [];
    const next = current.includes(item)
      ? current.filter((i) => i !== item)
      : [...current, item];
    updateRequirement(activeRoom.id, { mustHaveItems: next });
  }

  return (
    <div>
      <p className="text-xs uppercase tracking-widest text-amber-700 font-medium mb-2">
        Step 3 of 4
      </p>
      <h1 className="font-display text-3xl font-medium mb-2">Room requirements</h1>
      <p className="text-stone-600 max-w-xl mb-8">
        Pick must-have items per room, and write a short prompt describing what the
        room needs — this is required so the AI concept in step 4 is grounded in
        real requirements, not just aesthetics.
      </p>

      <div className="flex flex-wrap gap-2 mb-6 border-b border-stone-200 pb-4">
        {project.rooms.map((room) => {
          const done = (project.requirementsByRoom[room.id]?.prompt ?? "").trim().length > 0;
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
              <span className={cx("h-1.5 w-1.5 rounded-full", done ? "bg-emerald-500" : "bg-stone-300")} />
            </button>
          );
        })}
      </div>

      <div className="grid md:grid-cols-2 gap-8">
        <div>
          <h3 className="text-sm font-medium text-stone-700 mb-3">
            Must-have items — {activeRoom.name}
          </h3>
          <div className="flex flex-wrap gap-2 mb-4">
            {itemOptions.map((item) => {
              const active = activeReq?.mustHaveItems?.includes(item);
              return (
                <button
                  key={item}
                  type="button"
                  onClick={() => toggleItem(item)}
                  className={cx(
                    "rounded-full border px-3 py-1.5 text-xs",
                    active
                      ? "border-stone-900 bg-stone-900 text-white"
                      : "border-stone-200 bg-white text-stone-600 hover:border-stone-400"
                  )}
                >
                  {item}
                </button>
              );
            })}
          </div>
          {!!activeReq?.mustHaveItems?.length && (
            <div className="flex flex-wrap gap-1.5">
              {activeReq.mustHaveItems.map((item) => (
                <Tag key={item} onRemove={() => toggleItem(item)}>
                  {item}
                </Tag>
              ))}
            </div>
          )}
        </div>

        <div>
          <h3 className="text-sm font-medium text-stone-700 mb-3">
            Describe what this room needs <span className="text-red-500">*</span>
          </h3>
          <textarea
            value={activeReq?.prompt ?? ""}
            onChange={(e) => updateRequirement(activeRoom.id, { prompt: e.target.value })}
            placeholder={`e.g. "Needs to fit a full-size oven and microwave, tight galley layout, lots of storage for a family of 4."`}
            rows={6}
            className="w-full rounded-xl border border-stone-200 bg-white px-3 py-2.5 text-sm focus:border-stone-400 focus:outline-none resize-none"
          />
          <p className="mt-2 text-xs text-stone-400">
            Required — passed to Sonnet 4.5 alongside the checklist to build this
            room&apos;s generation prompt.
          </p>
        </div>
      </div>

      <StepFooter
        backHref="/project/inspiration"
        nextLabel="Generate AI Suggestions"
        nextDisabled={!allRoomsReady}
        onNext={() => router.push("/project/results")}
      />
    </div>
  );
}
