import { Suspense } from "react";

import { TrackDetail } from "@/components/TrackDetail";

export default function TrackPage() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-6 py-16">
      <Suspense fallback={<p className="text-zinc-500">Chargement…</p>}>
        <TrackDetail />
      </Suspense>
    </main>
  );
}
