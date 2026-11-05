export type ShortcutAction =
  | { type: "toggle-play" }
  | { type: "seek-by"; seconds: number }
  | { type: "speed-by"; delta: number }
  | { type: "go-start" }
  | { type: "set-loop-a" }
  | { type: "set-loop-b" }
  | { type: "clear-loop" }
  | { type: "toggle-metronome" }
  | { type: "toggle-names" }
  | { type: "toggle-stats" }
  | { type: "toggle-count-in" }
  | { type: "toggle-hand"; hand: "L" | "R" }
  | { type: "level"; index: number }
  | { type: "zoom-by"; factor: number };

export const SHORTCUT_HELP: [string, string][] = [
  ["Espace", "lecture / pause"],
  ["← →", "reculer / avancer de 5 s (Maj : 1 s)"],
  ["↑ ↓", "vitesse ± 5 %"],
  ["Début", "retour au début"],
  ["A / B", "début / fin de boucle"],
  ["Échap", "supprimer la boucle"],
  ["G / D", "couper la main gauche / droite"],
  ["1 2 3", "niveau débutant / intermédiaire / avancé"],
  ["M", "métronome"],
  ["C", "décompte avant lecture"],
  ["N", "nom des notes"],
  ["+ / -", "zoom vertical"],
  ["F", "fluidité et dérive (diagnostic)"],
];

type KeyInput = {
  key: string;
  shiftKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
};

/** Touche → action, ou null si la touche ne concerne pas le lecteur. */
export function shortcutFor(event: KeyInput): ShortcutAction | null {
  if (event.ctrlKey || event.metaKey || event.altKey) return null;
  const step = event.shiftKey ? 1 : 5;
  switch (event.key) {
    case " ":
      return { type: "toggle-play" };
    case "ArrowLeft":
      return { type: "seek-by", seconds: -step };
    case "ArrowRight":
      return { type: "seek-by", seconds: step };
    case "ArrowUp":
      return { type: "speed-by", delta: 0.05 };
    case "ArrowDown":
      return { type: "speed-by", delta: -0.05 };
    case "Home":
      return { type: "go-start" };
    case "Escape":
      return { type: "clear-loop" };
    case "+":
    case "=":
      return { type: "zoom-by", factor: 1.25 };
    case "-":
      return { type: "zoom-by", factor: 0.8 };
    case "1":
    case "2":
    case "3":
      return { type: "level", index: Number(event.key) - 1 };
  }
  switch (event.key.toLowerCase()) {
    case "a":
      return { type: "set-loop-a" };
    case "b":
      return { type: "set-loop-b" };
    case "m":
      return { type: "toggle-metronome" };
    case "n":
      return { type: "toggle-names" };
    case "f":
      return { type: "toggle-stats" };
    case "c":
      return { type: "toggle-count-in" };
    case "g":
      return { type: "toggle-hand", hand: "L" };
    case "d":
      return { type: "toggle-hand", hand: "R" };
  }
  return null;
}

/** Ne pas détourner la frappe dans un champ de saisie. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable || target.tagName === "TEXTAREA") return true;
  return (
    target.tagName === "INPUT" && !["range", "checkbox"].includes((target as HTMLInputElement).type)
  );
}
