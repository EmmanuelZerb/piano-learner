import { describe, expect, it } from "vitest";

import { HIGHEST, keyboardLayout, keyFor, LOWEST, WHITE_KEYS } from "./keyboard";
import {
  activeNotes,
  clampSpeed,
  firstIndexFrom,
  normalizeLoop,
  notesInWindow,
  parseArrangement,
  sustainedEnds,
  type PlayerNote,
} from "./notes";
import { keyboardHeight, noteAtPoint } from "./renderer";
import { SHORTCUT_HELP, shortcutFor } from "./shortcuts";

const key = (k: string, shiftKey = false) => ({
  key: k,
  shiftKey,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
});

describe("keyboardLayout", () => {
  const layout = keyboardLayout(1040);

  it("a 88 touches dont 52 blanches", () => {
    expect(layout).toHaveLength(HIGHEST - LOWEST + 1);
    expect(layout.filter((k) => !k.black)).toHaveLength(WHITE_KEYS);
  });

  it("place A0 à gauche et C8 au bord droit", () => {
    expect(keyFor(layout, 21)).toMatchObject({ x: 0, width: 20, black: false });
    const c8 = keyFor(layout, 108)!;
    expect(c8.x + c8.width).toBeCloseTo(1040);
  });

  it("centre les noires sur la jonction des blanches", () => {
    const c4 = keyFor(layout, 60)!;
    const cs4 = keyFor(layout, 61)!;
    expect(cs4.black).toBe(true);
    expect(cs4.x + cs4.width / 2).toBeCloseTo(c4.x + c4.width);
  });
});

const raw = {
  level: "advanced",
  tempo: 120,
  beats: [0, 0.5, 1],
  key: "C",
  chords: [[0, 1, "C"]] as [number, number, string][],
  pedals: [[0.5, 2.0]] as [number, number][],
  notes: [
    [64, 1.0, 1.5, 70, "R"],
    [48, 0.0, 3.0, 60, "L"],
    [60, 0.0, 0.4, 80, "R"],
    [67, 2.0, 2.2, 80, "R"],
  ] as [number, number, number, number, "L" | "R"][],
};

describe("arrangement", () => {
  const data = parseArrangement(raw);

  it("trie les notes et calcule les durées", () => {
    expect(data.notes.map((n) => n.pitch)).toEqual([48, 60, 64, 67]);
    expect(data.duration).toBe(3.0);
    expect(data.maxNoteDuration).toBe(3.0);
  });

  it("trouve les notes d'une fenêtre, y compris les notes longues commencées avant", () => {
    expect(firstIndexFrom(data.notes, 1.0)).toBe(2);
    expect(notesInWindow(data, 1.2, 1.8).map((n) => n.pitch)).toEqual([48, 64]);
    expect(notesInWindow(data, 2.5, 4).map((n) => n.pitch)).toEqual([48]);
  });

  it("donne les notes tenues à un instant", () => {
    expect(activeNotes(data, 0.2).map((n) => n.pitch)).toEqual([48, 60]);
    expect(activeNotes(data, 1.5).map((n) => n.pitch)).toEqual([48]);
  });

  it("prolonge les notes relâchées sous la pédale", () => {
    const notes: PlayerNote[] = [
      { pitch: 60, start: 0, end: 0.4, velocity: 80, hand: "R" }, // avant la pédale
      { pitch: 64, start: 1, end: 1.5, velocity: 80, hand: "R" }, // pendant
      { pitch: 67, start: 1.8, end: 2.5, velocity: 80, hand: "R" }, // après
    ];
    expect(sustainedEnds(notes, data.pedals)).toEqual([0.4, 2.0, 2.5]);
  });
});

describe("boucle et vitesse", () => {
  it("normalise la boucle A-B", () => {
    expect(normalizeLoop(5, 2, 10)).toEqual({ a: 2, b: 5 });
    expect(normalizeLoop(2, 2.2, 10)).toBeNull();
    expect(normalizeLoop(8, 15, 10)).toEqual({ a: 8, b: 10 });
    expect(normalizeLoop(null, 3, 10)).toBeNull();
  });

  it("borne la vitesse entre 25 % et 150 %", () => {
    expect(clampSpeed(0.1)).toBe(0.25);
    expect(clampSpeed(2)).toBe(1.5);
    expect(clampSpeed(0.95 + 0.05)).toBe(1);
  });
});

describe("raccourcis", () => {
  it("associe les touches aux actions", () => {
    expect(shortcutFor(key(" "))).toEqual({ type: "toggle-play" });
    expect(shortcutFor(key("ArrowLeft", true))).toEqual({ type: "seek-by", seconds: -1 });
    expect(shortcutFor(key("ArrowRight"))).toEqual({ type: "seek-by", seconds: 5 });
    expect(shortcutFor(key("G"))).toEqual({ type: "toggle-hand", hand: "L" });
    expect(shortcutFor(key("3"))).toEqual({ type: "level", index: 2 });
    expect(shortcutFor(key("f"))).toEqual({ type: "toggle-stats" });
    expect(shortcutFor(key("x"))).toBeNull();
    expect(shortcutFor({ ...key("a"), ctrlKey: true })).toBeNull();
  });
});

describe("sélection d'une note à la souris", () => {
  const data = parseArrangement(raw);
  const view = {
    width: 1040,
    height: 400,
    layout: keyboardLayout(1040),
    data,
    time: 0,
    pixelsPerSecond: 100,
  };
  const fall = 400 - keyboardHeight(1040);
  const center = (pitch: number) => {
    const k = keyFor(view.layout, pitch)!;
    return k.x + k.width / 2;
  };

  it("trouve la note sous le pointeur", () => {
    // 64 (Mi4) entre 1,0 s et 1,5 s → entre 100 et 150 px au-dessus du clavier.
    expect(noteAtPoint(view, center(64), fall - 120)?.pitch).toBe(64);
    expect(noteAtPoint(view, center(64), fall - 160)).toBeNull(); // après la fin
    expect(noteAtPoint(view, center(48), fall - 250)?.pitch).toBe(48); // note longue
  });

  it("ignore le clavier", () => {
    expect(noteAtPoint(view, center(48), fall + 10)).toBeNull();
  });
});

describe("aide des raccourcis", () => {
  it("n'a pas de touche en double", () => {
    const keys = SHORTCUT_HELP.map(([k]) => k);
    expect(new Set(keys).size).toBe(keys.length);
  });
});
