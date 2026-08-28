const SERVICES = [
  { name: 'db', carries: 'Events, state, ledger and configuration', phase: 'T-007' },
  { name: 'api', carries: 'Health endpoint only', phase: 'T-080' },
  { name: 'worker', carries: 'Cycle loop, no forecaster attached', phase: 'T-050' },
  { name: 'sim', carries: 'Service only, no line model attached', phase: 'T-020' },
  { name: 'web', carries: 'Design tokens and this page', phase: 'T-087' },
];

export default function Page() {
  return (
    <>
      <h1>Build status</h1>
      <p className="mt-4 text-ink-2">
        Phase 0 of docs/ai/TASKS.md is in place: the repository skeleton, continuous
        integration, the five-service stack, the design tokens, the lint suite, the
        database schema, and the two line configurations. Line view arrives in Phase 3.
      </p>
      <table className="mt-8 border-collapse text-body">
        <thead>
          <tr className="bg-paper-sunk">
            <th className="border border-rule px-3 py-2 text-left text-label">Service</th>
            <th className="border border-rule px-3 py-2 text-left text-label">
              What it carries today
            </th>
            <th className="border border-rule px-3 py-2 text-left text-label">
              Completed by
            </th>
          </tr>
        </thead>
        <tbody>
          {SERVICES.map((service) => (
            <tr key={service.name}>
              <td className="border border-rule px-3 py-2 font-mono">{service.name}</td>
              <td className="border border-rule px-3 py-2">{service.carries}</td>
              <td className="border border-rule px-3 py-2 font-mono">{service.phase}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
