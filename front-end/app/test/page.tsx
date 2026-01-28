import { getFlaskStatus } from './actions';
import TestRunner from './TestRunner';

export default async function TestPage() {
  const flaskStatus = await getFlaskStatus();

  return (
    <main className="min-h-screen p-8 max-w-4xl mx-auto font-sans">
      <h1 className="text-3xl font-bold mb-8">System Status Check</h1>

      <div className="space-y-6">
        <section className="p-6 bg-white/5 rounded-xl border border-white/10">
          <h2 className="text-xl font-semibold mb-4">Flask Service Status (GET /flask)</h2>
          <pre className="bg-black/50 p-4 rounded-lg overflow-x-auto text-sm font-mono">
            {JSON.stringify(flaskStatus, null, 2)}
          </pre>
        </section>

        <TestRunner />
      </div>
    </main>
  );
}
