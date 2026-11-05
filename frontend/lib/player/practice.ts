/** Mode entraînement : notes à jouer, étapes du mode « attente » et arbitrage des notes. */
import { firstIndexFrom, type Hand, type PlayerNote } from "@/lib/player/notes";

export type PracticeMode = "off" | "wait" | "free";
export type PracticeHands = "R" | "L" | "LR";
export type Verdict = "hit" | "wrong";
export type NoteJudgement = 0 | 1 | 2; // 0 = pas encore jugée, 1 = jouée juste, 2 = manquée

/** Notes jouées ensemble à moins de 60 ms = un même accord à plaquer. */
export const CHORD_WINDOW_S = 0.06;
/** Tolérance de justesse rythmique, en temps réel (convertie en temps du morceau selon la vitesse). */
export const TOLERANCE_S = 0.15;

export type WaitStep = { time: number; pitches: number[] };
export type PracticeScore = { hits: number; wrongs: number; misses: number };

export function handsOf(hands: PracticeHands): Hand[] {
  return hands === "LR" ? ["L", "R"] : [hands];
}

export function practiceTargets(notes: PlayerNote[], hands: PracticeHands): PlayerNote[] {
  const played = new Set(handsOf(hands));
  return notes.filter((n) => played.has(n.hand));
}

/** Étapes du mode attente : chaque attaque (note seule ou accord) des mains travaillées. */
export function waitSteps(targets: PlayerNote[]): WaitStep[] {
  const steps: WaitStep[] = [];
  for (const note of targets) {
    const last = steps[steps.length - 1];
    if (last && note.start - last.time <= CHORD_WINDOW_S) {
      if (!last.pitches.includes(note.pitch)) last.pitches.push(note.pitch);
    } else {
      steps.push({ time: note.start, pitches: [note.pitch] });
    }
  }
  return steps;
}

/** L'accord est validé quand chaque note est tenue ou a été jouée depuis l'arrêt. */
export function chordSatisfied(step: WaitStep, held: Set<number>, pressed: Set<number>): boolean {
  return step.pitches.every((p) => held.has(p) || pressed.has(p));
}

export function accuracy(score: PracticeScore): number {
  const total = score.hits + score.wrongs + score.misses;
  return total ? score.hits / total : 0;
}

/** Arbitre : compare les notes jouées aux notes attendues des mains travaillées. */
export class PracticeJudge {
  hits = 0;
  wrongs = 0;
  misses = 0;
  private judged = new Map<PlayerNote, 1 | 2>();
  private cursor = 0; // première note cible pas encore périmée

  constructor(readonly targets: PlayerNote[]) {}

  /** Une touche enfoncée : juste si une note attendue de même hauteur tombe dans la tolérance. */
  noteOn(pitch: number, songTime: number, tolerance: number): Verdict {
    let best: PlayerNote | null = null;
    for (let i = firstIndexFrom(this.targets, songTime - tolerance); i < this.targets.length; i++) {
      const note = this.targets[i];
      if (note.start > songTime + tolerance) break;
      if (note.pitch !== pitch || this.judged.has(note)) continue;
      if (!best || Math.abs(note.start - songTime) < Math.abs(best.start - songTime)) best = note;
    }
    if (best) {
      this.judged.set(best, 1);
      this.hits++;
      return "hit";
    }
    this.wrongs++;
    return "wrong";
  }

  /** Mode libre : les notes dépassées sans avoir été jouées comptent comme manquées. */
  advance(songTime: number, tolerance: number): void {
    while (this.cursor < this.targets.length) {
      const note = this.targets[this.cursor];
      if (note.start + tolerance >= songTime) break;
      if (!this.judged.has(note)) {
        this.judged.set(note, 2);
        this.misses++;
      }
      this.cursor++;
    }
  }

  /** Retour en arrière (boucle, saut) : le passage pourra être rejoué et rejugé. Le score de
   * la séance est conservé. */
  rewind(songTime: number, tolerance: number): void {
    for (const note of this.judged.keys()) {
      if (note.start >= songTime - tolerance) this.judged.delete(note);
    }
    this.cursor = firstIndexFrom(this.targets, songTime - tolerance);
  }

  judgement(note: PlayerNote): NoteJudgement {
    return this.judged.get(note) ?? 0;
  }

  score(): PracticeScore {
    return { hits: this.hits, wrongs: this.wrongs, misses: this.misses };
  }
}
