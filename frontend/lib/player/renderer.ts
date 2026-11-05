/** Dessin Canvas 2D d'une image : notes qui tombent + clavier. Aucune allocation lourde. */
import { keyFor, type Key } from "@/lib/player/keyboard";
import { activeNotes, notesInWindow, type ArrangementData, type Hand } from "@/lib/player/notes";
import { pitchName } from "@/lib/music";

export const HAND_COLORS: Record<Hand, { fill: string; dark: string; key: string }> = {
  R: { fill: "#22c55e", dark: "#15803d", key: "#4ade80" },
  L: { fill: "#3b82f6", dark: "#1d4ed8", key: "#60a5fa" },
};
const BACKGROUND = "#0b0b0f";
const BEAT_LINE = "rgba(255,255,255,0.05)";
const BAR_LINE = "rgba(255,255,255,0.12)";
const LOOP_SHADE = "rgba(250,204,21,0.08)";

export type FrameInput = {
  ctx: CanvasRenderingContext2D;
  width: number; // pixels CSS
  height: number;
  layout: Key[];
  data: ArrangementData;
  time: number;
  pixelsPerSecond: number;
  muted: Record<Hand, boolean>;
  showNames: boolean;
  loop: { a: number; b: number } | null;
  countIn: number | null; // temps restants du décompte
  stats: {
    fps: number;
    minFps: number;
    driftMs: number;
    maxAbsDriftMs: number;
    playedSeconds: number;
  } | null;
};

export function keyboardHeight(width: number): number {
  return Math.round(Math.min(150, Math.max(70, (width / 52) * 5.2)));
}

export function drawFrame(input: FrameInput): void {
  const { ctx, width, height } = input;
  const fallHeight = height - keyboardHeight(width);
  ctx.fillStyle = BACKGROUND;
  ctx.fillRect(0, 0, width, height);
  drawGrid(input, fallHeight);
  drawNotes(input, fallHeight);
  drawKeyboard(input, fallHeight);
  if (input.countIn !== null) drawCountIn(ctx, width, fallHeight, input.countIn);
  if (input.stats) drawStats(ctx, width, input.stats);
}

/** Ordonnée (px) d'un instant : le présent est au ras du clavier, le futur au-dessus. */
function yAt(t: number, input: FrameInput, fallHeight: number): number {
  return fallHeight - (t - input.time) * input.pixelsPerSecond;
}

function drawGrid(input: FrameInput, fallHeight: number): void {
  const { ctx, width, data, time, pixelsPerSecond, loop } = input;
  const horizon = time + fallHeight / pixelsPerSecond;
  if (loop && loop.b > time && loop.a < horizon) {
    const top = Math.max(0, yAt(loop.b, input, fallHeight));
    const bottom = Math.min(fallHeight, yAt(loop.a, input, fallHeight));
    ctx.fillStyle = LOOP_SHADE;
    ctx.fillRect(0, top, width, bottom - top);
  }
  for (let i = 0; i < data.beats.length; i++) {
    const beat = data.beats[i];
    if (beat < time) continue;
    if (beat > horizon) break;
    ctx.fillStyle = i % 4 === 0 ? BAR_LINE : BEAT_LINE;
    ctx.fillRect(0, Math.round(yAt(beat, input, fallHeight)), width, 1);
  }
}

function drawNotes(input: FrameInput, fallHeight: number): void {
  const { ctx, data, time, pixelsPerSecond, layout, muted, showNames } = input;
  const notes = notesInWindow(data, time, time + fallHeight / pixelsPerSecond);
  ctx.font = "600 10px system-ui, sans-serif";
  ctx.textAlign = "center";
  for (const note of notes) {
    const key = keyFor(layout, note.pitch);
    if (!key) continue;
    const top = yAt(note.end, input, fallHeight);
    const bottom = Math.min(fallHeight, yAt(note.start, input, fallHeight));
    const height = Math.max(2, bottom - top);
    const colors = HAND_COLORS[note.hand];
    ctx.globalAlpha = muted[note.hand] ? 0.25 : 1;
    ctx.fillStyle = key.black ? colors.dark : colors.fill;
    ctx.beginPath();
    ctx.roundRect(key.x + 1, top, key.width - 2, height, 3);
    ctx.fill();
    if (showNames && height > 14 && key.width > 9) {
      ctx.fillStyle = "rgba(0,0,0,0.75)";
      ctx.fillText(pitchName(note.pitch).replace(/\d+$/, ""), key.x + key.width / 2, bottom - 4);
    }
  }
  ctx.globalAlpha = 1;
}

function drawKeyboard(input: FrameInput, top: number): void {
  const { ctx, layout, data, time, height } = input;
  const pressed = new Map<number, Hand>();
  for (const note of activeNotes(data, time)) pressed.set(note.pitch, note.hand);

  const bottom = height - top;
  ctx.fillStyle = "#1f1f25";
  ctx.fillRect(0, top - 3, input.width, 3); // liseré au-dessus des touches
  for (const key of layout) {
    if (key.black) continue;
    const hand = pressed.get(key.pitch);
    ctx.fillStyle = hand ? HAND_COLORS[hand].key : "#f4f4f5";
    ctx.fillRect(key.x + 0.5, top, key.width - 1, bottom - 2);
  }
  const blackHeight = bottom * 0.62;
  for (const key of layout) {
    if (!key.black) continue;
    const hand = pressed.get(key.pitch);
    ctx.fillStyle = hand ? HAND_COLORS[hand].dark : "#18181b";
    ctx.fillRect(key.x, top, key.width, blackHeight);
  }
  // Repère du do central.
  const c4 = keyFor(layout, 60);
  if (c4) {
    ctx.fillStyle = "#a1a1aa";
    ctx.fillRect(c4.x + c4.width / 2 - 2, top + bottom - 10, 4, 4);
  }
}

function drawCountIn(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  beats: number,
): void {
  ctx.fillStyle = "rgba(0,0,0,0.45)";
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = "#fafafa";
  ctx.font = "700 96px system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(String(beats), width / 2, height / 2);
  ctx.textBaseline = "alphabetic";
}

function drawStats(
  ctx: CanvasRenderingContext2D,
  width: number,
  stats: NonNullable<FrameInput["stats"]>,
): void {
  const lines = [
    `${stats.fps} img/s (min ${Number.isFinite(stats.minFps) ? stats.minFps : "–"})`,
    `dérive ${stats.driftMs} ms (max ${stats.maxAbsDriftMs} ms)`,
    `lecture ${Math.round(stats.playedSeconds)} s`,
  ];
  ctx.fillStyle = "rgba(0,0,0,0.6)";
  ctx.fillRect(width - 230, 8, 222, 62);
  ctx.fillStyle = "#fafafa";
  ctx.font = "12px ui-monospace, monospace";
  ctx.textAlign = "left";
  lines.forEach((line, i) => ctx.fillText(line, width - 222, 26 + i * 18));
}
