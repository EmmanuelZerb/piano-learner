import { describe, expect, it } from "vitest";

import {
  beatPeriod,
  PPQ,
  realDuration,
  secondsToTicks,
  tickTime,
  ticksToSeconds,
  transportBpm,
  waitPointTime,
} from "./timing";

describe("conversions temps du morceau ↔ Transport", () => {
  it("fait correspondre un temps du Transport à une seconde du morceau", () => {
    expect(secondsToTicks(1)).toBe(PPQ);
    expect(ticksToSeconds(secondsToTicks(83.4567))).toBeCloseTo(83.4567, 2);
    expect(tickTime(0.5)).toBe("480i");
    expect(secondsToTicks(-1)).toBe(0);
  });

  it("garde une précision de l'ordre de la milliseconde sur un long morceau", () => {
    for (const t of [0.0011, 59.9993, 299.123]) {
      expect(Math.abs(ticksToSeconds(secondsToTicks(t)) - t)).toBeLessThanOrEqual(0.5 / PPQ);
    }
  });

  it("place le point d'attente un tick avant la note", () => {
    expect(waitPointTime(1)).toBe(`${PPQ - 1}i`);
    expect(waitPointTime(0)).toBe("0i");
  });
});

describe("vitesse", () => {
  it("convertit la vitesse en BPM du Transport", () => {
    expect(transportBpm(1)).toBe(60);
    expect(transportBpm(0.25)).toBe(15);
    expect(transportBpm(1.5)).toBe(90);
  });

  it("allonge les temps et la durée réelle quand on ralentit", () => {
    expect(beatPeriod(120, 1)).toBe(0.5);
    expect(beatPeriod(120, 0.5)).toBe(1);
    expect(realDuration(180, 0.6)).toBe(300); // 3 min à 60 % = 5 min de lecture
  });

  it("n'accumule pas de dérive : position = vitesse × temps écoulé", () => {
    // Le Transport avance de transportBpm(v) / 60 temps par seconde réelle, soit v s du morceau.
    const speed = 0.75;
    const elapsed = 300; // 5 minutes
    const songSeconds = (transportBpm(speed) / 60) * elapsed;
    expect(songSeconds).toBeCloseTo(speed * elapsed, 10);
  });
});
