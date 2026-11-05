import { describe, expect, it } from "vitest";

import { errorMessage } from "./api";
import { formatDuration } from "./format";

describe("formatDuration", () => {
  it.each([
    [0, "0:00"],
    [9.6, "0:10"],
    [125.4, "2:05"],
    [3725, "1:02:05"],
    [-3, "0:00"],
  ])("%s s → %s", (input, expected) => {
    expect(formatDuration(input)).toBe(expected);
  });
});

describe("errorMessage", () => {
  it("lit un detail texte", () => {
    expect(errorMessage({ code: "private", detail: "Cette vidéo est privée." }, 422)).toBe(
      "Cette vidéo est privée.",
    );
  });

  it("lit une erreur de validation FastAPI", () => {
    expect(errorMessage({ detail: [{ msg: "Field required" }] }, 422)).toBe("Field required");
  });

  it("retombe sur le statut HTTP", () => {
    expect(errorMessage(null, 500)).toBe("Erreur HTTP 500");
  });
});
