'use client';

import { useState } from 'react';
import { runFlaskTest } from './actions';

export default function TestRunner() {
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const handleRunTest = async () => {
    setLoading(true);
    try {
      const data = await runFlaskTest();
      setResult(data);
    } catch (err) {
      setResult({ error: 'Failed' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-8 p-6 bg-white/5 rounded-xl border border-white/10">
      <h2 className="text-xl font-semibold mb-4">Infrastructure Test</h2>
      <button
        onClick={handleRunTest}
        disabled={loading}
        className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-md font-medium transition-colors disabled:opacity-50"
      >
        {loading ? 'Running...' : 'Run /flask/test-infrastructure'}
      </button>

      {result && (
        <div className="mt-4">
            <h3 className="text-sm font-medium text-gray-400 mb-2">Result:</h3>
            <pre className="bg-black/50 p-4 rounded-lg overflow-x-auto text-sm font-mono">
            {JSON.stringify(result, null, 2)}
            </pre>
        </div>
      )}
    </div>
  );
}
