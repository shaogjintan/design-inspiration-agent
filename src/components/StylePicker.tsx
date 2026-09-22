"use client";

import { COLOR_SCHEMES, COLOR_SCHEME_SWATCHES, STYLE_THEMES } from "@/lib/data/catalog";
import { Chip } from "@/components/ui/Chip";

export function StylePicker({
  colorScheme,
  styleTheme,
  onColorScheme,
  onStyleTheme,
}: {
  colorScheme: string | null;
  styleTheme: string | null;
  onColorScheme: (v: string) => void;
  onStyleTheme: (v: string) => void;
}) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-medium text-stone-700 mb-3">Colour scheme</h3>
        <div className="flex flex-wrap gap-2">
          {COLOR_SCHEMES.map((c) => (
            <Chip
              key={c}
              active={colorScheme === c}
              onClick={() => onColorScheme(c)}
              swatches={COLOR_SCHEME_SWATCHES[c]}
            >
              {c}
            </Chip>
          ))}
        </div>
      </div>
      <div>
        <h3 className="text-sm font-medium text-stone-700 mb-3">Style theme</h3>
        <div className="flex flex-wrap gap-2">
          {STYLE_THEMES.map((t) => (
            <Chip key={t} active={styleTheme === t} onClick={() => onStyleTheme(t)}>
              {t}
            </Chip>
          ))}
        </div>
      </div>
    </div>
  );
}
