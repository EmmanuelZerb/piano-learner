"use client";

import { useEffect, useState } from "react";

import { getStems, mediaUrl, updateTranscribeStems, type Stems, type Track } from "@/lib/api";
import { isTranscribable, STEM_LABELS, STEM_ORDER, toggleStem } from "@/lib/stems";

type Props = {
  track: Track;
  onTrackChange: (track: Track) => void;
  busy: boolean; // une tâche tourne déjà sur ce morceau
  onSeparate: () => void;
};

export function StemsPanel({ track, onTrackChange, busy, onSeparate }: Props) {
  const [stems, setStems] = useState<Stems | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getStems(track.id, controller.signal)
      .then(setStems)
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err));
      });
    return () => controller.abort();
  }, [track.id]);

  async function toggle(stem: string) {
    const next = toggleStem(track.transcribe_stems, stem);
    if (next === track.transcribe_stems) return;
    onTrackChange({ ...track, transcribe_stems: next });
    try {
      onTrackChange(await updateTranscribeStems(track.id, next));
    } catch (err) {
      onTrackChange(track);
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const urls = new Map(stems?.stems.map((s) => [s.name, mediaUrl(s.url)]));

  return (
    <section className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <h2 className="font-medium">Pistes séparées</h2>
          <p className="text-sm text-zinc-500">
            Coche les pistes à transcrire en notes (par défaut : la prod sans voix ni batterie).
          </p>
        </div>
        {stems && !stems.available && (
          <button
            onClick={onSeparate}
            disabled={busy}
            className="shrink-0 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
          >
            Séparer les pistes
          </button>
        )}
      </div>

      {error && <p className="mb-4 text-sm text-red-500">{error}</p>}

      <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
        {STEM_ORDER.map((stem) => (
          <li key={stem} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3">
            <label className="flex w-56 items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={track.transcribe_stems.includes(stem)}
                disabled={!isTranscribable(stem)}
                onChange={() => void toggle(stem)}
              />
              {STEM_LABELS[stem]}
            </label>
            {urls.has(stem) ? (
              <audio controls preload="none" src={urls.get(stem)} className="h-8 min-w-0 flex-1" />
            ) : (
              <span className="text-sm text-zinc-400">pas encore séparée</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
