import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-50">
      <main className="mx-auto flex min-h-screen max-w-5xl flex-col justify-center px-6 py-16">
        <div className="space-y-6">
          <p className="text-sm uppercase tracking-[0.3em] text-zinc-400">
            Trip Copilot
          </p>
          <h1 className="text-4xl font-semibold leading-tight sm:text-5xl">
            Let the agents build your next joyful escape.
          </h1>
          <p className="max-w-2xl text-lg text-zinc-300">
            Tell us your days, budget, and group type. Our multi-agent system
            finds the best destinations and explains why.
          </p>
          <div className="flex flex-wrap gap-4">
            <Link
              className="rounded-full bg-white px-6 py-3 text-sm font-semibold text-zinc-900 transition hover:bg-zinc-200"
              href="/journey"
            >
              Start the Journey
            </Link>
            <div className="rounded-full border border-zinc-700 px-6 py-3 text-sm text-zinc-300">
              Powered by MCP tool calling
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
