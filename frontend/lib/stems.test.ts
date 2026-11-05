import { describe, expect, it } from "vitest";

import { toggleStem } from "./stems";

describe("toggleStem", () => {
  it("ajoute une piste", () => {
    expect(toggleStem(["piano"], "vocals")).toEqual(["piano", "vocals"]);
  });

  it("retire une piste", () => {
    expect(toggleStem(["piano", "bass"], "bass")).toEqual(["piano"]);
  });

  it("garde au moins une piste", () => {
    expect(toggleStem(["piano"], "piano")).toEqual(["piano"]);
  });

  it("ignore la batterie", () => {
    expect(toggleStem(["piano"], "drums")).toEqual(["piano"]);
  });
});
