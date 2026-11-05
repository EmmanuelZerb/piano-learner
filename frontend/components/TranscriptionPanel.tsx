"use client";

import { useEffect, useState } from "react";

import { Slider } from "@/components/Slider";
import {
  getTranscription,
  getTranscriptionDefaults,
  mediaUrl,
  transcribeTrack,
  type Track,
  type TranscribeParams,
  type Transcription,
} from "@/lib/api";
import { STEM_LABELS } from "@/lib/stems";

type Props = { track: Track; onTranscribed: () => void };

const ENGINE_LABELS: Record<string, string> = {
  bytedance: "ByteDance (piano)",
  basic_pitch: "Basic Pitch",
};

export function TranscriptionPanel({ track, onTranscribed }: Props) {
  const [result, setResult] = useState<Transcription | null>(null);
  const [params, setParams] = useState<TranscribeParams | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      getTranscription(track.id, controller.signal),
      getTranscriptionDefaults(controller.signal),
    ])
      .then(([current, defaults]) => {
        setResult(current);
        setParams(current.params ?? defaults);
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : String(err));
      });
    return () => controller.abort();
  }, [track.id]);

  async function run() {
    if (!params) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await transcribeTrack(track.id, params));
      onTranscribed();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const setBasicPitch = (patch: Partial<TranscribeParams["basic_pitch"]>) =>
    setParams((p) => p && { ...p, basic_pitch: { ...p.basic_pitch, ...patch } });
  const setPiano = (patch: Partial<TranscribeParams["piano"]>) =>
    setParams((p) => p && { ...p, piano: { ...p.piano, ...patch } });

  return (
    <section className="rounded-xl border border-zinc-200 p-6 dark:border-zinc-800">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <h2 className="font-medium">Transcription MIDI</h2>
          <p className="text-sm text-zinc-500">
            Pistes : {track.transcribe_stems.map((s) => STEM_LABELS[s] ?? s).join(", ")}. La
            séparation est lancée automatiquement si besoin.
          </p>
        </div>
        <button
          onClick={run}
          disabled={busy || !params}
          className="shrink-0 rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {busy ? "Transcription…" : result?.available ? "Retranscrire" : "Transcrire"}
        </button>
      </div>

      {params && (
        <details className="mb-4 rounded-lg bg-zinc-50 p-4 dark:bg-zinc-900">
          <summary className="cursor-pointer text-sm font-medium">Réglages avancés</summary>
          <div className="mt-4 grid gap-6 sm:grid-cols-2">
            <div className="space-y-3">
              <p className="text-sm font-medium">Piste piano</p>
              <select
                value={params.piano_engine}
                onChange={(e) =>
                  setParams({
                    ...params,
                    piano_engine: e.target.value as TranscribeParams["piano_engine"],
                  })
                }
                className="w-full rounded border border-zinc-300 bg-transparent px-2 py-1 text-sm dark:border-zinc-700"
              >
                <option value="bytedance">ByteDance (précis, pédale de sustain)</option>
                <option value="basic_pitch">Basic Pitch</option>
              </select>
              {params.piano_engine === "bytedance" && (
                <>
                  <Slider
                    label="Seuil d'attaque"
                    hint="Plus haut = moins de notes fantômes"
                    value={params.piano.onset_threshold}
                    min={0.05}
                    max={0.95}
                    step={0.05}
                    onChange={(v) => setPiano({ onset_threshold: v })}
                  />
                  <Slider
                    label="Seuil de tenue"
                    hint="Plus haut = notes plus courtes"
                    value={params.piano.frame_threshold}
                    min={0.05}
                    max={0.95}
                    step={0.05}
                    onChange={(v) => setPiano({ frame_threshold: v })}
                  />
                </>
              )}
            </div>
            <div className="space-y-3">
              <p className="text-sm font-medium">Autres pistes (Basic Pitch)</p>
              <Slider
                label="Seuil d'attaque"
                hint="Plus haut = moins de notes, plus sûres"
                value={params.basic_pitch.onset_threshold}
                min={0.05}
                max={0.95}
                step={0.05}
                onChange={(v) => setBasicPitch({ onset_threshold: v })}
              />
              <Slider
                label="Seuil de tenue"
                hint="Plus haut = notes plus courtes"
                value={params.basic_pitch.frame_threshold}
                min={0.05}
                max={0.95}
                step={0.05}
                onChange={(v) => setBasicPitch({ frame_threshold: v })}
              />
              <Slider
                label="Durée minimale (ms)"
                hint="Supprime les notes plus courtes"
                value={params.basic_pitch.min_note_ms}
                min={20}
                max={500}
                step={10}
                onChange={(v) => setBasicPitch({ min_note_ms: v })}
              />
            </div>
          </div>
        </details>
      )}

      {busy && (
        <p className="mb-4 text-sm text-zinc-500">
          Transcription en cours (environ 10 à 60 s selon la longueur et le nombre de pistes)…
        </p>
      )}
      {error && <p className="mb-4 text-sm text-red-500">{error}</p>}

      {result?.available && (
        <>
          <table className="w-full text-sm">
            <thead className="text-left text-zinc-500">
              <tr>
                <th className="py-1 font-normal">Piste</th>
                <th className="font-normal">Moteur</th>
                <th className="text-right font-normal">Notes</th>
                <th className="text-right font-normal">MIDI</th>
              </tr>
            </thead>
            <tbody>
              {result.stems.map((s) => (
                <tr key={s.stem} className="border-t border-zinc-200 dark:border-zinc-800">
                  <td className="py-2">{STEM_LABELS[s.stem] ?? s.stem}</td>
                  <td className="text-zinc-500">
                    {ENGINE_LABELS[s.engine] ?? s.engine}
                    {s.cached && " · cache"}
                  </td>
                  <td className="text-right font-mono">
                    {s.notes}
                    {s.pedals > 0 && ` (+${s.pedals} péd.)`}
                  </td>
                  <td className="text-right">
                    <a href={mediaUrl(s.midi_url)} className="underline">
                      .mid
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {result.merged_url && (
            <a
              href={mediaUrl(result.merged_url)}
              className="mt-4 inline-block rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium dark:border-zinc-700"
            >
              Télécharger le MIDI fusionné
            </a>
          )}
          {result.elapsed_s !== null && (
            <p className="mt-2 text-xs text-zinc-500">Calculé en {result.elapsed_s} s.</p>
          )}
        </>
      )}
    </section>
  );
}
