import { describe, expect, it } from "vitest";

import { matchesQuery } from "./library";

describe("matchesQuery", () => {
  const item = { title: "Clair de lune", artist: "Debussy" };

  it("cherche dans le titre et l'artiste, sans casse ni accents", () => {
    expect(matchesQuery(item, "CLAIR")).toBe(true);
    expect(matchesQuery(item, "débuss")).toBe(true);
    expect(matchesQuery({ title: "Été", artist: null }, "ete")).toBe(true);
    expect(matchesQuery(item, "chopin")).toBe(false);
  });

  it("accepte tout avec une recherche vide", () => {
    expect(matchesQuery(item, "  ")).toBe(true);
  });
});
