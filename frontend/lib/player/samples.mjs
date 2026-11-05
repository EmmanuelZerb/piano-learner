// Partagé entre le script de téléchargement (Node) et le lecteur (navigateur).
// Un échantillon toutes les tierces mineures (do, ré♯, fa♯, la) : Tone.Sampler transpose
// les notes intermédiaires d'au plus un ton et demi.

const NAMES = ["C", "Ds", "Fs", "A"];

/** Note Tone.js ("D#4") → nom de fichier Salamander ("Ds4.mp3"). */
export const SALAMANDER_URLS = (() => {
  const urls = { A0: "A0.mp3" };
  for (let octave = 1; octave <= 7; octave++) {
    for (const name of NAMES) urls[`${name.replace("s", "#")}${octave}`] = `${name}${octave}.mp3`;
  }
  urls.C8 = "C8.mp3";
  return urls;
})();

export const SALAMANDER_FILES = Object.values(SALAMANDER_URLS);
