/** Clavier MIDI via la Web MIDI API (Chrome/Edge ; autorisation demandée par le navigateur). */

export type MidiNoteMessage = { type: "on" | "off"; pitch: number; velocity: number };
export type MidiDevice = { id: string; name: string };

/** Note On / Note Off, tous canaux. Une Note On de vélocité 0 vaut Note Off. */
export function parseMidiMessage(data: Uint8Array | number[]): MidiNoteMessage | null {
  if (data.length < 3) return null;
  const command = data[0] & 0xf0;
  const pitch = data[1];
  const velocity = data[2];
  if (command === 0x90 && velocity > 0) return { type: "on", pitch, velocity };
  if (command === 0x80 || command === 0x90) return { type: "off", pitch, velocity: 0 };
  return null;
}

export function midiSupported(): boolean {
  return typeof navigator !== "undefined" && "requestMIDIAccess" in navigator;
}

export async function requestMidi(): Promise<MIDIAccess> {
  if (!midiSupported())
    throw new Error("Ce navigateur ne gère pas le MIDI (utilise Chrome ou Edge).");
  return navigator.requestMIDIAccess({ sysex: false });
}

export function listInputs(access: MIDIAccess): MidiDevice[] {
  return [...access.inputs.values()].map((input) => ({
    id: input.id,
    name: input.name ?? `Entrée ${input.id}`,
  }));
}

/** Écoute une entrée ; renvoie la fonction de désabonnement. */
export function listenInput(
  access: MIDIAccess,
  id: string,
  onMessage: (message: MidiNoteMessage) => void,
): () => void {
  const input = access.inputs.get(id);
  if (!input) return () => undefined;
  const handler = (event: MIDIMessageEvent) => {
    const message = event.data ? parseMidiMessage(event.data) : null;
    if (message) onMessage(message);
  };
  input.addEventListener("midimessage", handler);
  return () => input.removeEventListener("midimessage", handler);
}
