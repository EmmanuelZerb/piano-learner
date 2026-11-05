"use client";

import type { RefObject } from "react";

import type { Level } from "@/lib/api";
import { LEVEL_LABELS } from "@/lib/music";
import { SPEED_MAX, SPEED_MIN } from "@/lib/player/notes";
import { SHORTCUT_HELP } from "@/lib/player/shortcuts";
import { usePlayerStore, ZOOM_MAX, ZOOM_MIN } from "@/lib/player/store";
import { STEM_LABELS } from "@/lib/stems";

export type PlayerActions = {
  togglePlay: () => void;
  seek: (seconds: number) => void;
  seekBy: (delta: number) => void;
  setLoopPoint: (point: "a" | "b") => void;
  clearLoop: () => void;
};

type Props = {
  actions: PlayerActions;
  duration: number;
  loop: { a: number; b: number } | null;
  progressRef: RefObject<HTMLDivElement | null>;
  timeRef: RefObject<HTMLSpanElement | null>;
  accompanimentChoices: string[];
  disabled: boolean;
};

const ACCOMPANIMENT_LABELS: Record<string, string> = {
  ...STEM_LABELS,
  original: "Mixage original",
};

function Toggle(props: {
  on: boolean;
  onClick: () => void;
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <button
      onClick={props.onClick}
      title={props.title}
      className={`rounded px-2 py-1 text-xs font-medium ${
        props.on ? "bg-zinc-100 text-zinc-900" : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
      }`}
    >
      {props.children}
    </button>
  );
}

export function PlayerControls({
  actions,
  duration,
  loop,
  disabled,
  progressRef,
  timeRef,
  accompanimentChoices,
}: Props) {
  const s = usePlayerStore();
  const playing = s.status === "playing";

  return (
    <div className="space-y-2 border-t border-zinc-800 px-4 py-3 text-sm">
      {/* Barre de progression : cliquer pour se déplacer ; la boucle A-B est surlignée. */}
      <div
        title="Cliquer pour se déplacer (← → au clavier)"
        onClick={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          actions.seek(((e.clientX - rect.left) / rect.width) * duration);
        }}
        className="relative h-3 cursor-pointer rounded-full bg-zinc-800"
      >
        {loop && duration > 0 && (
          <div
            className="absolute inset-y-0 rounded-full bg-yellow-400/30"
            style={{
              left: `${(loop.a / duration) * 100}%`,
              width: `${((loop.b - loop.a) / duration) * 100}%`,
            }}
          />
        )}
        <div
          ref={progressRef}
          className="absolute inset-y-0 left-0 rounded-full bg-emerald-500/80"
        />
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <button
          onClick={actions.togglePlay}
          disabled={disabled}
          className="w-24 rounded-lg bg-zinc-100 px-3 py-1.5 font-semibold text-zinc-900 disabled:opacity-40"
        >
          {playing ? "Pause" : "Lecture"}
        </button>
        <span ref={timeRef} className="w-24 font-mono text-xs text-zinc-400" />

        <label className="flex items-center gap-2">
          <span className="text-zinc-400">Vitesse</span>
          <input
            type="range"
            min={SPEED_MIN}
            max={SPEED_MAX}
            step={0.05}
            value={s.speed}
            onChange={(e) => s.set({ speed: Number(e.target.value) })}
          />
          <span className="w-10 font-mono text-xs">{Math.round(s.speed * 100)} %</span>
        </label>

        <div className="flex items-center gap-1">
          <Toggle
            on={s.loopA !== null}
            onClick={() => actions.setLoopPoint("a")}
            title="Début de boucle (A)"
          >
            A
          </Toggle>
          <Toggle
            on={s.loopB !== null}
            onClick={() => actions.setLoopPoint("b")}
            title="Fin de boucle (B)"
          >
            B
          </Toggle>
          {(s.loopA !== null || s.loopB !== null) && (
            <button onClick={actions.clearLoop} className="px-1 text-xs text-zinc-400 underline">
              effacer
            </button>
          )}
        </div>

        <div className="flex items-center gap-1">
          <Toggle
            on={!s.muted.L}
            onClick={() => s.set({ muted: { ...s.muted, L: !s.muted.L } })}
            title="Main gauche (G)"
          >
            <span className="text-blue-400">●</span> Gauche
          </Toggle>
          <Toggle
            on={!s.muted.R}
            onClick={() => s.set({ muted: { ...s.muted, R: !s.muted.R } })}
            title="Main droite (D)"
          >
            <span className="text-green-400">●</span> Droite
          </Toggle>
        </div>

        <select
          value={s.level}
          onChange={(e) => s.set({ level: e.target.value as Level })}
          className="rounded bg-zinc-800 px-2 py-1 text-xs"
          aria-label="Niveau"
        >
          {(Object.keys(LEVEL_LABELS) as Level[]).map((level) => (
            <option key={level} value={level}>
              {LEVEL_LABELS[level]}
            </option>
          ))}
        </select>

        <div className="flex items-center gap-1">
          <Toggle
            on={s.countIn}
            onClick={() => s.set({ countIn: !s.countIn })}
            title="Décompte de 4 temps (C)"
          >
            Décompte
          </Toggle>
          <Toggle
            on={s.metronome}
            onClick={() => s.set({ metronome: !s.metronome })}
            title="Métronome (M)"
          >
            Métronome
          </Toggle>
          <Toggle
            on={s.showNames}
            onClick={() => s.set({ showNames: !s.showNames })}
            title="Nom des notes (N)"
          >
            Notes
          </Toggle>
        </div>

        <label className="flex items-center gap-2">
          <span className="text-zinc-400">Zoom</span>
          <input
            type="range"
            min={ZOOM_MIN}
            max={ZOOM_MAX}
            step={10}
            value={s.pixelsPerSecond}
            onChange={(e) => s.set({ pixelsPerSecond: Number(e.target.value) })}
          />
        </label>
      </div>

      <details className="text-xs text-zinc-400">
        <summary className="cursor-pointer">Accompagnement, volumes et raccourcis</summary>
        <div className="mt-2 flex flex-wrap gap-x-8 gap-y-3">
          <div className="space-y-1">
            <p className="text-zinc-300">Jouer aussi les pistes d&apos;origine :</p>
            <div className="flex flex-wrap gap-1">
              {accompanimentChoices.map((name) => (
                <Toggle
                  key={name}
                  on={s.accompaniment.includes(name)}
                  onClick={() =>
                    s.set({
                      accompaniment: s.accompaniment.includes(name)
                        ? s.accompaniment.filter((n) => n !== name)
                        : [...s.accompaniment, name],
                    })
                  }
                >
                  {ACCOMPANIMENT_LABELS[name] ?? name}
                </Toggle>
              ))}
            </div>
            <p>Hors vitesse 100 %, l&apos;accompagnement est étiré (léger grain).</p>
          </div>
          <div className="space-y-1">
            <label className="flex items-center gap-2">
              Piano
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={s.pianoVolume}
                onChange={(e) => s.set({ pianoVolume: Number(e.target.value) })}
              />
            </label>
            <label className="flex items-center gap-2">
              Accompagnement
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={s.accompanimentVolume}
                onChange={(e) => s.set({ accompanimentVolume: Number(e.target.value) })}
              />
            </label>
          </div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3">
            {SHORTCUT_HELP.map(([key, label]) => (
              <div key={key} className="contents">
                <dt className="font-mono text-zinc-300">{key}</dt>
                <dd>{label}</dd>
              </div>
            ))}
          </dl>
        </div>
        <p className="mt-2">Piano : Salamander Grand Piano, Alexander Holm (CC-BY 3.0).</p>
      </details>
    </div>
  );
}
