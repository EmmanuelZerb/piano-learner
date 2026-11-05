"use client";

import { useEffect, useState } from "react";

import { Slider } from "@/components/Slider";
import {
  arrangeTrack,
  getArrangement,
  getArrangementDefaults,
  mediaUrl,
  type Arrangement,
  type PostprocessParams,
} from "@/lib/api";
import { keyName, LEVEL_LABELS, pitchName } from "@/lib/music";

const QUANTIZE_LABELS: Record<PostprocessParams["quantize"], string> = {
  none: "Aucune",
  eighth: "Croche",
  sixteenth: "Double croche",
  triplet: "Triolet de croches",
};

export function ArrangementPanel({ trackId }: { trackId: string }) {
  const [result, setResult] = useState<Arrangement | null>(null);
  const [params, setParams] = useState<PostprocessParams | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      getArrangement(trackId, controller.signal),
      getArrangementDefaults(controller.signal),
    ])
      .then(([current, defaults]) => {
        setResult(current);
        setParams(current.params ?? defaults);
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err));
      });
    return () => controller.abort();
  }, [trackId]);

  async function run() {
    if (!params) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await arrangeTrack(trackId, params));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const set = (patch: Partial<PostprocessParams>) => setParams((p) => p && { ...p, ...patch });

  if (!result?.available && !error) {
    return (
      <section className="rounded-xl border border-zinc-200 p-6 text-sm text-zinc-500 dark:border-zinc-800">
        <h2 className="mb-1 font-medium text-current">Niveaux de difficulté</h2>
        Disponibles après la transcription.
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <h2 className="font-medium">Niveaux de difficulté</h2>
          {result?.available && (
            <p className="text-sm text-zinc-500">
              {result.tempo} BPM
              {result.key && ` · ${keyName(result.key)}`}
              {result.chords ? ` · ${result.chords} changements d'accord` : ""}
            </p>
          )}
        </div>
        <button
          onClick={run}
          disabled={busy || !params}
          className="shrink-0 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {busy ? "Calcul…" : "Recalculer"}
        </button>
      </div>

      {params && (
        <details className="mb-4 rounded-lg bg-zinc-50 p-4 dark:bg-zinc-900">
          <summary className="cursor-pointer text-sm font-medium">
            Réglages du nettoyage (sans relancer la transcription)
          </summary>
          <div className="mt-4 grid gap-6 sm:grid-cols-2">
            <div className="space-y-3">
              <label className="block text-sm">
                Quantification
                <select
                  value={params.quantize}
                  onChange={(e) =>
                    set({ quantize: e.target.value as PostprocessParams["quantize"] })
                  }
                  className="mt-1 w-full rounded border border-zinc-300 bg-transparent px-2 py-1 dark:border-zinc-700"
                >
                  {Object.entries(QUANTIZE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <Slider
                label="Intensité"
                hint="0 % = rythme joué, 100 % = aligné sur la grille"
                value={params.quantize_strength}
                min={0}
                max={100}
                step={5}
                unit=" %"
                onChange={(v) => set({ quantize_strength: v })}
              />
              <Slider
                label="Durée minimale"
                hint="Supprime les notes plus courtes"
                value={params.min_note_ms}
                min={0}
                max={300}
                step={10}
                unit=" ms"
                onChange={(v) => set({ min_note_ms: v })}
              />
              <Slider
                label="Vélocité minimale"
                hint="Supprime les notes jouées trop doucement (souvent des fantômes)"
                value={params.min_velocity}
                min={1}
                max={80}
                step={1}
                onChange={(v) => set({ min_velocity: v })}
              />
            </div>
            <div className="space-y-3">
              <Slider
                label={`Partage des mains : ${pitchName(params.split_point)}`}
                hint="Point de départ ; il suit ensuite le registre joué"
                value={params.split_point}
                min={48}
                max={72}
                step={1}
                onChange={(v) => set({ split_point: v })}
              />
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={params.dynamic_split}
                  onChange={(e) => set({ dynamic_split: e.target.checked })}
                />
                Partage dynamique
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={params.melody_from_vocals}
                  onChange={(e) => set({ melody_from_vocals: e.target.checked })}
                />
                Mélodie débutant tirée de la voix (si transcrite)
              </label>
            </div>
          </div>
        </details>
      )}

      {error && <p className="mb-4 text-sm text-red-500">{error}</p>}

      {result?.available && (
        <ul className="grid gap-3 sm:grid-cols-3">
          {result.levels.map((lvl) => (
            <li
              key={lvl.level}
              className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800"
            >
              <p className="font-medium">{LEVEL_LABELS[lvl.level]}</p>
              <p className="mt-1 text-sm text-zinc-500">
                Droite : {lvl.right_notes} notes (≤ {lvl.max_polyphony_right} à la fois)
                <br />
                Gauche : {lvl.left_notes} notes (≤ {lvl.max_polyphony_left} à la fois)
              </p>
              <a href={mediaUrl(lvl.midi_url)} className="mt-2 inline-block text-sm underline">
                Télécharger le MIDI
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
