"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { StemsPanel } from "@/components/StemsPanel";
import { TranscriptionPanel } from "@/components/TranscriptionPanel";
import { getTrack, mediaUrl, type Track } from "@/lib/api";
import { formatDuration } from "@/lib/format";

export function TrackDetail() {
  const { id } = useParams<{ id: string }>();
  const [track, setTrack] = useState<Track | null>(null);
  const [error, setError] = useState<string | null>(null);
  // La transcription peut déclencher la séparation : on recharge alors la liste des stems.
  const [stemsVersion, setStemsVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    getTrack(id, controller.signal)
      .then(setTrack)
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err));
      });
    return () => controller.abort();
  }, [id]);

  if (error) return <p className="text-red-500">{error}</p>;
  if (!track) return <p className="text-zinc-500">Chargement…</p>;

  return (
    <>
      <Link href="/" className="text-sm text-zinc-500 hover:underline">
        ← Bibliothèque
      </Link>
      <header className="flex gap-4">
        {track.thumbnail_url && (
          // Image servie par l'API locale : l'optimisation de next/image n'apporte rien ici.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={mediaUrl(track.thumbnail_url)}
            alt=""
            className="h-20 w-36 rounded object-cover"
          />
        )}
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold">{track.title}</h1>
          <p className="text-zinc-500">
            {[track.artist, formatDuration(track.duration_s)].filter(Boolean).join(" · ")}
          </p>
        </div>
      </header>

      <section className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800">
        <h2 className="mb-3 font-medium">Mixage original</h2>
        <audio controls preload="none" src={mediaUrl(track.audio_url)} className="w-full" />
      </section>

      <StemsPanel key={stemsVersion} track={track} onTrackChange={setTrack} />
      <TranscriptionPanel track={track} onTranscribed={() => setStemsVersion((v) => v + 1)} />
    </>
  );
}
