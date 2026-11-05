"use client";

import { useState } from "react";

import { HealthStatus } from "@/components/HealthStatus";
import { ImportPanel } from "@/components/ImportPanel";
import { TrackList } from "@/components/TrackList";

export default function Home() {
  const [refreshKey, setRefreshKey] = useState(0);

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-6 py-16">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Piano Learner</h1>
        <p className="mt-2 text-zinc-500">
          Audio ou YouTube → séparation → transcription MIDI → notes qui tombent.
        </p>
      </header>

      <section className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800">
        <h2 className="mb-4 font-medium">Importer un morceau</h2>
        <ImportPanel onImported={() => setRefreshKey((k) => k + 1)} />
      </section>

      <section className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800">
        <h2 className="mb-2 font-medium">Bibliothèque</h2>
        <TrackList refreshKey={refreshKey} />
      </section>

      <details className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800">
        <summary className="cursor-pointer font-medium">État du système</summary>
        <div className="mt-4">
          <HealthStatus />
        </div>
      </details>
    </main>
  );
}
