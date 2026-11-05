/**
 * Moteur audio du lecteur, entièrement piloté par l'horloge audio (Tone.Transport).
 *
 * Le temps du morceau est exprimé en ticks du Transport : à 60 BPM, un temps = une seconde,
 * donc `ticks / PPQ` = secondes dans l'audio d'origine. Changer la vitesse revient à changer
 * le BPM : les notes déjà programmées gardent leur place, sans reprogrammation ni dérive.
 * L'affichage lit la même horloge (`songTime()`), d'où l'absence de décalage image/son.
 */
import * as Tone from "tone";

import { sustainedEnds, type ArrangementData, type Hand } from "@/lib/player/notes";
import { SALAMANDER_URLS } from "@/lib/player/samples.mjs";

const PPQ = 960; // résolution ≈ 1 ms
const BASE_BPM = 60;
const START_DELAY_S = 0.05;

type NoteEvent = { time: string; type: "on" | "off"; note: string; velocity: number; hand: Hand };
type AccompanimentNode = Tone.Player | Tone.GrainPlayer;

const ticks = (seconds: number) => `${Math.max(0, Math.round(seconds * PPQ))}i`;

export class PlayerEngine {
  readonly ready: Promise<void>;
  private readonly transport = Tone.getTransport();
  private readonly pianoGain = new Tone.Gain(0.9).toDestination();
  private readonly accGain = new Tone.Gain(0.7).toDestination();
  private readonly sampler: Tone.Sampler;
  private readonly click = new Tone.Synth({
    oscillator: { type: "square" },
    envelope: { attack: 0.001, decay: 0.04, sustain: 0, release: 0.01 },
    volume: -14,
  }).toDestination();
  private part: Tone.Part<NoteEvent> | null = null;
  private metronomePart: Tone.Part<{ time: string; accent: boolean }> | null = null;
  private data: ArrangementData | null = null;
  private muted: Record<Hand, boolean> = { L: false, R: false };
  private metronome = false;
  private speed = 1;
  private loopStart = 0;
  private countInEnd: number | null = null;
  private waitPart: Tone.Part<{ time: string; index: number }> | null = null;
  private wait: { index: number; at: number } | null = null;
  private resumedFrom: number | null = null;
  // Intervalle (temps audio) pendant lequel le Transport avance réellement.
  private runFrom: number | null = null;
  private runUntil: number | null = null;
  private accBuffers = new Map<string, Tone.ToneAudioBuffer>();
  private accEnabled: string[] = [];
  private accNodes: AccompanimentNode[] = [];

  constructor(samplesBaseUrl: string) {
    this.transport.stop();
    this.transport.cancel();
    this.transport.PPQ = PPQ;
    this.transport.bpm.value = BASE_BPM;
    this.transport.loop = false;
    this.sampler = new Tone.Sampler({
      urls: SALAMANDER_URLS,
      baseUrl: samplesBaseUrl,
      release: 1,
    }).connect(this.pianoGain);
    this.transport.on("loop", this.onLoop);
    this.ready = Tone.loaded();
  }

  // --- Horloge ------------------------------------------------------------------------------

  get playing(): boolean {
    return this.transport.state === "started";
  }

  /** Instant audio actuellement entendu : horloge audio moins la latence de sortie. */
  audioTime(): number {
    const raw = Tone.getContext().rawContext as AudioContext;
    return raw.currentTime - (raw.outputLatency || 0);
  }

  /** Position (s) dans le morceau à l'instant entendu. */
  songTime(): number {
    const heard = this.audioTime();
    const running =
      this.runFrom !== null &&
      heard >= this.runFrom &&
      (this.runUntil === null || heard < this.runUntil);
    // À l'arrêt, on lit la position courante du Transport (à « maintenant ») : un saut fait
    // en pause est ainsi visible tout de suite, sans attendre l'anticipation de Tone.
    return (running ? this.transport.getTicksAtTime(heard) : this.transport.ticks) / PPQ;
  }

  /** Secondes restantes avant la fin du décompte (null hors décompte). */
  countInRemaining(): number | null {
    if (this.countInEnd === null) return null;
    const left = this.countInEnd - Tone.getContext().currentTime;
    if (left <= 0) this.countInEnd = null;
    return left > 0 ? left : null;
  }

  beatPeriod(): number {
    return this.data ? 60 / this.data.tempo / this.speed : 0.5;
  }

  // --- Contenu ------------------------------------------------------------------------------

  setArrangement(data: ArrangementData): void {
    this.data = data;
    this.part?.dispose();
    this.metronomePart?.dispose();
    this.sampler.releaseAll();

    const ends = sustainedEnds(data.notes, data.pedals);
    const events: NoteEvent[] = [];
    data.notes.forEach((n, i) => {
      const note = Tone.Frequency(n.pitch, "midi").toNote();
      const velocity = n.velocity / 127;
      events.push({ time: ticks(n.start), type: "on", note, velocity, hand: n.hand });
      events.push({ time: ticks(ends[i]), type: "off", note, velocity, hand: n.hand });
    });
    this.part = new Tone.Part<NoteEvent>((time, ev) => {
      if (ev.type === "off") this.sampler.triggerRelease(ev.note, time);
      else if (!this.muted[ev.hand]) this.sampler.triggerAttack(ev.note, time, ev.velocity);
    }, events).start(0);

    const beats = data.beats.map((b, i) => ({ time: ticks(b), accent: i % 4 === 0 }));
    this.metronomePart = new Tone.Part<{ time: string; accent: boolean }>((time, beat) => {
      if (this.metronome) this.tick(time, beat.accent);
    }, beats).start(0);
  }

  // --- Transport ------------------------------------------------------------------------------

  async play(countInBeats = 0): Promise<void> {
    await Tone.start();
    let startAt = Tone.now() + START_DELAY_S;
    if (countInBeats > 0) {
      const period = this.beatPeriod();
      for (let k = 0; k < countInBeats; k++) this.tick(startAt + k * period, k === 0);
      startAt += countInBeats * period;
      this.countInEnd = startAt;
    }
    this.transport.start(startAt);
    this.runFrom = startAt;
    this.runUntil = null;
    this.restartAccompaniment(startAt, this.transport.ticks / PPQ);
  }

  pause(): void {
    this.transport.pause();
    this.runFrom = null;
    this.countInEnd = null;
    this.wait = null;
    this.sampler.releaseAll();
    this.stopAccompaniment();
  }

  seek(seconds: number): void {
    const target = Math.max(0, Math.min(seconds, this.data?.duration ?? seconds));
    this.wait = null;
    this.transport.ticks = Math.round(target * PPQ);
    this.sampler.releaseAll();
    if (this.playing) this.restartAccompaniment(Tone.now(), target);
  }

  setSpeed(speed: number): void {
    const position = this.songTime();
    this.speed = speed;
    this.transport.bpm.value = BASE_BPM * speed;
    if (this.playing) this.restartAccompaniment(Tone.now(), position);
  }

  setLoop(loop: { a: number; b: number } | null): void {
    if (loop === null) {
      this.transport.loop = false;
      return;
    }
    this.loopStart = loop.a;
    this.transport.loopStart = ticks(loop.a);
    this.transport.loopEnd = ticks(loop.b);
    this.transport.loop = true;
  }

  private onLoop = (time: number): void => {
    this.sampler.releaseAll(time);
    this.restartAccompaniment(time, this.loopStart);
  };

  // --- Mode attente (entraînement) ------------------------------------------------------------

  /** Un point d'arrêt juste avant chaque étape. `shouldWait(i)` est appelé un peu en avance
   * (anticipation du Transport) : il renvoie false si l'accord est déjà tenu. */
  setWaitSteps(times: number[] | null, shouldWait: (index: number) => boolean): void {
    this.waitPart?.dispose();
    this.waitPart = null;
    this.wait = null;
    if (!times) return;
    const events = times.map((t, index) => ({
      time: `${Math.max(0, Math.round(t * PPQ) - 1)}i`,
      index,
    }));
    this.waitPart = new Tone.Part<{ time: string; index: number }>((time, ev) => {
      if (ev.index === this.resumedFrom) {
        this.resumedFrom = null; // le point où l'on vient de repartir ne bloque pas à nouveau
        return;
      }
      if (!shouldWait(ev.index)) return;
      this.transport.pause(time);
      this.runUntil = time;
      this.stopAccompaniment(time);
      this.wait = { index: ev.index, at: time };
    }, events).start(0);
  }

  /** Étape attendue (arrêt atteint ou imminent), null hors attente. */
  waitingIndex(): number | null {
    return this.wait?.index ?? null;
  }

  /** Reprend après une attente. Jamais avant l'instant d'arrêt déjà programmé, sinon la
   * reprise passerait avant la pause et la lecture resterait bloquée. */
  resume(): void {
    if (!this.wait) return;
    const at = Math.max(Tone.now() + 0.02, this.wait.at + 0.005);
    const position = this.transport.getTicksAtTime(this.wait.at) / PPQ;
    this.resumedFrom = this.wait.index;
    this.wait = null;
    this.transport.start(at);
    this.runFrom = at;
    this.runUntil = null;
    this.restartAccompaniment(at, position);
  }

  get waiting(): boolean {
    return this.wait !== null;
  }

  // --- Notes jouées par l'utilisateur ---------------------------------------------------------

  async previewNote(pitch: number, velocity: number): Promise<void> {
    await Tone.start();
    this.sampler.triggerAttack(Tone.Frequency(pitch, "midi").toNote(), Tone.now(), velocity / 127);
  }

  releasePreview(pitch: number): void {
    this.sampler.triggerRelease(Tone.Frequency(pitch, "midi").toNote(), Tone.now());
  }

  // --- Réglages -------------------------------------------------------------------------------

  setMuted(hand: Hand, muted: boolean): void {
    this.muted[hand] = muted;
  }

  setMetronome(on: boolean): void {
    this.metronome = on;
  }

  setVolumes(piano: number, accompaniment: number): void {
    this.pianoGain.gain.rampTo(piano, 0.05);
    this.accGain.gain.rampTo(accompaniment, 0.05);
  }

  private tick(time: number, accent: boolean): void {
    this.click.triggerAttackRelease(accent ? "C6" : "G5", 0.03, time, accent ? 0.9 : 0.5);
  }

  // --- Accompagnement (stems d'origine) ---------------------------------------------------------

  /** Charge (une fois) et active les pistes d'accompagnement. `sources` : nom → URL. */
  async setAccompaniment(sources: Record<string, string>, enabled: string[]): Promise<void> {
    await Promise.all(
      enabled
        .filter((name) => !this.accBuffers.has(name))
        .map(async (name) => {
          this.accBuffers.set(name, await new Tone.ToneAudioBuffer().load(sources[name]));
        }),
    );
    this.accEnabled = enabled;
    if (this.playing) this.restartAccompaniment(Tone.now(), this.songTime());
    else this.stopAccompaniment();
  }

  /** À vitesse normale : lecture directe (qualité d'origine). Sinon : lecture granulaire, qui
   * change la vitesse sans changer la hauteur (au prix de quelques artefacts). */
  private restartAccompaniment(at: number, position: number): void {
    this.stopAccompaniment(at);
    for (const name of this.accEnabled) {
      const buffer = this.accBuffers.get(name);
      if (!buffer || position >= buffer.duration) continue;
      const node: AccompanimentNode =
        this.speed === 1
          ? new Tone.Player(buffer)
          : new Tone.GrainPlayer({
              url: buffer,
              playbackRate: this.speed,
              grainSize: 0.1,
              overlap: 0.05,
            });
      node.connect(this.accGain).start(at, position);
      this.accNodes.push(node);
    }
  }

  private stopAccompaniment(at?: number): void {
    for (const node of this.accNodes) {
      node.stop(at);
      const dispose = () => node.dispose();
      setTimeout(dispose, Math.max(0, ((at ?? Tone.now()) - Tone.now()) * 1000) + 200);
    }
    this.accNodes = [];
  }

  dispose(): void {
    this.transport.off("loop", this.onLoop);
    this.transport.stop();
    this.transport.cancel();
    this.transport.loop = false;
    this.stopAccompaniment();
    this.part?.dispose();
    this.metronomePart?.dispose();
    this.waitPart?.dispose();
    for (const node of [this.sampler, this.click, this.pianoGain, this.accGain]) node.dispose();
    this.accBuffers.forEach((b) => b.dispose());
  }
}
