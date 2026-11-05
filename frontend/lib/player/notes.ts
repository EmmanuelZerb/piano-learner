/** Données d'un niveau (JSON produit par le post-traitement) et requêtes temporelles. */

export type Hand = "L" | "R";

export type PlayerNote = {
  pitch: number;
  start: number; // secondes dans l'audio d'origine
  end: number;
  velocity: number;
  hand: Hand;
};

export type ArrangementData = {
  level: string;
  tempo: number;
  beats: number[];
  key: string | null;
  chords: { start: number; end: number; name: string }[];
  pedals: { start: number; end: number }[];
  notes: PlayerNote[]; // triées par début
  duration: number;
  maxNoteDuration: number;
};

type RawArrangement = {
  level: string;
  tempo: number;
  beats: number[];
  key: string | null;
  chords: [number, number, string][];
  pedals: [number, number][];
  notes: [number, number, number, number, Hand][];
};

export function parseArrangement(raw: RawArrangement): ArrangementData {
  const notes = raw.notes
    .map(([pitch, start, end, velocity, hand]) => ({ pitch, start, end, velocity, hand }))
    .sort((a, b) => a.start - b.start || a.pitch - b.pitch);
  return {
    level: raw.level,
    tempo: raw.tempo,
    beats: raw.beats,
    key: raw.key,
    chords: raw.chords.map(([start, end, name]) => ({ start, end, name })),
    pedals: raw.pedals.map(([start, end]) => ({ start, end })),
    notes,
    duration: notes.reduce((max, n) => Math.max(max, n.end), 0),
    maxNoteDuration: notes.reduce((max, n) => Math.max(max, n.end - n.start), 0),
  };
}

/** Indice de la première note commençant à `t` ou après (recherche dichotomique). */
export function firstIndexFrom(notes: PlayerNote[], t: number): number {
  let lo = 0;
  let hi = notes.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (notes[mid].start < t) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** Notes qui recoupent [from, to] : coût en O(log n + notes affichées) par image. */
export function notesInWindow(data: ArrangementData, from: number, to: number): PlayerNote[] {
  const out: PlayerNote[] = [];
  const end = firstIndexFrom(data.notes, to);
  for (let i = firstIndexFrom(data.notes, from - data.maxNoteDuration); i < end; i++) {
    if (data.notes[i].end > from) out.push(data.notes[i]);
  }
  return out;
}

export function activeNotes(data: ArrangementData, t: number): PlayerNote[] {
  return notesInWindow(data, t, t + 1e-6).filter((n) => n.start <= t);
}

/** Fin sonore de chaque note : prolongée jusqu'au relâchement de la pédale de sustain si la
 * touche est relâchée pendant que la pédale est enfoncée. */
export function sustainedEnds(
  notes: PlayerNote[],
  pedals: { start: number; end: number }[],
): number[] {
  const sorted = [...pedals].sort((a, b) => a.start - b.start);
  return notes.map((n) => {
    const pedal = sorted.find((p) => p.start <= n.end && n.end < p.end);
    return pedal ? pedal.end : n.end;
  });
}

export const MIN_LOOP_S = 0.5;

/** Boucle A-B valide (A < B, durée minimale), ou null si impossible. */
export function normalizeLoop(
  a: number | null,
  b: number | null,
  duration: number,
): { a: number; b: number } | null {
  if (a === null || b === null) return null;
  const start = Math.max(0, Math.min(a, b));
  const end = Math.min(duration, Math.max(a, b));
  return end - start >= MIN_LOOP_S ? { a: start, b: end } : null;
}

export const SPEED_MIN = 0.25;
export const SPEED_MAX = 1.5;

export function clampSpeed(speed: number): number {
  return Math.round(Math.min(SPEED_MAX, Math.max(SPEED_MIN, speed)) * 100) / 100;
}
