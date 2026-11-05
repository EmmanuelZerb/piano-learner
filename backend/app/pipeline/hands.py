"""Répartition main gauche / main droite.

Heuristique volontairement simple et isolée (remplaçable par un modèle plus tard) :
- les notes attaquées ensemble forment un « accord » ;
- pour chaque accord, on choisit la coupure entre deux notes voisines qui minimise un coût :
  éloignement du point de partage courant + écart de chaque main au-delà d'une neuvième +
  plus de 5 notes dans une main ;
- le point de partage suit le registre joué (glissement progressif), puis revient lentement
  vers sa valeur initiale.
"""

from dataclasses import replace

from app.pipeline.notes import Note

CHORD_WINDOW_S = 0.05
MAX_SPAN = 14  # neuvième majeure : écart confortable pour une main
MAX_NOTES_PER_HAND = 5
SPLIT_RANGE = (48, 74)  # le point de partage reste entre C3 et D5


def group_onsets(notes: list[Note], window: float = CHORD_WINDOW_S) -> list[list[Note]]:
    """Notes triées regroupées par attaque quasi simultanée."""
    clusters: list[list[Note]] = []
    for n in sorted(notes, key=lambda n: (n.start, n.pitch)):
        if clusters and n.start - clusters[-1][0].start <= window:
            clusters[-1].append(n)
        else:
            clusters.append([n])
    return clusters


def _distance_to_interval(x: float, low: float, high: float) -> float:
    return 0.0 if low <= x <= high else min(abs(x - low), abs(x - high))


def _best_cut(pitches: list[int], split: float) -> int:
    """Indice k : pitches[:k] à gauche, pitches[k:] à droite."""

    def cost(k: int) -> float:
        left, right = pitches[:k], pitches[k:]
        low = pitches[k - 1] if k > 0 else -1e9
        high = pitches[k] if k < len(pitches) else 1e9
        c = _distance_to_interval(split, low, high) / 12
        for hand in (left, right):
            if hand:
                c += 3 * max(0, hand[-1] - hand[0] - MAX_SPAN) / 12
                c += 2 * max(0, len(hand) - MAX_NOTES_PER_HAND)
        return c

    return min(range(len(pitches) + 1), key=cost)


def split_hands(notes: list[Note], initial_split: int = 60, dynamic: bool = True) -> list[Note]:
    split = float(initial_split)
    out: list[Note] = []
    for cluster in group_onsets(notes):
        cluster.sort(key=lambda n: n.pitch)
        k = _best_cut([n.pitch for n in cluster], split)
        out += [replace(n, hand="L" if i < k else "R") for i, n in enumerate(cluster)]
        if not dynamic:
            continue
        low = cluster[k - 1].pitch if k > 0 else split - 6
        high = cluster[k].pitch if k < len(cluster) else split + 6
        boundary = (low + high) / 2
        split = 0.7 * split + 0.3 * boundary  # suit le registre
        split = 0.95 * split + 0.05 * initial_split  # et y revient doucement
        split = min(max(split, SPLIT_RANGE[0]), SPLIT_RANGE[1])
    return out
