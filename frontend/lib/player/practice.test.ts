import { describe, expect, it } from "vitest";

import { keyAt, keyboardLayout } from "./keyboard";
import { parseMidiMessage } from "./midi";
import type { PlayerNote } from "./notes";
import { accuracy, chordSatisfied, PracticeJudge, practiceTargets, waitSteps } from "./practice";

const note = (pitch: number, start: number, hand: "L" | "R" = "R"): PlayerNote => ({
  pitch,
  start,
  end: start + 0.4,
  velocity: 80,
  hand,
});

const song = [
  note(48, 0.0, "L"),
  note(60, 0.0),
  note(64, 0.02),
  note(67, 0.5),
  note(52, 1.0, "L"),
  note(72, 1.0),
];

describe("cibles et étapes d'attente", () => {
  it("ne garde que les mains travaillées", () => {
    expect(practiceTargets(song, "R").map((n) => n.pitch)).toEqual([60, 64, 67, 72]);
    expect(practiceTargets(song, "L").map((n) => n.pitch)).toEqual([48, 52]);
    expect(practiceTargets(song, "LR")).toHaveLength(6);
  });

  it("regroupe les attaques quasi simultanées en accords", () => {
    expect(waitSteps(practiceTargets(song, "R"))).toEqual([
      { time: 0, pitches: [60, 64] },
      { time: 0.5, pitches: [67] },
      { time: 1.0, pitches: [72] },
    ]);
  });

  it("valide un accord tenu ou joué note par note", () => {
    const step = { time: 0, pitches: [60, 64] };
    expect(chordSatisfied(step, new Set([60]), new Set())).toBe(false);
    expect(chordSatisfied(step, new Set([60, 64]), new Set())).toBe(true);
    expect(chordSatisfied(step, new Set([64]), new Set([60]))).toBe(true);
  });
});

describe("PracticeJudge", () => {
  const targets = practiceTargets(song, "R");

  it("compte justes, fausses et manquées", () => {
    const judge = new PracticeJudge(targets);
    expect(judge.noteOn(60, 0.05, 0.15)).toBe("hit");
    expect(judge.noteOn(60, 0.06, 0.15)).toBe("wrong"); // déjà jouée
    expect(judge.noteOn(61, 0.5, 0.15)).toBe("wrong"); // mauvaise hauteur
    expect(judge.noteOn(67, 0.9, 0.15)).toBe("wrong"); // trop tard
    judge.advance(1.3, 0.15);
    expect(judge.score()).toEqual({ hits: 1, wrongs: 3, misses: 3 });
    expect(judge.judgement(targets[0])).toBe(1);
    expect(judge.judgement(targets[1])).toBe(2);
    expect(accuracy(judge.score())).toBeCloseTo(1 / 7);
  });

  it("permet de rejouer un passage après un retour en arrière", () => {
    const judge = new PracticeJudge(targets);
    judge.advance(2, 0.15);
    expect(judge.misses).toBe(4);
    judge.rewind(0.4, 0.15);
    expect(judge.judgement(targets[2])).toBe(0);
    expect(judge.noteOn(67, 0.5, 0.15)).toBe("hit");
    expect(judge.misses).toBe(4); // le score de la séance est conservé
  });

  it("choisit la note attendue la plus proche", () => {
    const repeated = [note(60, 0), note(60, 0.2)];
    const judge = new PracticeJudge(repeated);
    judge.noteOn(60, 0.18, 0.15);
    expect(judge.judgement(repeated[1])).toBe(1);
    expect(judge.judgement(repeated[0])).toBe(0);
  });
});

describe("MIDI et clavier à la souris", () => {
  it("décode Note On / Note Off sur tous les canaux", () => {
    expect(parseMidiMessage([0x90, 60, 100])).toEqual({ type: "on", pitch: 60, velocity: 100 });
    expect(parseMidiMessage([0x93, 61, 0])).toEqual({ type: "off", pitch: 61, velocity: 0 });
    expect(parseMidiMessage([0x80, 62, 64])).toEqual({ type: "off", pitch: 62, velocity: 0 });
    expect(parseMidiMessage([0xb0, 64, 127])).toBeNull(); // pédale : ignorée
    expect(parseMidiMessage([0xf8])).toBeNull(); // horloge
  });

  it("trouve la touche sous la souris, noires devant", () => {
    const layout = keyboardLayout(1040); // blanches de 20 px
    const c4 = layout.find((k) => k.pitch === 60)!;
    expect(keyAt(layout, c4.x + 19, 90, 100)?.pitch).toBe(60); // bas : blanche
    expect(keyAt(layout, c4.x + 19, 10, 100)?.pitch).toBe(61); // haut : noire
    expect(keyAt(layout, c4.x + 5, 10, 100)?.pitch).toBe(60);
  });
});
