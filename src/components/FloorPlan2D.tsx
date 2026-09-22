"use client";

import { DetectedRoom, RoomInspo } from "@/lib/types";
import { COLOR_SCHEME_SWATCHES, ROOM_TYPE_LABEL } from "@/lib/data/catalog";

export function FloorPlan2D({
  rooms,
  inspoByRoom,
  overallColorScheme,
}: {
  rooms: DetectedRoom[];
  inspoByRoom: Record<string, RoomInspo>;
  overallColorScheme: string | null;
}) {
  return (
    <div className="rounded-2xl border border-stone-200 bg-white p-4">
      <svg viewBox="0 0 100 75" className="w-full h-auto" style={{ aspectRatio: "4/3" }}>
        <rect x={0} y={0} width={100} height={75} fill="#faf9f7" />
        {rooms.map((room) => {
          const scheme = inspoByRoom[room.id]?.colorScheme || overallColorScheme || "Warm Neutrals";
          const fill = COLOR_SCHEME_SWATCHES[scheme]?.[0] ?? "#eee";
          const stroke = COLOR_SCHEME_SWATCHES[scheme]?.[2] ?? "#999";
          const x = room.bbox.x * 100;
          const y = room.bbox.y * 75;
          const w = room.bbox.w * 100;
          const h = room.bbox.h * 75;
          return (
            <g key={room.id}>
              <rect
                x={x}
                y={y}
                width={w}
                height={h}
                fill={fill}
                stroke={stroke}
                strokeWidth={0.4}
                rx={0.6}
              />
              <text
                x={x + w / 2}
                y={y + h / 2 - 1}
                textAnchor="middle"
                fontSize={2.6}
                fontWeight={600}
                fill="#3a352f"
              >
                {room.name}
              </text>
              <text
                x={x + w / 2}
                y={y + h / 2 + 3}
                textAnchor="middle"
                fontSize={1.9}
                fill="#7a736a"
              >
                {ROOM_TYPE_LABEL[room.type]}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
