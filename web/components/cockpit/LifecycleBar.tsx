const STEPS = ["Plan", "Build", "Freeze", "Launch", "Learn"] as const;

export function LifecycleBar({ stage }: { stage: string }) {
  const at = STEPS.indexOf(stage as (typeof STEPS)[number]);
  return (
    <ol aria-label="Lifecycle" className="flex flex-wrap gap-2 text-sm">
      {STEPS.map((step, index) => {
        const here = index === at;
        const done = at > index;
        const tone = here ? "bg-action font-medium text-white" : done ? "bg-action/20 font-medium text-action" : "bg-white text-slate-600";
        return (
          <li key={step} aria-current={here ? "step" : undefined} className={`inline-flex min-h-11 items-center rounded-full px-3 ${tone}`}>
            {step}
          </li>
        );
      })}
      {stage === "Dates not known" && <li className="inline-flex min-h-11 items-center text-slate-500">Dates not known</li>}
    </ol>
  );
}
