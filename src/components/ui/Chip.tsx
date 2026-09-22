import { cx } from "@/lib/utils";

export function Chip({
  active,
  onClick,
  children,
  swatches,
}: {
  active?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
  swatches?: string[];
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cx(
        "flex items-center gap-2 rounded-xl border px-3 py-2 text-sm text-left transition-colors",
        active
          ? "border-stone-900 bg-stone-900 text-white"
          : "border-stone-200 bg-white text-stone-700 hover:border-stone-400"
      )}
    >
      {swatches && (
        <span className="flex -space-x-1 shrink-0">
          {swatches.slice(0, 4).map((c, i) => (
            <span
              key={i}
              className="h-4 w-4 rounded-full"
              style={{
                backgroundColor: c,
                boxShadow: `0 0 0 2px ${active ? "#1c1a17" : "#fff"}`,
              }}
            />
          ))}
        </span>
      )}
      <span>{children}</span>
    </button>
  );
}

export function Tag({ children, onRemove }: { children: React.ReactNode; onRemove?: () => void }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-stone-100 px-3 py-1 text-xs font-medium text-stone-700">
      {children}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          className="text-stone-400 hover:text-stone-700"
          aria-label="remove"
        >
          ×
        </button>
      )}
    </span>
  );
}
