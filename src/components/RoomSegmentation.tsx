"use client";

import { DetectedRoom, RoomType, UploadedImage } from "@/lib/types";
import { ROOM_TYPE_ICON, ROOM_TYPE_LABEL } from "@/lib/data/catalog";
import { uid } from "@/lib/utils";

const ROOM_TYPES = Object.keys(ROOM_TYPE_LABEL) as RoomType[];

const OVERLAY_COLORS = [
  "border-amber-600 bg-amber-500/10",
  "border-sky-600 bg-sky-500/10",
  "border-emerald-600 bg-emerald-500/10",
  "border-rose-600 bg-rose-500/10",
  "border-violet-600 bg-violet-500/10",
  "border-orange-600 bg-orange-500/10",
  "border-teal-600 bg-teal-500/10",
  "border-fuchsia-600 bg-fuchsia-500/10",
];

export function RoomOverlay({
  image,
  rooms,
}: {
  image: UploadedImage | null;
  rooms: DetectedRoom[];
}) {
  return (
    <div className="relative w-full overflow-hidden rounded-2xl border border-stone-200 bg-stone-50 aspect-[4/3]">
      {image ? (
        <img src={image.dataUrl} alt="" className="absolute inset-0 h-full w-full object-contain" />
      ) : (
        <div className="absolute inset-0 flex items-center justify-center text-stone-300 text-sm">
          No floor plan uploaded
        </div>
      )}
      {rooms.map((room, i) => (
        <div
          key={room.id}
          className={`absolute border-2 rounded-md flex items-start justify-start p-1.5 ${OVERLAY_COLORS[i % OVERLAY_COLORS.length]}`}
          style={{
            left: `${room.bbox.x * 100}%`,
            top: `${room.bbox.y * 100}%`,
            width: `${room.bbox.w * 100}%`,
            height: `${room.bbox.h * 100}%`,
          }}
        >
          <span className="rounded bg-white/90 px-1.5 py-0.5 text-[10px] font-medium text-stone-800 leading-tight shadow-sm">
            {ROOM_TYPE_ICON[room.type]} {room.name}
          </span>
        </div>
      ))}
    </div>
  );
}

export function RoomList({
  rooms,
  onUpdate,
  onRemove,
  onAdd,
}: {
  rooms: DetectedRoom[];
  onUpdate: (roomId: string, patch: Partial<DetectedRoom>) => void;
  onRemove: (roomId: string) => void;
  onAdd: (room: DetectedRoom) => void;
}) {
  return (
    <div className="space-y-2">
      {rooms.map((room) => (
        <div
          key={room.id}
          className="flex items-center gap-3 rounded-xl border border-stone-200 bg-white px-3 py-2.5"
        >
          <span className="text-lg shrink-0">{ROOM_TYPE_ICON[room.type]}</span>
          <input
            value={room.name}
            onChange={(e) => onUpdate(room.id, { name: e.target.value })}
            className="flex-1 min-w-0 rounded-lg border border-transparent bg-transparent px-2 py-1 text-sm font-medium hover:border-stone-200 focus:border-stone-400 focus:outline-none"
          />
          <select
            value={room.type}
            onChange={(e) => onUpdate(room.id, { type: e.target.value as RoomType })}
            className="rounded-lg border border-stone-200 bg-white px-2 py-1 text-xs text-stone-600"
          >
            {ROOM_TYPES.map((t) => (
              <option key={t} value={t}>
                {ROOM_TYPE_LABEL[t]}
              </option>
            ))}
          </select>
          <span className="text-[10px] text-stone-400 w-10 text-right shrink-0">
            {Math.round(room.confidence * 100)}%
          </span>
          <button
            type="button"
            onClick={() => onRemove(room.id)}
            className="text-stone-400 hover:text-red-600 text-sm shrink-0"
            aria-label="Remove room"
          >
            ×
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() =>
          onAdd({
            id: uid("room"),
            name: "New Room",
            type: "other",
            bbox: { x: 0.05, y: 0.05, w: 0.3, h: 0.3 },
            confidence: 1,
          })
        }
        className="w-full rounded-xl border border-dashed border-stone-300 px-3 py-2.5 text-sm text-stone-500 hover:border-stone-400 hover:text-stone-700"
      >
        + Add a room manually
      </button>
    </div>
  );
}
