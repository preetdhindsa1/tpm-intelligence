// Shown on every page of a sample-data project (the demo team, ADR-0020), so its numbers
// are never mistaken for a real project's.
export function SampleDataBanner() {
  return (
    <p role="note" className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
      <strong className="font-semibold">Sample data.</strong> This demo team is a repository the owner controls, with activity
      created by a script to show webhooks end to end. It is not a real project, and its numbers are kept apart from
      Kubernetes and Apache Kafka.
    </p>
  );
}
