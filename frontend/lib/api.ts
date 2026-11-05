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

export type Track = {
  id: string;
  title: string;
  artist: string | null;
  source: "upload" | "youtube";
  source_url: string | null;
  original_filename: string | null;
  duration_s: number;
  created_at: string;
  audio_url: string;
  thumbnail_url: string | null;
};

export type TrackCreated = { track: Track; duplicate: boolean };

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string | null,
  ) {
    super(message);
  }
}

/** Les URLs renvoyées par l'API sont relatives (ex. /tracks/{id}/audio). */
export function mediaUrl(path: string): string {
  return `${API_BASE}${path}`;
}

/** Message lisible depuis une réponse d'erreur FastAPI ({detail: string | [{msg}], code?}). */
export function errorMessage(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  }
  return `Erreur HTTP ${status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const code = (body as { code?: string } | null)?.code ?? null;
    throw new ApiError(errorMessage(body, res.status), res.status, code);
  }
  return body as T;
}

export function fetchHealth(signal?: AbortSignal): Promise<Health> {
  return request<Health>("/health", { signal });
}

export function listTracks(signal?: AbortSignal): Promise<Track[]> {
  return request<Track[]>("/tracks", { signal });
}

export function uploadTrack(file: File): Promise<TrackCreated> {
  const form = new FormData();
  form.append("file", file);
  return request<TrackCreated>("/tracks/upload", { method: "POST", body: form });
}

export function importYoutube(url: string): Promise<TrackCreated> {
  return request<TrackCreated>("/tracks/youtube", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
}

export function describeDevice(device: DeviceInfo): string {
  if (!device.torch_installed) return "torch non installé (uv sync --extra ml)";
  if (device.device === "cpu") return "CPU (aucun GPU détecté)";
  const vram = device.vram_gb ? ` · ${device.vram_gb} Go` : "";
  return `${device.device.toUpperCase()} · ${device.name ?? "?"}${vram}`;
}
