"use client";

import { DetectedRoom, GeneratedImage } from "@/lib/types";
import { ROOM_TYPE_ICON } from "@/lib/data/catalog";

// Deterministic pseudo-random from a numeric seed, used only to vary the
// mock concept-card gradient so regenerated variants look distinct.
function seededRand(seed: number, salt: number) {
  const x = Math.sin(seed * 999 + salt * 137.13) * 10000;
  return x - Math.floor(x);
}

export function ConceptCard({
  room,
  image,
  swatches,
}: {
  room: DetectedRoom;
  image: GeneratedImage;
  swatches: string[];
}) {
  const a1 = Math.round(seededRand(image.seed, 1) * 100);
  const a2 = Math.round(seededRand(image.seed, 2) * 100);
  const angle = Math.round(seededRand(image.seed, 3) * 360);
  const [c1, c2, c3] = swatches;

  return (
    <div className="rounded-2xl border border-stone-200 bg-white overflow-hidden">
      <div
        className="relative aspect-[4/3] flex items-end p-4"
        style={{
          background: `radial-gradient(circle at ${a1}% ${a2}%, ${c3 ?? c2} 0%, transparent 60%), linear-gradient(${angle}deg, ${c1}, ${c2 ?? c1})`,
        }}
      >
        <span className="absolute top-3 left-3 rounded-full bg-black/30 backdrop-blur px-2 py-1 text-[10px] font-medium text-white tracking-wide">
          AI CONCEPT · MOCK
        </span>
        <span className="text-4xl drop-shadow-sm">{ROOM_TYPE_ICON[room.type]}</span>
      </div>
      <div className="p-3">
        <p className="text-xs text-stone-500 line-clamp-2">{image.promptSummary}</p>
      </div>
    </div>
  );
}
