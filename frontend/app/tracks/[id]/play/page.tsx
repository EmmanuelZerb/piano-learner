import { Suspense } from "react";

import { PlayerView } from "@/components/player/PlayerView";

export default function PlayPage() {
  return (
    <Suspense fallback={<p className="p-6 text-zinc-500">Chargement du lecteur…</p>}>
      <PlayerView />
    </Suspense>
  );
}
