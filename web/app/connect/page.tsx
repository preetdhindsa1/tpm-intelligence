import { CONNECTORS, PROMISES, STEPS } from "@/lib/connect";

export const dynamic = "force-dynamic";

export default function ConnectPage() {
  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-2xl font-semibold">Connect your tools</h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-600">
          A company plugs in through a connector and a release calendar. Signing a company up is not open on this page.
        </p>
      </header>

      <ol className="grid gap-4 md:grid-cols-3">
        {STEPS.map((step, index) => (
          <li key={step.title} className="rounded-lg border bg-white p-4">
            <p className="text-xs font-semibold text-slate-400">{index + 1}</p>
            <h2 className="mt-1 font-semibold">{step.title}</h2>
            <p className="mt-2 text-sm text-slate-600">{step.body}</p>
          </li>
        ))}
      </ol>

      <section>
        <h2 className="text-lg font-semibold">Connector status</h2>
        <ul className="mt-3 divide-y rounded-lg border bg-white">
          {CONNECTORS.map((item) => (
            <li key={item.name} className="px-4 py-3">
              <p className="font-medium">{item.name}</p>
              <p className="text-sm text-slate-600">{item.usedFor}</p>
              <p className="mt-1 text-xs text-slate-500">{item.status}</p>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="text-lg font-semibold">What stays true when a company plugs in</h2>
        <ul className="mt-3 grid gap-3 md:grid-cols-3">
          {PROMISES.map((item) => (
            <li key={item.title} className="rounded-lg border bg-white p-4">
              <h3 className="font-semibold">{item.title}</h3>
              <p className="mt-2 text-sm text-slate-600">{item.body}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
