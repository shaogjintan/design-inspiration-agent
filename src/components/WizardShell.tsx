"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { WIZARD_STEPS } from "@/lib/steps";
import { cx } from "@/lib/utils";
import { useProject } from "@/lib/project-context";

export function WizardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { project } = useProject();
  const activeIndex = WIZARD_STEPS.findIndex((s) => s.path === pathname);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="no-print border-b border-stone-200 bg-white/80 backdrop-blur sticky top-0 z-10">
        <div className="mx-auto max-w-5xl px-6 py-4 flex items-center justify-between">
          <Link href="/" className="font-display text-xl font-semibold tracking-tight">
            Roomly
          </Link>
          <span className="text-sm text-stone-500 truncate max-w-[40%]">
            {project.projectName}
          </span>
        </div>
        <div className="mx-auto max-w-5xl px-6 pb-4">
          <ol className="flex items-center gap-2 sm:gap-4">
            {WIZARD_STEPS.map((step, i) => {
              const isActive = i === activeIndex;
              const isDone = activeIndex > i;
              return (
                <li key={step.path} className="flex items-center gap-2 sm:gap-4 flex-1">
                  <Link
                    href={step.path}
                    className="flex items-center gap-2 group min-w-0"
                  >
                    <span
                      className={cx(
                        "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                        isActive
                          ? "bg-stone-900 text-white"
                          : isDone
                          ? "bg-amber-700 text-white"
                          : "bg-stone-200 text-stone-500"
                      )}
                    >
                      {isDone ? "✓" : i + 1}
                    </span>
                    <span
                      className={cx(
                        "text-xs sm:text-sm truncate",
                        isActive ? "text-stone-900 font-medium" : "text-stone-500"
                      )}
                    >
                      {step.short}
                    </span>
                  </Link>
                  {i < WIZARD_STEPS.length - 1 && (
                    <div
                      className={cx(
                        "h-px flex-1",
                        isDone ? "bg-amber-700" : "bg-stone-200"
                      )}
                    />
                  )}
                </li>
              );
            })}
          </ol>
        </div>
      </header>
      <main className="flex-1 mx-auto w-full max-w-5xl px-6 py-10">{children}</main>
    </div>
  );
}

export function StepFooter({
  backHref,
  nextHref,
  onNext,
  nextLabel = "Continue",
  nextDisabled,
}: {
  backHref?: string;
  nextHref?: string;
  onNext?: () => void;
  nextLabel?: string;
  nextDisabled?: boolean;
}) {
  return (
    <div className="no-print mt-10 flex items-center justify-between border-t border-stone-200 pt-6">
      {backHref ? (
        <Link href={backHref} className="text-sm text-stone-500 hover:text-stone-900">
          ← Back
        </Link>
      ) : (
        <span />
      )}
      {nextHref && !onNext ? (
        <Link
          href={nextDisabled ? "#" : nextHref}
          aria-disabled={nextDisabled}
          className={cx(
            "inline-flex items-center gap-2 rounded-full bg-stone-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-stone-700",
            nextDisabled && "pointer-events-none opacity-40"
          )}
        >
          {nextLabel} →
        </Link>
      ) : (
        <button
          type="button"
          disabled={nextDisabled}
          onClick={onNext}
          className="inline-flex items-center gap-2 rounded-full bg-stone-900 px-5 py-2.5 text-sm font-medium text-white hover:bg-stone-700 disabled:opacity-40 disabled:pointer-events-none"
        >
          {nextLabel} →
        </button>
      )}
    </div>
  );
}
