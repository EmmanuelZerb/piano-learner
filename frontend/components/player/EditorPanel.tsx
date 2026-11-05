"use client";

import { useState } from "react";

import { addEdits, removeEdits, type NoteEdit } from "@/lib/api";
import { pitchName } from "@/lib/music";
import { usePlayerStore } from "@/lib/player/store";

const HAND_NAMES = { L: "main gauche", R: "main droite" } as const;

/** Corrections du niveau affiché : note sélectionnée (hauteur, main, suppression) et
 * partage des mains sur le passage A-B. Chaque correction est enregistrée côté serveur et
 * rejouée après un recalcul du post-traitement. */
export function EditorPanel({ trackId }: { trackId: string }) {
  const s = usePlayerStore();
  const [split, setSplit] = useState(60);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selected = s.selected;
  const loop =
    s.loopA !== null && s.loopB !== null
      ? { start: Math.min(s.loopA, s.loopB), end: Math.max(s.loopA, s.loopB) }
      : null;

  async function run(action: () => Promise<unknown>, after?: () => void) {
    setBusy(true);
    setError(null);
    try {
      await action();
      after?.();
      usePlayerStore.getState().set({ levelReload: usePlayerStore.getState().levelReload + 1 });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const edit = (e: NoteEdit, next: typeof selected) =>
    run(
      () => addEdits(trackId, s.level, [e]),
      () => s.set({ selected: next }),
    );

  const transpose = (delta: number) => {
    if (!selected) return;
    const newPitch = Math.min(108, Math.max(21, selected.pitch + delta));
    void edit(
      { op: "pitch", pitch: selected.pitch, start: selected.start, new_pitch: newPitch },
      { ...selected, pitch: newPitch },
    );
  };

  const button =
    "rounded bg-zinc-800 px-2 py-1 text-zinc-100 hover:bg-zinc-700 disabled:opacity-40";

  return (
    <div className="flex flex-wrap gap-x-8 gap-y-3 text-xs text-zinc-400">
      <div className="space-y-2">
        {selected ? (
          <>
            <p className="text-sm text-zinc-100">
              {pitchName(selected.pitch)} · {HAND_NAMES[selected.hand]} · à{" "}
              {selected.start.toFixed(2)} s
            </p>
            <div className="flex flex-wrap gap-1">
              <button disabled={busy} className={button} onClick={() => transpose(-12)}>
                − octave
              </button>
              <button disabled={busy} className={button} onClick={() => transpose(-1)}>
                − ½ ton
              </button>
              <button disabled={busy} className={button} onClick={() => transpose(1)}>
                + ½ ton
              </button>
              <button disabled={busy} className={button} onClick={() => transpose(12)}>
                + octave
              </button>
              <button
                disabled={busy}
                className={button}
                onClick={() => {
                  const hand = selected.hand === "L" ? "R" : "L";
                  void edit(
                    { op: "hand", pitch: selected.pitch, start: selected.start, hand },
                    { ...selected, hand },
                  );
                }}
              >
                Passer en {HAND_NAMES[selected.hand === "L" ? "R" : "L"]}
              </button>
              <button
                disabled={busy}
                className={`${button} text-red-300`}
                onClick={() =>
                  void edit({ op: "delete", pitch: selected.pitch, start: selected.start }, null)
                }
              >
                Supprimer
              </button>
            </div>
          </>
        ) : (
          <p>Clique sur une note qui tombe pour la sélectionner (lecture en pause).</p>
        )}
      </div>

      <div className="space-y-2">
        <p className="text-zinc-300">Partage des mains sur le passage A-B</p>
        {loop ? (
          <div className="flex items-center gap-2">
            <input
              type="range"
              min={36}
              max={84}
              value={split}
              onChange={(e) => setSplit(Number(e.target.value))}
            />
            <span className="w-14 font-mono text-zinc-100">{pitchName(split)}</span>
            <button
              disabled={busy}
              className={button}
              onClick={() =>
                void run(() => addEdits(trackId, s.level, [{ op: "split", ...loop, split }]))
              }
            >
              Appliquer
            </button>
          </div>
        ) : (
          <p>Pose d&apos;abord une boucle A-B sur le passage.</p>
        )}
      </div>

      <div className="space-y-2">
        <div className="flex gap-1">
          <button
            disabled={busy}
            className={button}
            onClick={() => void run(() => removeEdits(trackId, s.level, true))}
          >
            Annuler la dernière correction
          </button>
          <button
            disabled={busy}
            className={button}
            onClick={() => {
              if (window.confirm("Effacer toutes les corrections de ce niveau ?"))
                void run(
                  () => removeEdits(trackId, s.level, false),
                  () => s.set({ selected: null }),
                );
            }}
          >
            Tout effacer
          </button>
        </div>
        {error && <p className="text-red-400">{error}</p>}
      </div>
    </div>
  );
}

/** Raccourci Suppr : supprime la note sélectionnée. */
export async function deleteSelected(trackId: string): Promise<void> {
  const s = usePlayerStore.getState();
  if (!s.editing || !s.selected) return;
  await addEdits(trackId, s.level, [
    { op: "delete", pitch: s.selected.pitch, start: s.selected.start },
  ]);
  s.set({ selected: null, levelReload: s.levelReload + 1 });
}
