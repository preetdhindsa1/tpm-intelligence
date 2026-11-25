// Shared empty, loading, and error states. The detail of an error is the failure
// the API or the page already has. These components add no numbers.

export function LoadingState({ label }: { label: string }) {
  return (
    <p className="text-sm text-slate-600" role="status">
      {label}
    </p>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <section className="rounded-lg border bg-white p-4">
      <h2 className="font-semibold text-slate-800">{title}</h2>
      <p className="mt-1 text-sm text-slate-600">{body}</p>
    </section>
  );
}

export function ErrorState({ title, detail }: { title: string; detail: string }) {
  return (
    <section className="rounded-lg border border-critical/30 bg-critical-bg p-4" role="alert">
      <h2 className="font-semibold text-critical">{title}</h2>
      <p className="mt-1 text-sm text-critical">{detail}</p>
    </section>
  );
}
