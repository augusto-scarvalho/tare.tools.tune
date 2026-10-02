import json

import numpy as np

from tare.tools.tune import Creature
from tare.tools.tune.analysis import clean_f0, distance, features, segments, yin
from tare.tools.tune.clap import LABELS
from tare.tools.tune.designer import design, gene_names, match

SR = 16_000


def tone(f, dur=0.5, sr=SR):
    t = np.arange(int(dur * sr)) / sr
    return 0.5 * np.sin(2 * np.pi * f * t) * np.hanning(len(t)) ** 0.2


def test_yin_and_cleanup():
    f0, aper = yin(tone(220), SR)
    assert abs(np.median(f0[f0 > 0]) - 220) < 2 and np.median(aper[f0 > 0]) < 0.05
    track = np.full(100, 300.0)
    track[40:46] = 600.0                                   # an octave error
    assert np.allclose(clean_f0(track)[40:46], 300, rtol=0.02)


def test_features_and_distance():
    a = features(tone(300), SR)
    assert distance(a, a) == 0
    assert distance(a, features(tone(450), SR)) > 5           # ~7 semitones apart
    gap = np.concatenate([tone(300, 0.3), np.zeros(SR // 5), tone(300, 0.3)])
    assert segments(clean_f0(yin(gap, SR)[0])) == 2


def test_gene_names_cover_branches():
    genes = gene_names("monster")
    assert "kind" in genes and len(genes) > 10
    assert {"voice", "shape"} <= set(gene_names("bird"))      # song and squawk branches both probed


class FakeClap:
    """Stands in for CLAP: embeds audio by brightness and length, text by a fixed vector."""

    def text(self, texts):
        return np.array([[1.0, 0.0]] * len(texts))

    def audio(self, clips, sr=48_000):
        out = []
        for c in clips:
            spec = np.abs(np.fft.rfft(c))
            centroid = np.sum(np.fft.rfftfreq(len(c), 1 / sr) * spec) / (np.sum(spec) + 1e-9)
            v = np.array([np.exp(-centroid / 1500), len(c) / sr / 5])
            out.append(v / (np.linalg.norm(v) + 1e-12))
        return np.array(out)


def test_design_and_match_search():
    clap = FakeClap()
    c, score = design("a dark low growl", ["mammal", "reptile"], iters=4, screen=2, clap=clap, sr=SR)
    assert isinstance(c, Creature) and c.archetype in ("mammal", "reptile") and -1 <= score <= 1
    assert c == design("a dark low growl", ["mammal", "reptile"], iters=4, screen=2, clap=clap, sr=SR)[0]
    assert Creature.from_dict(json.loads(json.dumps(c.to_dict()))) == c
    target = Creature("mammal", 3, 0.6, 0.4).render("idle", sr=SR)
    m, _ = match(target, SR, ["mammal"], iters=3, screen=2, clap=clap, sr=SR)
    assert m.archetype == "mammal" and set(dict(m.genes)) <= set(gene_names("mammal"))


def test_pinned_genes_still_vary_per_individual():
    c = Creature("mammal", 1, genes={"f0": 0.5})
    pitches = {c.member(i).voice().syllables[0].pitch[0][1] for i in range(5)}
    assert len(pitches) > 1


def test_every_archetype_has_a_label():
    covered = set().union(*LABELS.values())
    from tare.tools.tune import ARCHETYPES
    assert covered == set(ARCHETYPES)
