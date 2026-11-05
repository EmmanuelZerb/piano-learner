"use client";

import { useEffect, useState } from "react";

import { describeDevice, fetchHealth, type Health } from "@/lib/api";

type State =
  { kind: "loading" } | { kind: "error"; message: string } | { kind: "ok"; health: Health };

function Row({ label, ok, value }: { label: string; ok: boolean; value: string }) {
  return (
    <li className="flex items-center gap-3">
      <span className={`h-2.5 w-2.5 rounded-full ${ok ? "bg-emerald-500" : "bg-amber-500"}`} />
      <span className="w-20 text-zinc-500">{label}</span>
      <span className="font-mono text-sm">{value}</span>
    </li>
  );
}

export function HealthStatus() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then((health) => setState({ kind: "ok", health }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setState({ kind: "error", message: err instanceof Error ? err.message : String(err) });
      });
    return () => controller.abort();
  }, []);

  if (state.kind === "loading") return <p className="text-zinc-500">Connexion au backend…</p>;
  if (state.kind === "error")
    return <p className="text-red-500">Backend injoignable : {state.message}</p>;

  const { ffmpeg, ffprobe, device } = state.health;
  return (
    <ul className="space-y-2">
      <Row label="ffmpeg" ok={ffmpeg.available} value={ffmpeg.available ? "présent" : "absent"} />
      <Row
        label="ffprobe"
        ok={ffprobe.available}
        value={ffprobe.available ? "présent" : "absent"}
      />
      <Row label="Calcul" ok={device.device !== "cpu"} value={describeDevice(device)} />
    </ul>
  );
}
