import { create } from "zustand";

import type { Level } from "@/lib/api";
import type { Hand } from "@/lib/player/notes";

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
  set: (patch: Partial<Omit<PlayerState, "set">>) => void;
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
  set: (patch) => set(patch),
}));

export const ZOOM_MIN = 60;
export const ZOOM_MAX = 600;
