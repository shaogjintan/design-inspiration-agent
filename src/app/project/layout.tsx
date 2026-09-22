"use client";

import { WizardShell } from "@/components/WizardShell";

export default function ProjectLayout({ children }: { children: React.ReactNode }) {
  return <WizardShell>{children}</WizardShell>;
}
