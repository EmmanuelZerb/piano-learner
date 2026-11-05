import { describe, expect, it } from "vitest";

import { describeDevice, type DeviceInfo } from "./api";

const base: DeviceInfo = {
  torch_installed: true,
  torch_version: "2.8.0",
  device: "cuda",
  name: "RTX",
  vram_gb: 8,
};

describe("describeDevice", () => {
  it("décrit un GPU CUDA avec sa VRAM", () => {
    expect(describeDevice(base)).toBe("CUDA · RTX · 8 Go");
  });

  it("signale le repli CPU", () => {
    expect(describeDevice({ ...base, device: "cpu", name: null })).toBe("CPU (aucun GPU détecté)");
  });

  it("signale l'absence de torch", () => {
    expect(describeDevice({ ...base, torch_installed: false })).toMatch(/torch non installé/);
  });
});
