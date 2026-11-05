export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type ToolInfo = {
  available: boolean;
  path: string | null;
  version: string | null;
};

export type DeviceInfo = {
  torch_installed: boolean;
  torch_version: string | null;
  device: "cuda" | "mps" | "cpu";
  name: string | null;
  vram_gb: number | null;
};

export type Health = {
  status: "ok" | "degraded";
  ffmpeg: ToolInfo;
  ffprobe: ToolInfo;
  device: DeviceInfo;
};

export async function fetchHealth(signal?: AbortSignal): Promise<Health> {
  const res = await fetch(`${API_BASE}/health`, { signal, cache: "no-store" });
  if (!res.ok) throw new Error(`API /health : HTTP ${res.status}`);
  return (await res.json()) as Health;
}

export function describeDevice(device: DeviceInfo): string {
  if (!device.torch_installed) return "torch non installé (uv sync --extra ml)";
  if (device.device === "cpu") return "CPU (aucun GPU détecté)";
  const vram = device.vram_gb ? ` · ${device.vram_gb} Go` : "";
  return `${device.device.toUpperCase()} · ${device.name ?? "?"}${vram}`;
}
