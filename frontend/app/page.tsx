import { HealthStatus } from "@/components/HealthStatus";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-6 py-16">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Piano Learner</h1>
        <p className="mt-2 text-zinc-500">
          Audio ou YouTube → séparation → transcription MIDI → notes qui tombent.
        </p>
      </header>
      <section className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800">
        <h2 className="mb-4 font-medium">État du système</h2>
        <HealthStatus />
      </section>
    </main>
  );
}
