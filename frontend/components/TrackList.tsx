"use client";

import { useEffect, useState } from "react";

import { listTracks, mediaUrl, type Track } from "@/lib/api";
import { formatDate, formatDuration } from "@/lib/format";

function TrackRow({ track }: { track: Track }) {
  return (
    <li className="flex gap-4 py-4">
      {track.thumbnail_url ? (
        // Image servie par l'API locale : l'optimisation de next/image n'apporte rien ici.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={mediaUrl(track.thumbnail_url)}
          alt=""
          className="h-16 w-28 shrink-0 rounded object-cover"
        />
      ) : (
        <div className="flex h-16 w-28 shrink-0 items-center justify-center rounded bg-zinc-100 text-2xl dark:bg-zinc-900">
          ♪
        </div>
      )}
      <div className="min-w-0 flex-1 space-y-2">
        <div>
          <p className="truncate font-medium">{track.title}</p>
          <p className="truncate text-sm text-zinc-500">
            {[
              track.artist,
              formatDuration(track.duration_s),
              track.source === "youtube" ? "YouTube" : "Fichier",
              formatDate(track.created_at),
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        <audio controls preload="none" src={mediaUrl(track.audio_url)} className="h-8 w-full" />
      </div>
    </li>
  );
}

export function TrackList({ refreshKey }: { refreshKey: number }) {
  const [tracks, setTracks] = useState<Track[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    listTracks(controller.signal)
      .then((data) => {
        setTracks(data);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err));
      });
    return () => controller.abort();
  }, [refreshKey]);

  if (error) return <p className="text-sm text-red-500">{error}</p>;
  if (tracks === null) return <p className="text-sm text-zinc-500">Chargement…</p>;
  if (tracks.length === 0)
    return <p className="text-sm text-zinc-500">Aucun morceau pour l&apos;instant.</p>;

  return (
    <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
      {tracks.map((t) => (
        <TrackRow key={t.id} track={t} />
      ))}
    </ul>
  );
}
