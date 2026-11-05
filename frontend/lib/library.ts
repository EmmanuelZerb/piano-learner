/** Filtre plein texte (titre ou artiste), insensible à la casse et aux accents. */
export function matchesQuery(
  item: { title: string; artist: string | null },
  query: string,
): boolean {
  const normalize = (s: string) =>
    s
      .normalize("NFD")
      .replace(/\p{Diacritic}/gu, "")
      .toLowerCase();
  const needle = normalize(query.trim());
  return !needle || normalize(`${item.title} ${item.artist ?? ""}`).includes(needle);
}
