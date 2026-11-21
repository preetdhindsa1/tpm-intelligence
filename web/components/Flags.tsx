import type { Flag } from "@/lib/api";
import { sortFlags } from "@/lib/format";

const STYLE = {
  critical: "bg-rose-100 text-rose-800 ring-rose-200",
  warning: "bg-amber-100 text-amber-800 ring-amber-200",
  info: "bg-sky-100 text-sky-800 ring-sky-200",
};

export function FlagChips({ flags }: { flags: Flag[] }) {
  if (!flags.length) return <span className="text-xs text-slate-400">none</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {sortFlags(flags).map((f) => (
        <span key={f.code + f.message} title={f.message} className={`rounded px-1.5 py-0.5 text-[11px] ring-1 ${STYLE[f.severity]}`}>
          {f.code.replaceAll("_", " ")}
        </span>
      ))}
    </div>
  );
}

export function FlagList({ flags }: { flags: Flag[] }) {
  if (!flags.length) return <p className="text-sm text-slate-500">No flags.</p>;
  return (
    <ul className="space-y-2">
      {sortFlags(flags).map((f) => (
        <li key={f.code + f.message} className={`rounded p-2 text-sm ring-1 ${STYLE[f.severity]}`}>
          <span className="font-medium">{f.code.replaceAll("_", " ")}</span>: {f.message}
        </li>
      ))}
    </ul>
  );
}
