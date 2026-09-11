"use client";

import Link from "next/link";
import { useProject } from "@/lib/project-context";
import { COLOR_SCHEME_SWATCHES, HOUSING_TYPES, ROOM_TYPE_ICON, ROOM_TYPE_LABEL } from "@/lib/data/catalog";
import { FloorPlan2D } from "@/components/FloorPlan2D";
import { ConceptCard } from "@/components/ConceptCard";
import { Button } from "@/components/ui/Button";

export default function BriefPage() {
  const { project } = useProject();
  const housing = HOUSING_TYPES.find((h) => h.id === project.housingType);

  if (project.rooms.length === 0) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16 text-center">
        <p className="text-stone-600 mb-4">No project yet.</p>
        <Link href="/project/housing" className="text-stone-900 underline">
          Start a project
        </Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-stone-50">
      <header className="no-print sticky top-0 z-10 border-b border-stone-200 bg-white/90 backdrop-blur">
        <div className="mx-auto max-w-3xl px-6 py-4 flex items-center justify-between">
          <Link href="/project/results" className="text-sm text-stone-500 hover:text-stone-900">
            ← Back to results
          </Link>
          <Button size="sm" onClick={() => window.print()}>
            Print / Save as PDF
          </Button>
        </div>
      </header>

      <div className="mx-auto max-w-3xl px-6 py-12 print:py-0">
        <p className="text-xs uppercase tracking-widest text-amber-700 font-medium mb-2">
          Design Brief
        </p>
        <h1 className="font-display text-3xl font-medium mb-1">{project.projectName}</h1>
        <p className="text-stone-500 text-sm mb-10">
          {housing?.label} · {project.overallStyleTheme ?? "—"} · {project.overallColorScheme ?? "—"}
        </p>

        <section className="mb-12">
          <h2 className="font-display text-xl font-medium mb-4">2D Floor Plan</h2>
          <FloorPlan2D
            rooms={project.rooms}
            inspoByRoom={project.inspoByRoom}
            overallColorScheme={project.overallColorScheme}
          />
        </section>

        <section className="space-y-10">
          {project.rooms.map((room) => {
            const inspo = project.inspoByRoom[room.id];
            const requirement = project.requirementsByRoom[room.id];
            const gen = project.generationsByRoom[room.id];
            const scheme = inspo?.colorScheme || project.overallColorScheme || "Warm Neutrals";
            const swatches = COLOR_SCHEME_SWATCHES[scheme] ?? [];

            return (
              <div key={room.id} className="break-inside-avoid border-t border-stone-200 pt-6">
                <h3 className="font-display text-lg font-medium flex items-center gap-2 mb-1">
                  <span>{ROOM_TYPE_ICON[room.type]}</span>
                  {room.name}
                  <span className="text-xs font-sans font-normal text-stone-400">
                    {ROOM_TYPE_LABEL[room.type]}
                  </span>
                </h3>
                <p className="text-xs text-stone-500 mb-3">
                  {inspo?.styleTheme || project.overallStyleTheme} · {scheme}
                </p>

                <div className="flex gap-1.5 mb-3">
                  {swatches.map((c) => (
                    <span key={c} className="h-5 w-5 rounded-full border border-white shadow" style={{ backgroundColor: c }} />
                  ))}
                </div>

                {!!requirement?.mustHaveItems?.length && (
                  <div className="mb-3">
                    <p className="text-xs font-medium text-stone-600 mb-1">Must-haves</p>
                    <div className="flex flex-wrap gap-1.5">
                      {requirement.mustHaveItems.map((item) => (
                        <span key={item} className="rounded-full bg-stone-100 px-2.5 py-1 text-xs text-stone-700">
                          {item}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {requirement?.prompt && (
                  <div className="mb-4">
                    <p className="text-xs font-medium text-stone-600 mb-1">Consumer notes</p>
                    <p className="text-sm text-stone-700 italic">&ldquo;{requirement.prompt}&rdquo;</p>
                  </div>
                )}

                {!!inspo?.images?.length && (
                  <div className="mb-4">
                    <p className="text-xs font-medium text-stone-600 mb-1.5">Inspo references</p>
                    <div className="flex flex-wrap gap-2">
                      {inspo.images.map((img) => (
                        <img
                          key={img.id}
                          src={img.dataUrl}
                          alt={img.name}
                          className="h-16 w-16 object-cover rounded-lg border border-stone-200"
                        />
                      ))}
                    </div>
                  </div>
                )}

                {!!gen?.images?.length ? (
                  <div className="grid grid-cols-3 gap-3">
                    {gen.images.map((img) => (
                      <ConceptCard key={img.id} room={room} image={img} swatches={swatches} />
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-stone-400">No AI concepts generated for this room yet.</p>
                )}
              </div>
            );
          })}
        </section>

        <footer className="no-print mt-16 pt-6 border-t border-stone-200 text-xs text-stone-400">
          Generated by Roomly — design inspiration agent prototype.
        </footer>
      </div>
    </div>
  );
}
