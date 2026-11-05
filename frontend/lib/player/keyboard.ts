/** Géométrie du clavier 88 touches (A0 = 21 → C8 = 108). */

export const LOWEST = 21;
export const HIGHEST = 108;
export const WHITE_KEYS = 52;
const BLACK_PITCH_CLASSES = new Set([1, 3, 6, 8, 10]);
const BLACK_WIDTH_RATIO = 0.62;

export type Key = { pitch: number; x: number; width: number; black: boolean };

export function isBlack(pitch: number): boolean {
  return BLACK_PITCH_CLASSES.has(pitch % 12);
}

/** Une entrée par touche, indexée par `pitch - LOWEST`. Les noires sont centrées sur la
 * jonction entre les deux blanches voisines. */
export function keyboardLayout(width: number): Key[] {
  const whiteWidth = width / WHITE_KEYS;
  const blackWidth = whiteWidth * BLACK_WIDTH_RATIO;
  const keys: Key[] = [];
  let whites = 0;
  for (let pitch = LOWEST; pitch <= HIGHEST; pitch++) {
    if (isBlack(pitch)) {
      keys.push({ pitch, x: whites * whiteWidth - blackWidth / 2, width: blackWidth, black: true });
    } else {
      keys.push({ pitch, x: whites * whiteWidth, width: whiteWidth, black: false });
      whites++;
    }
  }
  return keys;
}

export function keyFor(layout: Key[], pitch: number): Key | undefined {
  return layout[pitch - LOWEST];
}

/** Hauteur des touches noires, en fraction de la hauteur du clavier. */
export const BLACK_KEY_HEIGHT_RATIO = 0.62;

/** Touche sous un point du clavier (y relatif au haut du clavier) : les noires passent devant. */
export function keyAt(
  layout: Key[],
  x: number,
  y: number,
  keyboardHeight: number,
): Key | undefined {
  const inside = (k: Key) => x >= k.x && x < k.x + k.width;
  if (y < keyboardHeight * BLACK_KEY_HEIGHT_RATIO) {
    const black = layout.find((k) => k.black && inside(k));
    if (black) return black;
  }
  return layout.find((k) => !k.black && inside(k));
}
