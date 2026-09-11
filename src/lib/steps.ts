export interface WizardStep {
  path: string;
  label: string;
  short: string;
}

export const WIZARD_STEPS: WizardStep[] = [
  { path: "/project/housing", label: "Housing & Floor Plan", short: "Floor Plan" },
  { path: "/project/inspiration", label: "Inspiration & Theme", short: "Inspiration" },
  { path: "/project/requirements", label: "Room Requirements", short: "Requirements" },
  { path: "/project/results", label: "AI Suggestions", short: "Results" },
];
