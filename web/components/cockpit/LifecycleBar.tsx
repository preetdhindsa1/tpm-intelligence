const STEPS = ["Plan", "Build", "Freeze", "Launch", "Learn"] as const;

export function LifecycleBar({ stage }: { stage: string }) {
  return (
    <ol aria-label="Lifecycle" className="flex flex-wrap gap-2 text-sm">
      {STEPS.map((step) => {
        const here = step === stage;
        return (
          <li key={step} aria-current={here ? "step" : undefined} className={`inline-flex min-h-11 items-center rounded-full px-3 ${here ? "bg-action font-medium text-white" : "bg-white text-slate-600"}`}>
            {step}
          </li>
        );
      })}
      {stage === "Dates not known" && <li className="inline-flex min-h-11 items-center text-slate-500">Dates not known</li>}
    </ol>
  );
}
