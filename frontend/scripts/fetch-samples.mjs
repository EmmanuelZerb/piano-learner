// Télécharge les échantillons du Salamander Grand Piano (CC-BY 3.0, Alexander Holm) dans
// public/samples/salamander/ pour que le lecteur fonctionne hors ligne. Ignorés par git.
// Usage : npm run fetch:samples
import { mkdir, stat, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { SALAMANDER_FILES } from "../lib/player/samples.mjs";

const BASE = "https://tonejs.github.io/audio/salamander/";
const dest = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "samples", "salamander");

await mkdir(dest, { recursive: true });
let downloaded = 0;
for (const file of SALAMANDER_FILES) {
  const target = join(dest, file);
  if (await stat(target).catch(() => null)) continue;
  const res = await fetch(BASE + file);
  if (!res.ok) throw new Error(`${file} : HTTP ${res.status}`);
  await writeFile(target, Buffer.from(await res.arrayBuffer()));
  downloaded += 1;
}
console.log(
  `Salamander : ${downloaded} téléchargé(s), ${SALAMANDER_FILES.length} au total dans ${dest}`,
);
