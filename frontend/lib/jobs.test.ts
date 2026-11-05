import { describe, expect, it } from "vitest";

import type { Job } from "./api";
import { describeJob, describeTimings, isFinished, percent } from "./jobs";

const job: Job = {
  id: "j",
  label: "x",
  source: "youtube",
  track_id: null,
  status: "running",
  step: "separate",
  progress: 0.42,
  error_code: null,
  error_message: null,
  created_at: "",
  finished_at: null,
  timings: null,
};

describe("jobs", () => {
  it("décrit l'étape en cours", () => {
    expect(describeJob(job)).toBe("Séparation des pistes");
    expect(describeJob({ ...job, status: "queued" })).toBe("En attente");
    expect(describeJob({ ...job, status: "error", error_message: "Vidéo privée." })).toBe(
      "Vidéo privée.",
    );
  });

  it("sait quand une tâche est terminée", () => {
    expect(isFinished("running")).toBe(false);
    expect(isFinished("cancelled")).toBe(true);
  });

  it("formate le pourcentage", () => {
    expect(percent(0.426)).toBe("43 %");
    expect(percent(1.2)).toBe("100 %");
  });
});

describe("describeTimings", () => {
  it("résume les durées notables par étape", () => {
    expect(describeTimings({ download: 3.2, separate: 19.4, arrange: 0.2 })).toBe(
      "Téléchargement 3 s · Séparation des pistes 19 s",
    );
    expect(describeTimings(null)).toBeNull();
    expect(describeTimings({ arrange: 0.1 })).toBeNull();
  });
});
