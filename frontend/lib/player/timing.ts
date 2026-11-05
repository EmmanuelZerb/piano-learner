/**
 * Conversions entre le temps du morceau (secondes de l'audio d'origine) et le Transport Tone.
 *
 * À BASE_BPM = 60, un temps du Transport dure une seconde : `ticks / PPQ` donne donc
 * directement la position dans le morceau, et la vitesse de lecture n'est qu'un BPM.
 */

export const PPQ = 960; // résolution ≈ 1 ms
export const BASE_BPM = 60;

export function secondsToTicks(seconds: number): number {
  return Math.max(0, Math.round(seconds * PPQ));
}

export function ticksToSeconds(ticks: number): number {
  return ticks / PPQ;
}

/** Notation Tone.js d'une position en ticks (« 960i »). */
export function tickTime(seconds: number): string {
  return `${secondsToTicks(seconds)}i`;
}

/** Point d'arrêt du mode attente : un tick avant l'attaque, pour que la note ne parte pas. */
export function waitPointTime(seconds: number): string {
  return `${Math.max(0, secondsToTicks(seconds) - 1)}i`;
}

export function transportBpm(speed: number): number {
  return BASE_BPM * speed;
}

/** Durée réelle (s) d'un temps musical à une vitesse donnée : métronome et décompte. */
export function beatPeriod(tempo: number, speed: number): number {
  return 60 / tempo / speed;
}

/** Durée réelle (s) pour parcourir `songSeconds` du morceau à cette vitesse. */
export function realDuration(songSeconds: number, speed: number): number {
  return songSeconds / speed;
}
