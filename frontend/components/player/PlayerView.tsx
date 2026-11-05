"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { PlayerControls, type PlayerActions } from "@/components/player/PlayerControls";
import {
  getArrangement,
  getStems,
  getTrack,
  mediaUrl,
  type Arrangement,
  type Level,
  type Track,
} from "@/lib/api";
import type { PlayerEngine } from "@/lib/player/engine";
import { keyboardLayout } from "@/lib/player/keyboard";
import {
  clampSpeed,
  normalizeLoop,
  parseArrangement,
  type ArrangementData,
} from "@/lib/player/notes";
import { drawFrame } from "@/lib/player/renderer";
import { isTypingTarget, shortcutFor, type ShortcutAction } from "@/lib/player/shortcuts";
import { usePlayerStore, ZOOM_MAX, ZOOM_MIN } from "@/lib/player/store";

const LEVELS: Level[] = ["beginner", "intermediate", "advanced"];
const COUNT_IN_BEATS = 4;

/** Statistiques exposées pour mesurer fluidité et dérive (console : window.__playerStats). */
type PlayerStats = {
  fps: number;
  worstFrameMs: number;
  driftMs: number;
  // Cumuls sur toute la session de lecture :
  minFps: number;
  worstFrameDuringPlayMs: number;
  maxAbsDriftMs: number;
  playedSeconds: number;
};
declare global {
  interface Window {
    __playerStats?: PlayerStats;
  }
}

export function PlayerView() {
  const { id } = useParams<{ id: string }>();
  const store = usePlayerStore();
  const engineRef = useRef<PlayerEngine | null>(null);
  const dataRef = useRef<ArrangementData | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const progressRef = useRef<HTMLDivElement>(null);
  const timeRef = useRef<HTMLSpanElement>(null);
  const [track, setTrack] = useState<Track | null>(null);
  const [arrangement, setArrangement] = useState<Arrangement | null>(null);
  const [sources, setSources] = useState<Record<string, string>>({});
  const [duration, setDuration] = useState(0);
  const [samplesReady, setSamplesReady] = useState(false);
  // Repère pour mesurer la dérive : (temps audio, position) au dernier changement.
  const anchorRef = useRef<{ audio: number; song: number; speed: number } | null>(null);

  const { set } = store;

  // --- Moteur audio (chargé côté client uniquement : Web Audio) ----------------------------
  useEffect(() => {
    let disposed = false;
    let engine: PlayerEngine | null = null;
    void import("@/lib/player/engine").then(({ PlayerEngine }) => {
      if (disposed) return;
      engine = new PlayerEngine("/samples/salamander/");
      engineRef.current = engine;
      engine.ready
        .then(() => !disposed && setSamplesReady(true))
        .catch(() =>
          set({
            status: "error",
            error: "Échantillons de piano introuvables (npm run fetch:samples).",
          }),
        );
    });
    set({ status: "loading", error: null, loopA: null, loopB: null, speed: 1 });
    return () => {
      disposed = true;
      engine?.dispose();
      engineRef.current = null;
    };
  }, [set]);

  // --- Morceau, niveaux disponibles et pistes d'accompagnement ------------------------------
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      getTrack(id, controller.signal),
      getArrangement(id, controller.signal),
      getStems(id, controller.signal),
    ])
      .then(([t, a, s]) => {
        setTrack(t);
        setArrangement(a);
        setSources({
          original: mediaUrl(t.audio_url),
          ...Object.fromEntries(s.stems.map((stem) => [stem.name, mediaUrl(stem.url)])),
        });
        if (!a.available) set({ status: "error", error: "Ce morceau n'a pas encore de niveaux." });
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted)
          set({ status: "error", error: err instanceof Error ? err.message : String(err) });
      });
    return () => controller.abort();
  }, [id, set]);

  // --- Chargement du niveau choisi (on garde la position) ---------------------------------
  useEffect(() => {
    const level = arrangement?.levels.find((l) => l.level === store.level);
    const engine = engineRef.current;
    if (!level || !engine || !samplesReady) return;
    const controller = new AbortController();
    fetch(mediaUrl(level.notes_url), { signal: controller.signal })
      .then((res) => res.json())
      .then((raw) => {
        const data = parseArrangement(raw);
        const position = dataRef.current ? engine.songTime() : 0;
        dataRef.current = data;
        engine.setArrangement(data);
        engine.seek(Math.min(position, data.duration));
        setDuration(data.duration);
        set({ status: engine.playing ? "playing" : "ready" });
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted)
          set({ status: "error", error: err instanceof Error ? err.message : String(err) });
      });
    return () => controller.abort();
  }, [arrangement, store.level, samplesReady, set]);

  // --- Réglages du store → moteur -------------------------------------------------------------
  const loop = useMemo(
    () => normalizeLoop(store.loopA, store.loopB, duration),
    [store.loopA, store.loopB, duration],
  );
  useEffect(() => engineRef.current?.setLoop(loop), [loop, samplesReady]);
  useEffect(() => {
    engineRef.current?.setMuted("L", store.muted.L);
    engineRef.current?.setMuted("R", store.muted.R);
  }, [store.muted, samplesReady]);
  useEffect(
    () => engineRef.current?.setMetronome(store.metronome),
    [store.metronome, samplesReady],
  );
  useEffect(
    () => engineRef.current?.setVolumes(store.pianoVolume, store.accompanimentVolume),
    [store.pianoVolume, store.accompanimentVolume, samplesReady],
  );
  useEffect(() => {
    const engine = engineRef.current;
    if (!engine || !samplesReady) return;
    engine.setSpeed(store.speed);
    anchorRef.current = null;
  }, [store.speed, samplesReady]);
  useEffect(() => {
    const engine = engineRef.current;
    if (!engine || !samplesReady) return;
    engine
      .setAccompaniment(sources, store.accompaniment)
      .catch(() => set({ error: "Impossible de charger l'accompagnement." }));
  }, [sources, store.accompaniment, samplesReady, set]);

  // --- Actions ---------------------------------------------------------------------------
  const actions: PlayerActions = useMemo(() => {
    const engine = () => engineRef.current;
    const pause = () => {
      engine()?.pause();
      set({ status: "ready" });
    };
    return {
      togglePlay: () => {
        const e = engine();
        if (!e || !dataRef.current) return;
        if (e.playing) return pause();
        const { countIn } = usePlayerStore.getState();
        if (e.songTime() >= dataRef.current.duration - 0.05) e.seek(loop?.a ?? 0);
        void e.play(countIn ? COUNT_IN_BEATS : 0).then(() => set({ status: "playing" }));
        anchorRef.current = null;
      },
      seek: (seconds: number) => {
        engine()?.seek(seconds);
        anchorRef.current = null;
      },
      seekBy: (delta: number) => {
        const e = engine();
        if (e) e.seek(e.songTime() + delta);
        anchorRef.current = null;
      },
      setLoopPoint: (point: "a" | "b") => {
        const t = engine()?.songTime() ?? 0;
        set(point === "a" ? { loopA: t } : { loopB: t });
      },
      clearLoop: () => set({ loopA: null, loopB: null }),
    };
  }, [loop, set]);

  // --- Raccourcis clavier ---------------------------------------------------------------
  const runShortcut = useCallback(
    (action: ShortcutAction) => {
      const s = usePlayerStore.getState();
      switch (action.type) {
        case "toggle-play":
          return actions.togglePlay();
        case "seek-by":
          return actions.seekBy(action.seconds);
        case "speed-by":
          return set({ speed: clampSpeed(s.speed + action.delta) });
        case "go-start":
          return actions.seek(loop?.a ?? 0);
        case "set-loop-a":
          return actions.setLoopPoint("a");
        case "set-loop-b":
          return actions.setLoopPoint("b");
        case "clear-loop":
          return actions.clearLoop();
        case "toggle-metronome":
          return set({ metronome: !s.metronome });
        case "toggle-names":
          return set({ showNames: !s.showNames });
        case "toggle-stats":
          return set({ showStats: !s.showStats });
        case "toggle-count-in":
          return set({ countIn: !s.countIn });
        case "toggle-hand":
          return set({ muted: { ...s.muted, [action.hand]: !s.muted[action.hand] } });
        case "level":
          return set({ level: LEVELS[action.index] });
        case "zoom-by":
          return set({
            pixelsPerSecond: Math.min(
              ZOOM_MAX,
              Math.max(ZOOM_MIN, s.pixelsPerSecond * action.factor),
            ),
          });
      }
    },
    [actions, loop, set],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target)) return;
      const action = shortcutFor(event);
      if (!action) return;
      event.preventDefault();
      runShortcut(action);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [runShortcut]);

  // --- Boucle d'affichage (requestAnimationFrame, lit l'horloge audio) ------------------------
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) return;
    let size = { width: 0, height: 0 };
    let layout = keyboardLayout(1);
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      size = { width: rect.width, height: rect.height };
      canvas.width = Math.round(rect.width * dpr);
      canvas.height = Math.round(rect.height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      layout = keyboardLayout(rect.width);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();

    let frame = 0;
    const stats: PlayerStats = {
      fps: 0,
      worstFrameMs: 0,
      driftMs: 0,
      minFps: Infinity,
      worstFrameDuringPlayMs: 0,
      maxAbsDriftMs: 0,
      playedSeconds: 0,
    };
    window.__playerStats = stats;
    let frames = 0;
    let worst = 0;
    let last = performance.now();
    let windowStart = last;
    const loopFn = (now: number) => {
      frame = requestAnimationFrame(loopFn);
      const engine = engineRef.current;
      const data = dataRef.current;
      worst = Math.max(worst, now - last);
      last = now;
      frames++;
      if (now - windowStart >= 1000) {
        stats.fps = Math.round((frames * 1000) / (now - windowStart));
        stats.worstFrameMs = Math.round(worst);
        if (engine?.playing) {
          stats.minFps = Math.min(stats.minFps, stats.fps);
          stats.worstFrameDuringPlayMs = Math.max(stats.worstFrameDuringPlayMs, stats.worstFrameMs);
          stats.playedSeconds += (now - windowStart) / 1000;
        }
        frames = 0;
        worst = 0;
        windowStart = now;
      }
      if (!engine || !data || size.width === 0) return;

      const s = usePlayerStore.getState();
      const time = engine.songTime();
      if (engine.playing && !engine.countInRemaining()) {
        trackDrift(engine, time);
        const end = s.loopA !== null && s.loopB !== null ? Infinity : data.duration;
        if (time >= end) {
          engine.pause();
          s.set({ status: "ready" });
        }
      }
      const countLeft = engine.countInRemaining();
      drawFrame({
        ctx,
        width: size.width,
        height: size.height,
        layout,
        data,
        time,
        pixelsPerSecond: s.pixelsPerSecond,
        muted: s.muted,
        showNames: s.showNames,
        stats: s.showStats ? stats : null,
        loop: normalizeLoop(s.loopA, s.loopB, data.duration),
        countIn: countLeft === null ? null : Math.ceil(countLeft / engine.beatPeriod()),
      });
      if (progressRef.current) progressRef.current.style.width = `${(time / data.duration) * 100}%`;
      if (timeRef.current) timeRef.current.textContent = `${clock(time)} / ${clock(data.duration)}`;
    };

    /** Écart entre la position lue et celle attendue d'après l'horloge audio brute depuis le
     * dernier repère (lecture continue à vitesse constante). Doit rester ≈ 0. */
    const trackDrift = (engine: PlayerEngine, time: number) => {
      const audioNow = engine.audioTime();
      const anchor = anchorRef.current;
      if (!anchor || anchor.speed !== usePlayerStore.getState().speed || time < anchor.song) {
        anchorRef.current = { audio: audioNow, song: time, speed: usePlayerStore.getState().speed };
        return;
      }
      const expected = anchor.song + (audioNow - anchor.audio) * anchor.speed;
      stats.driftMs = Math.round((time - expected) * 1000 * 10) / 10;
      stats.maxAbsDriftMs = Math.max(stats.maxAbsDriftMs, Math.abs(stats.driftMs));
    };

    frame = requestAnimationFrame(loopFn);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, []);

  return (
    <div className="flex h-[calc(100vh-3.5rem)] min-h-[480px] flex-col bg-[#0b0b0f] text-zinc-100">
      <header className="flex items-center gap-4 px-4 py-2 text-sm">
        <Link href={`/tracks/${id}`} className="text-zinc-400 hover:underline">
          ←
        </Link>
        <span className="truncate font-medium">{track?.title ?? "…"}</span>
        {arrangement?.key && <span className="text-zinc-500">{arrangement.tempo} BPM</span>}
        {store.error && <span className="text-red-400">{store.error}</span>}
        {!samplesReady && store.status !== "error" && (
          <span className="text-zinc-500">Chargement du piano…</span>
        )}
      </header>
      <canvas ref={canvasRef} className="min-h-0 w-full flex-1" />
      <PlayerControls
        actions={actions}
        duration={duration}
        loop={loop}
        progressRef={progressRef}
        timeRef={timeRef}
        accompanimentChoices={Object.keys(sources)}
        disabled={!samplesReady || duration === 0}
      />
    </div>
  );
}

function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
