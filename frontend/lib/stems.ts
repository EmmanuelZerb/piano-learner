export const STEM_ORDER = ["piano", "other", "bass", "guitar", "vocals", "drums"] as const;

export const STEM_LABELS: Record<string, string> = {
  piano: "Piano",
  other: "Autres (synthés, cordes…)",
  bass: "Basse",
  guitar: "Guitare",
  vocals: "Voix (mélodie)",
  drums: "Batterie",
};

/** La batterie n'a pas de hauteur : jamais transcrite en notes. */
export function isTranscribable(stem: string): boolean {
  return stem !== "drums";
}

/** Coche/décoche une piste en gardant toujours au moins une piste sélectionnée. */
export function toggleStem(selection: string[], stem: string): string[] {
  if (!isTranscribable(stem)) return selection;
  if (!selection.includes(stem)) return [...selection, stem];
  return selection.length > 1 ? selection.filter((s) => s !== stem) : selection;
}
