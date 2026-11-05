import { describe, expect, it } from "vitest";

import { keyName, pitchName } from "./music";

describe("pitchName", () => {
  it.each([
    [60, "Do4"],
    [21, "La0"],
    [108, "Do8"],
    [70, "Si♭4"],
  ])("%s → %s", (pitch, name) => {
    expect(pitchName(pitch)).toBe(name);
  });
});

describe("keyName", () => {
  it.each([
    ["C", "Do majeur"],
    ["Am", "La mineur"],
    ["Eb", "Mi♭ majeur"],
    ["F#m", "Fa♯ mineur"],
  ])("%s → %s", (key, name) => {
    expect(keyName(key)).toBe(name);
  });
});
