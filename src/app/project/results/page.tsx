"use client";

import { useProject } from "@/lib/project-context";
import { COLOR_SCHEME_SWATCHES, ROOM_TYPE_ICON } from "@/lib/data/catalog";
import { StepFooter } from "@/components/WizardShell";
import { ConceptCard } from "@/components/ConceptCard";
import { FloorPlan2D } from "@/components/FloorPlan2D";
import { buildRoomBrief, generateRoomConcepts, MAX_ITERATIONS_PER_ROOM } from "@/lib/ai/bedrock";
import { RoomGeneration } from "@/lib/types";

export default function ResultsStep() {
  const { project, updateGeneration } = useProject();

  if (project.rooms.length === 0) {
    return (
      <div>
        <p className="text-stone-600">No rooms yet — head back to step 1.</p>
        <StepFooter backHref="/project/housing" />
      </div>
    );
  }

  async function runGeneration(roomId: string) {
    const room = project.rooms.find((r) => r.id === roomId)!;
    const existing: RoomGeneration | undefined = project.generationsByRoom[roomId];
    if (existing && existing.iteration >= existing.maxIterations) return;

    updateGeneration(roomId, { status: "generating" });
    const inspo = project.inspoByRoom[roomId];
    const requirement = project.requirementsByRoom[roomId];
    const promptSummary = await buildRoomBrief(room, inspo, requirement);
    const images = await generateRoomConcepts(room, promptSummary, 3);
    updateGeneration(roomId, {
      status: "done",
      images,
      iteration: (existing?.iteration ?? 0) + 1,
    });
  }

  return (
    <div>
      <p className="text-xs uppercase tracking-widest text-amber-700 font-medium mb-2">
        Step 4 of 4
      </p>
      <h1 className="font-display text-3xl font-medium mb-2">AI suggestions</h1>
      <p className="text-stone-600 max-w-xl mb-4">
        Generate concept previews per room and a matching 2D floor plan. Each
        regeneration simulates a Bedrock image-model call, so iterations are capped
        at {MAX_ITERATIONS_PER_ROOM} per room to manage inference cost.
      </p>

      <div className="mb-10">
        <h2 className="text-sm font-medium text-stone-700 mb-3">2D floor plan</h2>
        <FloorPlan2D
          rooms={project.rooms}
          inspoByRoom={project.inspoByRoom}
          overallColorScheme={project.overallColorScheme}
        />
      </div>

      <div className="space-y-8">
        {project.rooms.map((room) => {
          const gen = project.generationsByRoom[room.id];
          const inspo = project.inspoByRoom[room.id];
          const requirement = project.requirementsByRoom[room.id];
          const scheme = inspo?.colorScheme || project.overallColorScheme || "Warm Neutrals";
          const swatches = COLOR_SCHEME_SWATCHES[scheme] ?? [];
          const iteration = gen?.iteration ?? 0;
          const maxed = iteration >= MAX_ITERATIONS_PER_ROOM;
          const generating = gen?.status === "generating";

          return (
            <div key={room.id} className="rounded-2xl border border-stone-200 bg-white p-5">
              <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
                <div>
                  <h3 className="font-medium flex items-center gap-2">
                    <span>{ROOM_TYPE_ICON[room.type]}</span>
                    {room.name}
                  </h3>
                  <p className="text-xs text-stone-400 mt-0.5">
                    {inspo?.styleTheme || project.overallStyleTheme} · {scheme}
                    {requirement?.mustHaveItems?.length
                      ? ` · ${requirement.mustHaveItems.length} must-haves`
                      : ""}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[11px] text-stone-400">
                    {iteration}/{MAX_ITERATIONS_PER_ROOM} generations used
                  </span>
                  <button
                    type="button"
                    disabled={generating || maxed}
                    onClick={() => runGeneration(room.id)}
                    className="inline-flex items-center gap-2 rounded-full bg-stone-900 px-4 py-2 text-xs font-medium text-white hover:bg-stone-700 disabled:opacity-40 disabled:pointer-events-none"
                  >
                    {generating ? (
                      <>
                        <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                        Generating…
                      </>
                    ) : iteration === 0 ? (
                      "Generate concepts"
                    ) : maxed ? (
                      "Iteration limit reached"
                    ) : (
                      "Regenerate"
                    )}
                  </button>
                </div>
              </div>

              {gen?.images?.length ? (
                <div className="grid sm:grid-cols-3 gap-4">
                  {gen.images.map((img) => (
                    <ConceptCard key={img.id} room={room} image={img} swatches={swatches} />
                  ))}
                </div>
              ) : (
                <div className="rounded-xl border border-dashed border-stone-200 py-8 text-center text-sm text-stone-400">
                  No concepts generated yet
                </div>
              )}
            </div>
          );
        })}
      </div>

      <StepFooter backHref="/project/requirements" />

      <div className="no-print mt-10 rounded-2xl border border-amber-200 bg-amber-50 p-6">
        <h3 className="font-medium text-stone-800 mb-1">Share with your designer</h3>
        <p className="text-sm text-stone-600 mb-4">
          Everything above — floor plan, per-room theme, must-haves and concepts —
          rolls up into one design brief the designer can open directly, cutting
          out the back-and-forth screenshots and voice notes.
        </p>
        <a
          href="/brief"
          className="inline-flex items-center gap-2 rounded-full bg-stone-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-stone-700"
        >
          View design brief →
        </a>
      </div>
    </div>
  );
}
