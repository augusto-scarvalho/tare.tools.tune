"""Interface sounds: menus, a tactics game's grid and cursor, and the rhythm of its battles.

Measured on game UI sounds: a click lasts 8-170 ms, a tick or a soft thump; opening a bag is a 0.4-1 s rustle;
level up is a rising major arpeggio (notes 60-150 ms apart) ending on a long bright note with sparkle, 1.6-3.4 s;
quest complete climbs the chord more slowly (~0.2 s per note) and rests on the top note; an error is short (0.14-0.6 s)
and low (around D#3-A3), a buzz or two falling tones.

And on 200 CC0 interface sounds (Kenney's Interface Sounds, UI Audio and RPG Audio; analysis only):

    cursor tick    10-54 ms: a click with a harmonic ring (800 Hz x 3, 4, 5, 6, 7, 12) or a 3.6 kHz cluster
    hover          52-174 ms, soft, 600-1400 Hz
    select         34-186 ms, a bright struck tone at 1-3 kHz with its octave, falling a little
    confirm        280-500 ms: pure notes climbing by fifth and octave (1, 1.5, 2, 3) or third and octave, 60 ms each
    back           ~60 ms, low (110-260 Hz): a short "thup"
    question       three notes ~100 ms each, falling (G, F#, E) or rising
    scroll         ticks ~50 ms apart, cycling through a few pitches
    open, close    a pure tone gliding 10-13 semitones up or down in ~250 ms
    page flip      ~380 ms of rustle between 1.6 and 7 kHz
    glass          a near-pure ring (~2 kHz) beating against a partner 2-4 % above it

Four voices (styles): "fantasy" (struck steel: glockenspiel and chimes, cloth and paper), "crystal" (glass), "wood"
(marimba and wood blocks, soft) and "retro" (square-wave blips, like an 8-bit console). Each game its own key; each
take a hair different (a few cents, a dB, a few ms), so a cursor heard a hundred times a battle does not tire.
"""
from dataclasses import replace

from .. import rng
from ..instruments import INSTRUMENTS, glockenspiel, marimba
from ..score import Note
from ..spec import Modal, Noise, Scatter, Syllable
from . import Fx, bell_curve, decay_curve, recipe
from .physical import burst, paper, splits

BAR = (1.0, 2.756, 5.404, 8.933)   # a free bar's modes: glockenspiel, celesta
TACTICS = ("cursor", "hover", "target", "select", "confirm", "cancel", "scroll", "range", "text", "advance", "turn",
           "enemy_turn", "learn", "battle")


def hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def chime(start: float, midi: float, ring: float = 1.0, gain: float = 1.0) -> Modal:
    """A struck metal bar at a note."""
    return bar(start, hz(midi), ring, gain)


def bar(start: float, f: float, ring: float = 1.0, gain: float = 1.0) -> Modal:
    """A struck metal bar whose lowest mode is `f`."""
    modes = [(round(f * r, 1), round(ring * 1.2 / (1 + 1.5 * i), 4), round(1 / (1 + i) ** 0.6, 4))
             for i, r in enumerate(BAR) if f * r < 18000]
    return Modal(round(start, 4), round(ring * 1.4 + 0.1, 3), modes, [(0.0, 1.0, 0.0006)], hardness=12000,
                 click=0.02, gain=gain)


def blip(start: float, midi: float, dur: float, gain: float = 1.0, glide: float = 0.0) -> Syllable:
    """A square-wave note."""
    f = hz(midi)
    return Syllable(round(start, 4), round(dur, 4), [(0, round(f, 2)), (1, round(f * 2 ** (glide / 12), 2))], "pulse",
                    0.5, 0.7, attack=0.002, release=round(min(0.03, dur / 3), 4), gain=round(gain, 4))


def glass(n: Note) -> list:
    """Struck glass: a near-pure ring, beating against a partner 3 % above it, and a weak 2.26 overtone."""
    t1 = round(min(1.2 * (2000 / n.f) ** 0.5, 2.5), 3)
    return [Modal(round(n.start, 4), round(t1 + 0.05, 3),
                  [(round(n.f, 2), t1, 1.0), (round(n.f * 1.03, 2), round(0.8 * t1, 3), 0.55),
                   (round(n.f * 2.26, 2), round(0.35 * t1, 3), 0.22)],
                  [(0.0, 1.0, 0.0004)], hardness=14000, click=0.01, gain=round(n.vel, 4))]


VOICES = {"fantasy": glockenspiel, "crystal": glass, "wood": marimba}


def note(fx: Fx, start: float, midi: float, ring: float, vel: float = 0.8, name: str = "n") -> list:
    """A note in the style's voice, choked `ring` seconds after it is struck; each take a few cents and up to 1.5 dB
    off."""
    midi = midi + 0.2 * (fx.rand(name + "c") - 0.5)
    vel = min(vel * 10 ** (1.5 * (fx.rand(name + "v") - 0.5) / 20), 1.0)
    if fx.style == "retro":
        return [blip(start, midi, max(ring, 0.012), vel)]
    n = Note(round(start, 4), ring, hz(midi), vel, rng.key(fx.sfx.species, fx.take, fx.event, name))
    return [replace(x, damp=round(ring, 4), dur=round(min(x.dur, ring + 0.15), 3)) if isinstance(x, Modal) else x
            for x in VOICES[fx.style](n)]


def tick(fx: Fx, start: float, midi: float, gain: float = 1.0, name: str = "t") -> list:
    """The shortest sound there is: a click with a little ring (measured ticks: 10-54 ms)."""
    if fx.style == "retro":
        return [blip(start, midi + 0.3 * (fx.rand(name + "c") - 0.5), 0.018, gain)]
    f = hz(midi) * (1 + 0.012 * (fx.rand(name + "c") - 0.5))
    g = 10 ** (1.5 * (fx.rand(name + "v") - 0.5) / 20) * gain
    if fx.style == "wood":       # a wood block: two modes, gone in 40 ms
        modes, hardness = [(round(f, 1), 0.035, 1.0), (round(f * 2.7, 1), 0.02, 0.4)], 3500
    else:                        # a tiny metal or glass tick, ringing harmonically (measured: tick_002)
        modes = [(round(f * r, 1), 0.03 if r == 1 else 0.02, round(w * (0.8 + 0.4 * fx.rand(f"{name}{r}")), 3))
                 for r, w in ((1, 1.0), (3, 0.5), (4, 0.45), (5, 0.6), (7, 0.7))]
        hardness = 14000
    return [Modal(round(start, 4), 0.06, modes, [(0.0, 1.0, 0.0004)], hardness=hardness, click=0.3, gain=round(g, 4)),
            burst(round(start, 4), 0.006, 6000, round(0.25 * g, 4))]


def run(fx: Fx, start: float, base: float, steps, step: float, ring: float, last: float, vel=(0.7, 0.85)) -> list:
    """Notes up or down a figure, `step` seconds apart (each take a little faster or slower); the last one rings."""
    step *= 0.92 + 0.16 * fx.rand("step")
    out = []
    for i, d in enumerate(steps):
        end = i == len(steps) - 1
        out += note(fx, start + i * step, base + d, last if end else ring, vel[1] if end else vel[0], f"n{i}")
    return out


def sparkle(fx: Fx, start: float, dur: float, key: int, rate: float = 40) -> list:
    return [] if fx.style == "retro" else [Scatter(round(start, 4), round(dur, 3), [(0, rate), (1, 0)], "ping",
                                                   (hz(key + 24), hz(key + 36)), (0.04, 0.15), (0.2, 0.7), 0.4)]


def arpeggio(fx: Fx, notes: list, step: float, hold: float, retro: bool) -> list:
    out = []
    for k, n in enumerate(notes):
        last = k == len(notes) - 1
        if retro:
            out.append(blip(k * step, n, hold if last else step * 0.9, 0.8 if last else 0.6))
        else:
            out.append(chime(k * step, n, hold if last else 0.6, 1.0 if last else 0.7))
    return out


MENU = ("click", "open", "close", "levelup", "quest", "error")
RESULTS = ("critical", "miss", "damage", "heal", "mp", "ko", "revive")


def key_of(fx: Fx) -> int:
    """Each game its own key, near C5 (the same for every recipe of one species)."""
    return 72 + int(round(6 * (fx.g.base("key") - 0.5)))


@recipe("ui", MENU + TACTICS + RESULTS, ("fantasy", "retro", "crystal", "wood"))
def ui(fx: Fx):
    """Interface: menus, a tactics grid (cursor, hover, select, confirm, cancel, range, text), its battles' rhythm
    (turns, battle start, ability learned) and what each blow did (critical, miss, damage, heal, mp, ko, revive);
    level up, quest complete, error."""
    e = fx.event
    key = key_of(fx)
    if e in TACTICS:
        return tactics(fx, e, key)
    if e in RESULTS:
        return results(fx, e, key)
    if fx.style in ("crystal", "wood"):
        return menu(fx, e, key)
    retro = fx.style == "retro"
    if e == "click":
        if retro:
            return fx.voice(fx.level(0.5), syllables=[blip(0.0, key + 12, 0.025)])
        tick_ = Modal(0.0, 0.08, [(round(hz(key + 19) * (0.95 + 0.1 * fx.rand("t")), 1), 0.03, 1.0),
                                  (round(hz(key + 7), 1), 0.02, 0.4)], [(0.0, 1.0, 0.001)], hardness=6000, click=0.2)
        return fx.voice(fx.level(0.5), modal=[tick_])
    if e in ("open", "close"):
        if retro:
            notes = [key, key + 7] if e == "open" else [key + 7, key]
            return fx.voice(fx.level(0.6), syllables=[blip(0.0, notes[0], 0.05, 0.6), blip(0.05, notes[1], 0.08, 0.6)])
        dur = 0.45 if e == "open" else 0.3
        layers = [Noise(0.0, dur, [(0, 900), (1, 1400)], "band", 0.7, amp=bell_curve(0.35, 1.3), attack=0.02,
                        wobble=(22.0, 0.7), gain=0.8),
                  Scatter(0.0, dur, [(0, 60), (0.5, 90), (1, 0)], "pop", (800, 4000), (0.001, 0.004), (0.2, 1.0), 0.3),
                  Modal(round(dur * (0.8 if e == "open" else 0.9), 3), 0.25, [(2600, 0.05, 1.0), (4100, 0.04, 0.6)],
                        [(0.0, 1.0, 0.0006)], hardness=12000, click=0.1, gain=0.35)]   # a buckle
        return fx.voice(fx.level(0.6), **splits(layers))
    if e == "levelup":   # the major chord climbing, the top note held, sparkle
        notes = [key, key + 4, key + 7, key + 12, key + 16, key + 19]
        layers = arpeggio(fx, notes, 0.075, 1.6, retro)
        if retro:
            layers.append(blip(len(notes) * 0.075, key + 24, 0.5, 0.7, 0.0))
        else:
            layers.append(Scatter(0.3, 1.6, [(0, 40), (1, 0)], "ping", (hz(key + 24), hz(key + 36)), (0.04, 0.15),
                                  (0.2, 0.7), 0.5))
        return fx.voice(fx.level(0.8), **splits(layers))
    if e == "quest":     # slower, resting on the top note over its root
        notes = [key - 2, key + 2, key + 5, key + 10]
        layers = arpeggio(fx, notes, 0.2, 2.0, retro)
        if not retro:
            layers.append(Syllable(0.6, 1.8, [(0, hz(key - 14)), (1, hz(key - 14))], "sine", 0.5, 0.3,
                                   attack=0.15, release=0.6, gain=0.35))   # a soft root underneath
        return fx.voice(fx.level(0.8), **splits(layers))
    # error: two falling tones, low and buzzy (retro) or a dull knock under a low tone (fantasy)
    low = key - 27
    if retro:
        return fx.voice(fx.level(0.6), syllables=[blip(0.0, low + 3, 0.1, 0.8), blip(0.12, low, 0.18, 0.8)])
    knock = Modal(0.0, 0.3, [(180, 0.08, 1.0), (420, 0.05, 0.5), (760, 0.04, 0.3)], [(0.0, 1.0, 0.004),
                                                                                    (0.13, 0.8, 0.004)],
                  hardness=2500, click=0.0)
    tone = Syllable(0.0, 0.32, [(0, hz(low + 3)), (0.45, hz(low + 3)), (0.5, hz(low)), (1, hz(low))], "glottal",
                    0.5, 0.4, attack=0.01, release=0.08, gain=0.6)
    return fx.voice(fx.level(0.6), modal=[knock], syllables=[tone],
                    noise=[Noise(0.0, 0.3, [(0, 300), (1, 250)], "low", 0.8, amp=decay_curve(3), gain=0.2)])


def menu(fx: Fx, e: str, key: int):
    """The menu events in the crystal and wood voices."""
    crystal = fx.style == "crystal"
    if e == "click":
        return fx.voice(fx.level(0.5), **splits(tick(fx, 0.0, key + 12)))
    if e in ("open", "close"):
        if crystal:   # a pure tone gliding an octave (measured: maximize, minimize)
            lo, hi = hz(key + 7), hz(key + 19)
            curve = [(0, round(lo, 2)), (1, round(hi, 2))] if e == "open" else [(0, round(hi, 2)), (1, round(lo, 2))]
            glide = Syllable(0.0, 0.25, curve, "sine", 0.5, 0.0, attack=0.01, release=0.08, gain=0.6)
            return fx.voice(fx.level(0.55), **splits([glide] + note(fx, 0.22, key + (19 if e == "open" else 7),
                                                                    0.15, 0.4)))
        return fx.voice(fx.level(0.6), **splits(paper(fx, 0.3 if e == "open" else 0.22) +
                                                tick(fx, 0.28 if e == "open" else 0.2, key - 5, 0.6)))
    if e == "levelup":
        layers = run(fx, 0.0, key, (0, 4, 7, 12, 16, 19), 0.075, 0.5, 1.6) + sparkle(fx, 0.3, 1.6, key)
        return fx.voice(fx.level(0.8), **splits(layers))
    if e == "quest":
        return fx.voice(fx.level(0.8), **splits(run(fx, 0.0, key - 2, (0, 4, 7, 12), 0.2, 0.6, 2.0)))
    # error: two low notes falling a minor third, then a dull double knock under them
    layers = note(fx, 0.0, key - 21, 0.12, 0.9, "a") + note(fx, 0.12, key - 24, 0.2, 0.9, "b")
    return fx.voice(fx.level(0.6), **splits(layers + tick(fx, 0.0, key - 17, 0.5, "k")))


def tactics(fx: Fx, e: str, key: int):
    """A tactics game: the cursor on the grid, its menus and the rhythm of a battle."""
    if e == "cursor":           # tile to tile, dozens of times a turn: a tick around G5, never quite the same
        return fx.voice(fx.level(0.45), **splits(tick(fx, 0.0, key + 7)))
    if e == "scroll":           # down a list: smaller ticks cycling through four steps, take after take
        return fx.voice(fx.level(0.45), **splits(tick(fx, 0.0, key + 12 + (0, 2, 4, 2)[fx.take % 4], 0.8)))
    if e == "hover":            # a unit under the cursor: one soft note
        return fx.voice(fx.level(0.5), **splits(note(fx, 0.0, key + 7, 0.09, 0.5)))
    if e == "target":           # an enemy under it: a low note rubbing against the semitone above
        return fx.voice(fx.level(0.5), **splits(note(fx, 0.0, key - 5, 0.12, 0.6, "a") +
                                                note(fx, 0.008, key - 4, 0.12, 0.45, "b")))
    if e == "select":           # bright, with its octave, a little lower after
        return fx.voice(fx.level(0.55), **splits(note(fx, 0.0, key + 12, 0.11, 0.8, "a") +
                                                 note(fx, 0.0, key + 24, 0.06, 0.35, "b")))
    if e == "confirm":          # root, fifth, octave, twelfth, 60 ms apart
        return fx.voice(fx.level(0.6), **splits(run(fx, 0.0, key + 12, (0, 7, 12, 19), 0.06, 0.06, 0.3)))
    if e == "cancel":           # down a fourth, low and short
        return fx.voice(fx.level(0.5), **splits(note(fx, 0.0, key - 7, 0.05, 0.7, "a") +
                                                note(fx, 0.05, key - 12, 0.08, 0.8, "b")))
    if e == "range":            # the reach of a move shown on the ground: a soft pentatonic run, a shimmer
        layers = run(fx, 0.0, key + 7, (0, 2, 4, 7, 9, 12, 14, 16), 0.03, 0.12, 0.35, (0.35, 0.5))
        return fx.voice(fx.level(0.5), **splits(layers + sparkle(fx, 0.1, 0.4, key, 25)))
    if e == "text":             # one letter appearing: a 35 ms note on a pentatonic scale (size lowers the voice)
        step = (0, 2, 4, 7, 9, 12)[int(fx.rand("letter") * 6)]
        return fx.voice(fx.level(0.45), **splits(note(fx, 0.0, key + 12 - round(12 * fx.size) + step, 0.035, 0.5)))
    if e == "advance":          # the next page of a dialogue
        if fx.style in ("fantasy", "wood"):
            return fx.voice(fx.level(0.5), **splits(paper(fx, 0.22) + note(fx, 0.2, key + 12, 0.08, 0.35)))
        return fx.voice(fx.level(0.5), **splits(note(fx, 0.0, key + 12, 0.05, 0.5, "a") +
                                                note(fx, 0.05, key + 19, 0.12, 0.55, "b")))
    if e == "turn":             # a unit's turn: three notes up a major triad, ~0.1 s apart
        return fx.voice(fx.level(0.6), **splits(run(fx, 0.0, key, (0, 4, 7), 0.1, 0.1, 0.45)))
    if e == "enemy_turn":       # theirs: lower, falling a semitone, then a third
        return fx.voice(fx.level(0.6), **splits(run(fx, 0.0, key - 5, (3, 2, -2), 0.1, 0.1, 0.5)))
    if e == "learn":            # an ability learned, a class unlocked: up the chord to the twelfth, sparkle
        layers = run(fx, 0.0, key + 7, (0, 4, 7, 12, 16), 0.05, 0.15, 0.9, (0.6, 0.85)) + sparkle(fx, 0.2, 0.9, key)
        return fx.voice(fx.level(0.7), **splits(layers))
    return fx.voice(fx.level(0.8), **splits(battle(fx, key)))


def play(fx: Fx, instrument: str, start: float, midi: float, dur: float, vel: float, name: str,
         ring: float = 0.0) -> list:
    """A note of one of the measured instruments; struck ones choked after `ring` seconds if given."""
    n = Note(round(start, 4), dur, hz(midi), vel, rng.key(fx.sfx.species, fx.take, fx.event, name))
    return [replace(x, damp=round(ring, 4), dur=round(min(x.dur, ring + 0.15), 3)) if ring and isinstance(x, Modal)
            else x for x in INSTRUMENTS[instrument](n)]


def battle(fx: Fx, key: int) -> list:
    """Battle start, ~1.6 s: a roll swelling for 0.6 s, then a chord struck over a low hit."""
    roll = {"fantasy": "snare", "crystal": "triangle", "wood": "hand_drum", "retro": "chip_snare"}[fx.style]
    low = {"fantasy": "timpani", "crystal": "tubular_bell", "wood": "log_drum", "retro": "chip_bass"}[fx.style]
    chord = {"fantasy": "trumpet", "crystal": "celesta", "wood": "marimba", "retro": "square"}[fx.style]
    out = []
    for i in range(12):                                   # the roll, louder and louder
        out += play(fx, roll, i * 0.05, key + 12, 0.05, round(0.3 + 0.5 * i / 11, 3), f"r{i}", 0.12)
    hit = 0.62 + 0.03 * fx.rand("hit")
    out += play(fx, low, hit, key - 24, 0.9, 0.95, "low", 1.3)
    for i, d in enumerate((0, 4, 7, 12)):                 # the chord, fifth and octave over the root
        out += play(fx, chord, hit + 0.01 * i, key - 12 + d, 0.8, 0.85, f"c{i}", 1.2)
    if fx.style == "fantasy":                             # horns under the trumpets
        out += play(fx, "horn", hit, key - 17, 0.8, 0.8, "horn")
    return out + sparkle(fx, hit, 0.8, key, 20)


def results(fx: Fx, e: str, key: int):
    """What a blow did, laid over the weapon or the spell. Measured: retro hits last 40-110 ms, noisy, low and falling;
    a critical rushes up (Tactics Ogre: ~38 semitones in 0.67 s); a miss is two short tones, the second lower (Tactics
    Ogre, FFTA2: ~0.17 s); a heal swells for 0.25 s into a shimmer climbing from 5 to 13 kHz; a revive climbs ~17
    semitones through seconds of sparkle; a fall drops 10-37 semitones."""
    retro = fx.style == "retro"
    if e == "critical":         # a rush up (Tactics Ogre's: ~38 semitones in 0.67 s, mostly bright noise), landing on
        if retro:               # the voice's double octave and its fifth
            layers = [Noise(0.0, 0.08, [(0, 3000), (1, 1500)], "high", 0.7, amp=decay_curve(5), attack=0.001,
                            release=0.01, gain=0.8),
                      Syllable(0.0, 0.3, [(0, round(hz(key - 12), 2)), (1, round(hz(key + 26), 2))], "pulse", 0.25,
                               0.8, attack=0.002, release=0.02, gain=0.7), blip(0.3, key + 24, 0.12, 0.7)]
        else:
            layers = ([Noise(0.0, 0.5, [(0, 600), (0.7, 9000), (1, 7000)], "band", 2.0, amp=bell_curve(0.65, 1.5),
                             attack=0.01, release=0.05, wobble=(30.0, 0.4), gain=1.0)] +
                      note(fx, 0.3, key + 24, 0.3, 0.5, "a") + note(fx, 0.3, key + 31, 0.25, 0.35, "b") +
                      sparkle(fx, 0.3, 0.4, key, 60))
        return fx.voice(fx.level(0.8), **splits(layers))
    if e == "miss":             # not the air (the swing carries that): two short notes, the second lower, ~0.17 s
        layers = note(fx, 0.0, key + 7, 0.05, 0.5, "a") + note(fx, 0.08, key + 2, 0.06, 0.7, "b")
        return fx.voice(fx.level(0.5), **splits(layers))
    if e == "damage":           # the number popping up: a short thump under a low tick
        thump = Noise(0.0, 0.09, [(0, 600), (1, 160)], "low", 0.9, amp=decay_curve(5), attack=0.001, release=0.01,
                      gain=0.9)
        top = [blip(0.0, key - 5, 0.06, 0.6, -7)] if retro else tick(fx, 0.0, key - 5, 0.7)
        return fx.voice(fx.level(0.55), **splits([thump] + top))
    if e in ("heal", "mp"):     # up the chord into a shimmer that climbs; mana is cooler, a fifth lower, slower
        steps, base = ((0, 4, 7, 12), key + 12) if e == "heal" else ((0, 7, 12, 19), key + 7)
        layers = run(fx, 0.0, base, steps, 0.06 if e == "heal" else 0.08, 0.15, 0.6, (0.4, 0.55))
        if retro:
            layers += [blip(0.3 + 0.05 * k, base + (12, 19)[k % 2], 0.045, 0.4) for k in range(6)]
        else:
            lo, hi = (6000, 11000) if e == "heal" else (3000, 6000)
            layers += [Noise(0.0, 0.9, [(0, lo), (1, hi)], "band", 1.2, amp=bell_curve(0.28, 1.5), attack=0.01,
                             release=0.1, wobble=(30.0 if e == "heal" else 8.0, 0.6), gain=0.35),
                       Scatter(0.05, 0.9, [(0, 20), (0.25, 70), (1, 0)], "ping", (round(lo * 1.2), round(hi * 1.1)),
                               (0.03, 0.12), (0.2, 0.8), 0.45)]
        return fx.voice(fx.level(0.6), **splits(layers))
    if e == "ko":               # down: three notes, a tone sinking an octave and a half
        layers = run(fx, 0.0, key, (0, -5, -12), 0.12, 0.12, 0.5, (0.6, 0.7))
        layers.append(Syllable(0.1, 0.9, [(0, round(hz(key - 12), 2)), (1, round(hz(key - 30), 2))],
                               "pulse" if retro else "sine", 0.5, 0.3, attack=0.02, release=0.4, amp=decay_curve(2),
                               gain=0.5))
        return fx.voice(fx.level(0.6), **splits(layers))
    # revive: up two octaves of the chord, ~0.11 s a note, through a sparkle that thickens, a soft chord swelling under
    layers = run(fx, 0.0, key, (0, 4, 7, 12, 16, 19, 24), 0.11, 0.25, 1.4, (0.55, 0.8))
    if retro:
        layers += [blip(0.77 + 0.05 * k, key + (24, 28, 31)[k % 3], 0.045, 0.4) for k in range(12)]
    else:
        layers += [Scatter(0.0, 2.2, [(0, 10), (0.6, 60), (1, 0)], "ping", (round(hz(key + 24)), round(hz(key + 38))),
                           (0.04, 0.15), (0.2, 0.7), 0.5)]
        layers += [Syllable(0.1, 2.0, [(0, round(hz(key - 12 + d), 2)), (1, round(hz(key - 12 + d), 2))], "sine",
                            attack=0.6, release=0.8, gain=0.25) for d in (0, 4, 7)]
    return fx.voice(fx.level(0.75), **splits(layers))
