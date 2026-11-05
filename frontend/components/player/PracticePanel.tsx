"use client";

import { useEffect, useState } from "react";

import { getPracticeHistory, type PracticeHistory } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { LEVEL_LABELS } from "@/lib/music";
import type { MidiDevice } from "@/lib/player/midi";
import { accuracy, type PracticeHands, type PracticeMode } from "@/lib/player/practice";
import { usePlayerStore } from "@/lib/player/store";

type MidiState = {
  connected: boolean;
  devices: MidiDevice[];
  error: string | null;
  connect: () => Promise<void>;
};

const MODE_LABELS: Record<PracticeMode, string> = {
  off: "Désactivé",
  wait: "Attente (la lecture attend la bonne note)",
  free: "Libre (justes / fausses en direct)",
};
const HANDS_LABELS: Record<PracticeHands, string> = {
  R: "Main droite (la gauche est jouée)",
  L: "Main gauche (la droite est jouée)",
  LR: "Deux mains",
};
const MODE_SHORT = { wait: "attente", free: "libre" } as const;

const percent = (value: number) => `${Math.round(value * 100)} %`;

export function PracticePanel(props: { trackId: string; midi: MidiState; onFinish: () => void }) {
  const { trackId, midi, onFinish } = props;
  const s = usePlayerStore();
  const [history, setHistory] = useState<PracticeHistory | null>(null);
  const saved = s.summary?.saved ?? false;

  useEffect(() => {
    const controller = new AbortController();
    getPracticeHistory(trackId, controller.signal)
      .then(setHistory)
      .catch(() => undefined);
    return () => controller.abort();
  }, [trackId, saved]);

  const total = s.score.hits + s.score.wrongs + s.score.misses;

  return (
    <div className="flex flex-wrap gap-x-8 gap-y-3 text-xs text-zinc-400">
      <div className="space-y-2">
        <label className="flex items-center gap-2">
          Mode
          <select
            value={s.practiceMode}
            onChange={(e) => s.set({ practiceMode: e.target.value as PracticeMode })}
            className="rounded bg-zinc-800 px-2 py-1 text-zinc-100"
          >
            {Object.entries(MODE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2">
          Je joue
          <select
            value={s.practiceHands}
            onChange={(e) => s.set({ practiceHands: e.target.value as PracticeHands })}
            className="rounded bg-zinc-800 px-2 py-1 text-zinc-100"
          >
            {Object.entries(HANDS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="space-y-2">
        {midi.connected ? (
          <label className="flex items-center gap-2">
            Clavier MIDI
            <select
              value={s.midiInputId ?? ""}
              onChange={(e) => s.set({ midiInputId: e.target.value || null })}
              className="rounded bg-zinc-800 px-2 py-1 text-zinc-100"
            >
              {midi.devices.length === 0 && <option value="">Aucun clavier détecté</option>}
              {midi.devices.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <button
            onClick={() => void midi.connect()}
            className="rounded bg-zinc-800 px-2 py-1 text-zinc-100 hover:bg-zinc-700"
          >
            Connecter un clavier MIDI
          </button>
        )}
        {midi.error && <p className="text-red-400">{midi.error}</p>}
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={s.inputSound}
            onChange={(e) => s.set({ inputSound: e.target.checked })}
          />
          Son de mes notes (décocher si le clavier a ses propres haut-parleurs)
        </label>
        <p>Sans clavier : clique sur les touches à l&apos;écran.</p>
      </div>

      {s.practiceMode !== "off" && (
        <div className="space-y-2">
          <p className="text-sm text-zinc-100">
            <span className="text-yellow-300">{s.score.hits} justes</span> ·{" "}
            <span className="text-red-400">{s.score.wrongs} fausses</span> ·{" "}
            <span className="text-zinc-300">{s.score.misses} manquées</span>
            {total > 0 && <> · {percent(accuracy(s.score))}</>}
          </p>
          <button
            onClick={onFinish}
            className="rounded bg-zinc-100 px-3 py-1 font-medium text-zinc-900"
          >
            Terminer la séance
          </button>
        </div>
      )}

      {history && history.sessions.length > 0 && (
        <div className="space-y-1">
          <p className="text-zinc-300">
            Progression : meilleur score {percent(history.best_accuracy ?? 0)},{" "}
            {history.sessions.length} séance(s), {Math.round(history.total_duration_s / 60)} min au
            total
          </p>
          <ul>
            {history.sessions.slice(0, 5).map((session) => (
              <li key={session.id}>
                {formatDate(session.created_at)} · {LEVEL_LABELS[session.level]} ·{" "}
                {MODE_SHORT[session.mode]} · {Math.round(session.speed * 100)} % ·{" "}
                <span className="text-zinc-100">{percent(session.accuracy)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function PracticeSummaryDialog() {
  const summary = usePlayerStore((s) => s.summary);
  const set = usePlayerStore((s) => s.set);
  if (!summary) return null;
  const minutes = Math.floor(summary.durationS / 60);
  const seconds = Math.round(summary.durationS % 60);
  return (
    <div className="absolute inset-0 flex items-center justify-center bg-black/60">
      <div className="w-80 space-y-3 rounded-xl bg-zinc-900 p-6 text-center shadow-xl">
        <p className="text-sm text-zinc-400">Bilan de la séance</p>
        <p className="text-5xl font-bold text-yellow-300">{percent(summary.accuracy)}</p>
        <p className="text-sm">
          {summary.hits} justes · {summary.wrongs} fausses · {summary.misses} manquées
        </p>
        <p className="text-xs text-zinc-400">
          Durée {minutes} min {String(seconds).padStart(2, "0")} s ·{" "}
          {summary.hits + summary.wrongs + summary.misses === 0
            ? "rien à enregistrer"
            : summary.saved
              ? "enregistrée dans l'historique"
              : "enregistrement…"}
        </p>
        <button
          onClick={() => set({ summary: null })}
          className="rounded-lg bg-zinc-100 px-4 py-1.5 text-sm font-medium text-zinc-900"
        >
          Continuer
        </button>
      </div>
    </div>
  );
}
