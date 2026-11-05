const NOTE_NAMES = ["Do", "Do♯", "Ré", "Mi♭", "Mi", "Fa", "Fa♯", "Sol", "La♭", "La", "Si♭", "Si"];

/** 60 → « Do4 » (indice d'octave scientifique : le do central est Do4). */
export function pitchName(pitch: number): string {
  return `${NOTE_NAMES[pitch % 12]}${Math.floor(pitch / 12) - 1}`;
}

const KEY_NAMES: Record<string, string> = {
  C: "Do",
  "C#": "Do♯",
  Db: "Ré♭",
  D: "Ré",
  Eb: "Mi♭",
  E: "Mi",
  F: "Fa",
  "F#": "Fa♯",
  G: "Sol",
  "G#": "Sol♯",
  Ab: "La♭",
  A: "La",
  Bb: "Si♭",
  B: "Si",
};

/** « Eb » → « Mi♭ majeur », « F#m » → « Fa♯ mineur ». */
export function keyName(key: string): string {
  const minor = key.endsWith("m");
  const tonic = minor ? key.slice(0, -1) : key;
  return `${KEY_NAMES[tonic] ?? tonic} ${minor ? "mineur" : "majeur"}`;
}

export const LEVEL_LABELS = {
  beginner: "Débutant",
  intermediate: "Intermédiaire",
  advanced: "Avancé",
} as const;
