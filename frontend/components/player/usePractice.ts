"use client";

import { useCallback, useEffect, useRef, type RefObject } from "react";

import { recordPractice } from "@/lib/api";
import type { PlayerEngine } from "@/lib/player/engine";
import type { ArrangementData, PlayerNote } from "@/lib/player/notes";
import {
  accuracy,
  chordSatisfied,
  PracticeJudge,
  practiceTargets,
  TOLERANCE_S,
  waitSteps,
  type NoteJudgement,
  type WaitStep,
} from "@/lib/player/practice";
import { usePlayerStore } from "@/lib/player/store";

export type KeyMark = "hit" | "wrong" | "held";

/** Ce que le rendu doit afficher pour l'entraînement à l'image courante. */
export type PracticeFrame = {
  judgement: (note: PlayerNote) => NoteJudgement;
  keys: Map<number, KeyMark>; // touches tenues par l'utilisateur
  waitPitches: number[] | null; // accord attendu en mode attente
};

const REWIND_THRESHOLD_S = 0.25;

/**
 * Logique d'entraînement branchée sur le moteur : arbitre des notes, arrêts du mode attente,
 * son des notes jouées, chronométrage et enregistrement de la séance.
 * `dataVersion` change à chaque chargement de niveau.
 */
export function usePractice(
  trackId: string,
  engineRef: RefObject<PlayerEngine | null>,
  dataRef: RefObject<ArrangementData | null>,
  dataVersion: number,
) {
  const mode = usePlayerStore((s) => s.practiceMode);
  const hands = usePlayerStore((s) => s.practiceHands);
  const judgeRef = useRef<PracticeJudge | null>(null);
  const stepsRef = useRef<WaitStep[]>([]);
  const keysRef = useRef(new Map<number, KeyMark>());
  const pressedSinceWait = useRef(new Set<number>());
  const lastTimeRef = useRef(0);
  const sessionRef = useRef({ seconds: 0, lastFrame: 0 });
  const lastScoreRef = useRef("");

  const tolerance = () => TOLERANCE_S * usePlayerStore.getState().speed;
  const heldPitches = () => new Set(keysRef.current.keys());

  const resetSession = useCallback(() => {
    const data = dataRef.current;
    const { practiceMode, practiceHands, set } = usePlayerStore.getState();
    judgeRef.current =
      data && practiceMode !== "off"
        ? new PracticeJudge(practiceTargets(data.notes, practiceHands))
        : null;
    sessionRef.current = { seconds: 0, lastFrame: 0 };
    lastScoreRef.current = "";
    set({ score: { hits: 0, wrongs: 0, misses: 0 } });
  }, [dataRef]);

  // Nouvelle séance quand le mode, les mains ou le niveau changent.
  useEffect(() => {
    const engine = engineRef.current;
    const data = dataRef.current;
    resetSession();
    if (!engine || !data) return;
    if (mode !== "wait") {
      engine.setWaitSteps(null, () => false);
      return;
    }
    stepsRef.current = waitSteps(practiceTargets(data.notes, hands));
    engine.setWaitSteps(
      stepsRef.current.map((s) => s.time),
      (index) => {
        if (chordSatisfied(stepsRef.current[index], heldPitches(), new Set())) return false;
        pressedSinceWait.current = new Set();
        return true;
      },
    );
  }, [mode, hands, dataVersion, engineRef, dataRef, resetSession]);

  // Pendant l'entraînement, la ou les mains travaillées ne sont pas jouées par le lecteur.
  useEffect(() => {
    const apply = () => {
      const s = usePlayerStore.getState();
      const practiced = s.practiceMode === "off" ? [] : s.practiceHands.split("");
      for (const hand of ["L", "R"] as const) {
        engineRef.current?.setMuted(hand, s.muted[hand] || practiced.includes(hand));
      }
    };
    apply();
    return usePlayerStore.subscribe(apply);
  }, [engineRef, dataVersion]);

  const noteOn = useCallback(
    (pitch: number, velocity: number) => {
      const engine = engineRef.current;
      if (!engine) return;
      if (usePlayerStore.getState().inputSound) void engine.previewNote(pitch, velocity);
      const judge = judgeRef.current;
      if (!judge) {
        keysRef.current.set(pitch, "held");
        return;
      }
      keysRef.current.set(pitch, judge.noteOn(pitch, engine.songTime(), tolerance()));
      const waiting = engine.waitingIndex();
      if (waiting !== null) {
        pressedSinceWait.current.add(pitch);
        if (chordSatisfied(stepsRef.current[waiting], heldPitches(), pressedSinceWait.current)) {
          engine.resume();
        }
      }
    },
    [engineRef],
  );

  const noteOff = useCallback(
    (pitch: number) => {
      keysRef.current.delete(pitch);
      if (usePlayerStore.getState().inputSound) engineRef.current?.releasePreview(pitch);
    },
    [engineRef],
  );

  /** Appelé à chaque image : notes manquées, retours en arrière, chrono, score affiché. */
  const frame = useCallback(
    (time: number, now: number): PracticeFrame | null => {
      const engine = engineRef.current;
      const judge = judgeRef.current;
      if (!engine || !judge) return null;
      const active = engine.playing || engine.waiting;
      const s = usePlayerStore.getState();

      if (time < lastTimeRef.current - REWIND_THRESHOLD_S) judge.rewind(time, tolerance());
      if (s.practiceMode === "free" && engine.playing) judge.advance(time, tolerance());
      lastTimeRef.current = time;

      const session = sessionRef.current;
      if (active && session.lastFrame) session.seconds += (now - session.lastFrame) / 1000;
      session.lastFrame = active ? now : 0;

      const score = judge.score();
      const key = `${score.hits}/${score.wrongs}/${score.misses}`;
      if (key !== lastScoreRef.current) {
        lastScoreRef.current = key;
        s.set({ score });
      }
      const waiting = engine.waitingIndex();
      return {
        judgement: (note) => judge.judgement(note),
        keys: keysRef.current,
        waitPitches: waiting === null ? null : stepsRef.current[waiting].pitches,
      };
    },
    [engineRef],
  );

  /** Fin de séance : bilan affiché, enregistré dans l'historique, puis remise à zéro. */
  const finishSession = useCallback(async () => {
    const judge = judgeRef.current;
    const s = usePlayerStore.getState();
    if (!judge || s.practiceMode === "off") return;
    const score = judge.score();
    const durationS = Math.round(sessionRef.current.seconds * 10) / 10;
    const summary = { ...score, accuracy: accuracy(score), durationS, saved: false };
    s.set({ summary });
    resetSession();
    if (score.hits + score.wrongs + score.misses === 0) return;
    await recordPractice(trackId, {
      level: s.level,
      mode: s.practiceMode,
      hands: s.practiceHands,
      speed: s.speed,
      ...score,
      duration_s: durationS,
    });
    usePlayerStore.getState().set({ summary: { ...summary, saved: true } });
  }, [trackId, resetSession]);

  return { noteOn, noteOff, frame, finishSession, active: mode !== "off" };
}
