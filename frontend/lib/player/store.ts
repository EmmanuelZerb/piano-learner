import { create } from "zustand";

import type { Level } from "@/lib/api";
import type { Hand } from "@/lib/player/notes";
import type { PracticeHands, PracticeMode, PracticeScore } from "@/lib/player/practice";

export type PlayerStatus = "loading" | "ready" | "playing" | "error";

/** État de l'interface du lecteur. La position de lecture n'y figure pas : elle est lue
 * sur l'horloge audio à chaque image, sans passer par React. */
export type PlayerState = {
  status: PlayerStatus;
  error: string | null;
  level: Level;
  speed: number;
  loopA: number | null;
  loopB: number | null;
  muted: Record<Hand, boolean>;
  showNames: boolean;
  showStats: boolean;
  pixelsPerSecond: number;
  metronome: boolean;
  countIn: boolean;
  accompaniment: string[];
  pianoVolume: number;
  accompanimentVolume: number;
  // Entraînement
  practiceMode: PracticeMode;
  practiceHands: PracticeHands;
  midiInputId: string | null;
  inputSound: boolean; // jouer le son des notes de l'utilisateur (clavier sans haut-parleur, souris)
  score: PracticeScore;
  summary: PracticeSummary | null;
  // Éditeur
  editing: boolean;
  selected: SelectedNote | null;
  levelReload: number; // incrémenté après une correction pour recharger le niveau
  set: (patch: Partial<Omit<PlayerState, "set">>) => void;
};

export type SelectedNote = { pitch: number; start: number; end: number; hand: Hand };

export type PracticeSummary = PracticeScore & {
  accuracy: number;
  durationS: number;
  saved: boolean;
};

export const usePlayerStore = create<PlayerState>((set) => ({
  status: "loading",
  error: null,
  level: "intermediate",
  speed: 1,
  loopA: null,
  loopB: null,
  muted: { L: false, R: false },
  showNames: false,
  showStats: false,
  pixelsPerSecond: 160,
  metronome: false,
  countIn: true,
  accompaniment: [],
  pianoVolume: 0.9,
  accompanimentVolume: 0.6,
  practiceMode: "off",
  practiceHands: "R",
  midiInputId: null,
  inputSound: true,
  score: { hits: 0, wrongs: 0, misses: 0 },
  summary: null,
  editing: false,
  selected: null,
  levelReload: 0,
  set: (patch) => set(patch),
}));

export const ZOOM_MIN = 60;
export const ZOOM_MAX = 600;
