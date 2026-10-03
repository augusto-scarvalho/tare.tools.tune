"""Status effects of a tactics battle: stats raised and lowered, wards, time bent, the ailments and their cure.

Measured on RPG heal and buff sounds (leohpaz's "8 Heals and Buffs SFX", CC-BY 4.0; the RPG packs of artisticdude,
CC0, and of Reemax, CC-BY 3.0; Juhani Junkala's 512 retro sounds, CC0; analysis only):

    buff        a sweep up an octave in 0.15 s, then one pure ring (~3 kHz) fading over 1.5 s
    debuff      a low voice falling from ~180 to ~75 Hz in 0.25 s, then wavering there, fading over 2 s
    protect     three low throbs ~0.75 s apart under a steady ring near 1.2 kHz
    sleep       a high, still tone (~4.3 kHz) over notes falling slowly (~0.25 s each, 1.9 -> 0.9 kHz), 2 s
    haste       a voice climbing ~10 semitones over 2.4 s, pulsing
    retro       power-ups: 0.2-0.8 s, square waves sweeping up 8-18 semitones (some 44), held level, then cut;
                the negative ones fall as far

The ailments with no recording keep to what the classics made of them: poison bubbles, sleep sighs, silence is cut
short, confusion wobbles and tweets, charm beats like a heart, berserk growls, doom tolls, stone grinds and sets, a
toad croaks, a zombie groans. Tactics battles are fast, so everything is shorter than the references (0.5-2.5 s).

Two voices: "fantasy" (bells, glass, voices, air) and "retro" (square waves). The key is the game's, as in `ui`.
"""
from ..archetypes import VOWELS
from ..score import Note
from ..spec import Noise, Scatter, Syllable
from . import Fx, bell_curve, decay_curve, recipe
from .magic import boom
from .physical import burst, splits
from .ui import blip, glass, hz, key_of, note, play, run, sparkle, tick

EVENTS = ("buff", "debuff", "protect", "shell", "haste", "slow", "stop", "sleep", "poison", "silence", "blind",
          "confuse", "charm", "berserk", "doom", "stone", "toad", "zombie", "cure")


def sine(start, dur, f0, f1, gain, attack=0.02, release=0.1, **kw) -> Syllable:
    return Syllable(round(start, 4), round(dur, 4), [(0, round(f0, 2)), (1, round(f1, 2))], "sine", attack=attack,
                    release=release, gain=gain, **kw)


def sweep(start, dur, a, b, gain=0.7, **kw) -> Syllable:
    """A square wave gliding from note `a` to note `b`."""
    return Syllable(round(start, 4), round(dur, 4), [(0, round(hz(a), 2)), (1, round(hz(b), 2))], "pulse", 0.5, 0.7,
                    attack=0.002, release=0.03, gain=gain, **kw)


def ring(fx: Fx, start, midi, vel=0.6, name="g") -> list:
    """A struck glass, ringing as long as glass does."""
    return glass(Note(round(start, 4), 1.0, hz(midi + 0.2 * (fx.rand(name) - 0.5)), vel, 0))


def ticks(fx: Fx, start, first, ratio, until, a, b) -> list:
    """Clock ticks whose gap starts at `first` and is multiplied by `ratio` each time, pitch moving from `a` to `b`."""
    out, t, gap, k = [], start, first, 0
    while t < until:
        midi = a + (b - a) * (t - start) / (until - start)
        out += [blip(t, midi, 0.02, 0.6)] if fx.style == "retro" else tick(fx, t, midi, 0.7, f"t{k}")
        t, gap, k = t + gap, max(gap * ratio, 0.035), k + 1     # never closer than 35 ms, so it ends
    return out


@recipe("status", EVENTS, ("fantasy", "retro"))
def status(fx: Fx):
    """Status effects: buff, debuff, protect, shell, haste, slow, stop, the ailments (sleep, poison, silence, blind,
    confuse, charm, berserk, doom, stone, toad, zombie) and their cure."""
    e, key, retro = fx.event, key_of(fx), fx.style == "retro"
    extra = {}
    if e == "buff":             # up an octave in 0.15 s, the chord, one pure ring ~3 kHz
        if retro:
            layers = run(fx, 0.0, key, (0, 4, 7, 12), 0.05, 0.05, 0.05) + [sweep(0.2, 0.3, key + 12, key + 24,
                                                                                  vibrato=(9.0, 0.3))]
        else:
            layers = ([sine(0.0, 0.18, hz(key - 12), hz(key), 0.45, release=0.04)] +
                      run(fx, 0.12, key + 12, (0, 4, 7, 12), 0.05, 0.2, 1.0, (0.45, 0.6)) +
                      ring(fx, 0.3, key + 31, 0.5) + sparkle(fx, 0.25, 1.0, key, 30))
        level = 0.7
    elif e == "debuff":         # a low voice falling from ~180 to ~80 Hz and wavering there; the bells down a dim chord
        if retro:
            layers = [sweep(0.0, 0.5, key + 7, key - 17, vibrato=(8.0, 0.8)), blip(0.5, key - 17, 0.12, 0.5)]
        else:
            layers = [Syllable(0.0, 1.4, [(0, round(hz(key - 18), 2)), (0.15, round(hz(key - 31), 2)),
                                          (1, round(hz(key - 32), 2))], "glottal", brightness=0.3, vibrato=(5.5, 1.2),
                               rough=(0.4, 6.0), formants=[(450, 200, 1.0), (900, 300, 0.4)], attack=0.01,
                               release=0.6, amp=decay_curve(1.5), gain=0.8)]
            layers += run(fx, 0.05, key - 12, (0, -3, -6, -9), 0.12, 0.2, 0.7, (0.25, 0.3))   # the voice leads
        level = 0.7
    elif e == "protect":        # three low throbs under a steady ring near 1.2 kHz
        if retro:
            layers = [blip(0.2 * k, key - 12, 0.08, 0.7) for k in range(3)] + [
                sweep(0.0, 0.8, key + 15, key + 15, 0.35, vibrato=(7.0, 0.2))]
        else:
            layers = [boom(0.35 * k, 0.35, 160, 1.0 - 0.1 * k) for k in range(3)]     # each throb 10 dB over the ring
            layers += note(fx, 0.0, key + 15, 1.2, 0.1) + [sine(0.0, 1.4, hz(key + 15), hz(key + 15), 0.07,
                                                                attack=0.3, release=0.6, pulses=(2.9, 0.4, 2.0))]
        level = 0.65
    elif e == "shell":          # magic's ward: glass up the chord, a rush of air, a high tone shimmering
        if retro:
            layers = [blip(0.04 * k, key + (19, 24)[k % 2], 0.04, 0.5) for k in range(14)]
        else:
            layers = [x for k, d in enumerate((12, 19, 24)) for x in ring(fx, 0.08 * k, key + d, 0.5, f"g{k}")]
            layers += [Noise(0.0, 0.9, [(0, 3000), (1, 6000)], "band", 0.9, amp=bell_curve(0.4, 1.5), attack=0.02,
                             release=0.1, wobble=(12.0, 0.5), gain=0.35),
                       sine(0.1, 1.1, hz(key + 24), hz(key + 24), 0.2, attack=0.2, release=0.5, vibrato=(5.0, 0.15))]
        level = 0.6
    elif e == "haste":          # a clock speeding up and climbing, then a bright note
        layers = ticks(fx, 0.0, 0.15, 0.82, 0.9, key + 12, key + 24)
        if retro:
            layers.append(sweep(0.0, 0.9, key, key + 12, 0.35))
            layers.append(blip(0.95, key + 24, 0.15, 0.6))
        else:
            layers += [sine(0.0, 0.9, hz(key), hz(key + 12), 0.35, attack=0.4, release=0.05)]
            layers += note(fx, 0.95, key + 19, 0.5, 0.7)
        level = 0.65
    elif e == "slow":           # a clock running down, falling, then a low note
        layers = ticks(fx, 0.0, 0.04, 1.25, 1.1, key + 19, key + 5)
        if retro:
            layers += [sweep(0.0, 1.0, key + 7, key - 5, 0.3), blip(1.15, key - 5, 0.2, 0.6)]
        else:
            layers += [sine(0.0, 1.0, hz(key + 7), hz(key - 5), 0.3, attack=0.05, release=0.3)]
            layers += note(fx, 1.15, key - 5, 0.6, 0.7)
        level = 0.6
    elif e == "stop":           # tick, tock... then frozen: glass and a crack of ice, nothing moving after
        layers = []
        for k in range(5):
            midi = key + (12 if k % 2 == 0 else 7)
            layers += [blip(0.09 * k, midi, 0.02, 0.6)] if retro else tick(fx, 0.09 * k, midi, 0.7, f"t{k}")
        if retro:
            layers.append(blip(0.5, key + 24, 0.4, 0.7))
        else:
            layers += ring(fx, 0.5, key + 24, 0.8, "a") + ring(fx, 0.5, key + 31, 0.5, "b")
            layers += [burst(0.5, 0.05, 6000, 0.5),
                       Noise(0.3, 0.2, [(0, 2000), (1, 8000)], "band", 0.8, amp=[(0, 0.0), (1, 1.0)], attack=0.01,
                             release=0.002, gain=0.4)]
        level = 0.65
    elif e == "sleep":          # notes falling slowly over a high, still tone, then a sigh
        layers = run(fx, 0.0, key + 7, (12, 9, 5, 0), 0.27, 0.4, 0.9, (0.35, 0.45))
        if not retro:
            layers += [sine(0.0, 1.6, hz(key + 36), hz(key + 36), 0.25, attack=0.2, release=0.8),
                       Noise(1.0, 0.8, [(0, 1400), (1, 900)], "band", 1.0, amp=bell_curve(0.35, 1.5), attack=0.05,
                             release=0.2, wobble=(6.0, 0.3), gain=0.25)]
        level = 0.55
    elif e == "poison":         # bubbles, and a sickly tone beating against itself, sinking
        if retro:
            layers = [blip(0.13 * k + 0.04 * fx.rand(f"b{k}"), key - 12 + int(7 * fx.rand(f"p{k}")), 0.05, 0.6, 5)
                      for k in range(7)] + [sweep(0.0, 0.9, key - 5, key - 8, 0.25, vibrato=(5.0, 0.5))]
        else:
            layers = [Scatter(0.0, 1.0, [(0, 30), (0.6, 20), (1, 0)], "drop", (300, 900), (0.01, 0.04), (0.3, 1.0),
                              0.7),
                      sine(0.05, 0.9, hz(key - 5), hz(key - 7), 0.35, attack=0.1, release=0.4),
                      sine(0.05, 0.9, hz(key - 5) * 1.03, hz(key - 7) * 1.03, 0.3, attack=0.1, release=0.4),
                      Noise(0.0, 0.8, [(0, 350), (1, 300)], "band", 1.5, "brown", attack=0.05, release=0.3,
                            wobble=(8.0, 0.8), gain=0.4)]
        level = 0.6
    elif e == "silence":        # "shh", muffled at the end, a dull thump
        if retro:
            layers = [Noise(0.0, 0.25, [(0, 5000), (0.7, 4500), (1, 400)], "band", 0.8, amp=bell_curve(0.5, 1.5),
                            attack=0.01, release=0.01, gain=0.6), blip(0.28, key - 12, 0.08, 0.6)]
        else:
            layers = [Noise(0.0, 0.35, [(0, 5000), (0.7, 4500), (1, 400)], "band", 0.8, amp=bell_curve(0.55, 1.5),
                            attack=0.02, release=0.01, gain=0.7)] + tick(fx, 0.33, key - 17, 0.6)
            layers += note(fx, 0.33, key - 7, 0.05, 0.4)
        level = 0.5
    elif e == "blind":          # the light going out: air darkening from 4.5 kHz to 250 Hz, a knock, a semitone down
        layers = [Noise(0.0, 0.7, [(0, 4500), (1, 250)], "band", 1.0, amp=bell_curve(0.2, 1.5), attack=0.01,
                        release=0.1, gain=0.8)]
        layers += [blip(0.3, key - 12, 0.12, 0.5), blip(0.42, key - 13, 0.25, 0.5)] if retro else (
            [boom(0.25, 0.5, 90, 0.5)] + note(fx, 0.3, key - 12, 0.15, 0.45, "a") +
            note(fx, 0.45, key - 13, 0.4, 0.45, "b"))
        level = 0.6
    elif e == "confuse":        # dizzy: two tones wobbling wide around each other, birds circling
        if retro:
            layers = [Syllable(0.0, 1.0, [(0, round(hz(key + 12), 2)), (1, round(hz(key + 12), 2))], "pulse", 0.5,
                               0.7, vibrato=(7.0, 2.5), attack=0.01, release=0.1, gain=0.6)]
            layers += [blip(0.15 + 0.22 * k, key + 24 + 3 * (k % 2), 0.04, 0.4, 5) for k in range(4)]
        else:
            layers = [sine(0.0, 1.1, hz(key + 12), hz(key + 12), 0.4, attack=0.1, release=0.3, vibrato=(7.0, 2.5)),
                      sine(0.05, 1.05, hz(key + 16), hz(key + 16), 0.3, attack=0.1, release=0.3, vibrato=(6.0, 2.5)),
                      Scatter(0.0, 1.0, [(0, 9), (1, 9)], "drop", (round(hz(key + 24)), round(hz(key + 31))),
                              (0.02, 0.05), (0.3, 1.0), 0.5)]
        level = 0.55
    elif e == "charm":          # a heartbeat, then up a sweet sixth, trembling
        beats = [blip(0.0, key - 12, 0.06, 0.6), blip(0.16, key - 12, 0.08, 0.5)] if retro else [
            boom(0.0, 0.15, 120, 0.7), boom(0.16, 0.2, 110, 0.6)]
        top = [sweep(0.3, 0.12, key + 12, key + 12, 0.5), sweep(0.42, 0.5, key + 21, key + 21, 0.6,
                                                                 vibrato=(6.0, 0.4))] if retro else (
            note(fx, 0.3, key + 12, 0.3, 0.6, "a") + note(fx, 0.42, key + 21, 0.9, 0.7, "b") +
            [sine(0.42, 0.9, hz(key + 21), hz(key + 21), 0.2, attack=0.15, release=0.4, vibrato=(6.0, 0.25))] +
            sparkle(fx, 0.4, 0.8, key, 25))
        layers = beats + top
        level = 0.6
    elif e == "berserk":        # a growl rising into a snarl, driven hard
        if retro:
            layers = [sweep(0.0, 0.6, key - 12, key + 12, 0.7), Noise(0.0, 0.6, [(0, 800), (1, 2500)], "band", 0.8,
                                                                      amp=[(0, 0.3), (1, 1.0)], attack=0.01,
                                                                      release=0.05, gain=0.4)]
            extra = {"crush": 0.3}
        else:
            layers = [Syllable(0.0, 0.9, [(0, round(hz(key - 28), 2)), (1, round(hz(key - 24), 2))], "glottal",
                               brightness=0.6, rough=(0.7, 28.0), sub=0.5, breath=0.2,
                               formants=[(500, 200, 1.0), (1100, 300, 0.5)], attack=0.05, release=0.2, gain=0.8),
                      Syllable(0.1, 0.8, [(0, round(hz(key - 12), 2)), (1, round(hz(key + 12), 2))], "glottal",
                               brightness=0.9, attack=0.2, release=0.1, gain=0.5)]
            extra = {"drive": 2.5}
        level = 0.7
    elif e == "doom":           # a bell tolls, low; the count begins
        if retro:
            layers = [blip(0.0, key - 12, 0.3, 0.7), blip(0.45, key - 12, 0.3, 0.6), blip(0.9, key - 24, 0.6, 0.7)]
        else:
            layers = play(fx, "tubular_bell", 0.0, key - 12, 2.5, 0.9, "toll", 2.2)
            layers.append(sine(0.0, 2.5, hz(key - 36), hz(key - 36), 0.25, attack=0.5, release=1.0))
            extra = {"space": 2.0, "wet": 0.3}
        level = 0.7
    elif e == "stone":          # grinding faster and faster, then set hard
        if retro:
            layers = [Noise(0.0, 0.8, [(0, 400), (1, 1500)], "band", 0.7, amp=[(0, 0.2), (1, 1.0)], attack=0.01,
                            release=0.01, gain=0.6)]
            layers += [blip(0.1 * k, key - 5 - 2 * k, 0.05, 0.5) for k in range(7)] + [blip(0.8, key - 24, 0.2, 0.8)]
        else:
            layers = [Scatter(0.0, 0.9, [(0, 20), (0.8, 250), (1, 0)], "pop", (200, 1500), (0.001, 0.006), (0.2, 1.0),
                              0.7),
                      Noise(0.0, 0.9, [(0, 150), (1, 400)], "band", 0.8, "brown", amp=[(0, 0.1), (1, 1.0)],
                            attack=0.05, release=0.02, gain=0.5),
                      fx.strike("stone", start=0.85, size=0.6, gain=0.9), boom(0.85, 0.3, 120, 0.6)]
        level = 0.7
    elif e == "toad":           # a puff, then a croak, twice
        if retro:
            layers = [Noise(0.0, 0.1, [(0, 2000), (1, 1000)], "band", 0.8, amp=decay_curve(4), attack=0.001,
                            gain=0.5)]
            layers += [sweep(0.15 + 0.3 * k, 0.2, key - 17, key - 19, 0.7, pulses=(30.0, 0.8, 2.0)) for k in range(2)]
        else:
            layers = [burst(0.0, 0.15, 1500, 0.5, "band")]
            croak = [(0, round(hz(key - 17), 2)), (1, round(hz(key - 19), 2))]
            layers += [Syllable(round(0.2 + 0.3 * k, 3), 0.22, croak, "pulse", 0.3, 0.5, pulses=(32.0, 0.9, 2.0),
                                formants=[(400, 150, 1.0), (1300, 250, 0.4)], attack=0.01, release=0.05, gain=0.8)
                       for k in range(2)]
        level = 0.6
    elif e == "zombie":         # a groan, wavering and sinking
        if retro:
            layers = [Syllable(0.0, 1.0, [(0, round(hz(key - 17), 2)), (0.3, round(hz(key - 15), 2)),
                                          (1, round(hz(key - 22), 2))], "pulse", 0.3, 0.5, vibrato=(4.0, 0.6),
                               attack=0.05, release=0.3, gain=0.7)]
        else:
            layers = [Syllable(0.0, 1.3, [(0, round(hz(key - 26), 2)), (0.3, round(hz(key - 24), 2)),
                                          (1, round(hz(key - 30), 2))], "glottal", brightness=0.35, jitter=0.4,
                               breath=0.5, rough=(0.3, 20.0),
                               formants=[(f, bw, g) for f, bw, g in zip(VOWELS["o"], (90, 110, 160, 250),
                                                                         (1.0, 0.6, 0.3, 0.15), strict=True)],
                               attack=0.15, release=0.4, gain=0.8),
                      sine(0.0, 1.3, hz(key - 36), hz(key - 38), 0.2, attack=0.3, release=0.5)]
        level = 0.65
    else:                       # cure: a bright sweep up, the chord chiming, a short sparkle
        if retro:
            layers = run(fx, 0.0, key + 12, (0, 4, 7, 12, 16, 19, 24), 0.035, 0.035, 0.2)
        else:
            layers = ([sine(0.0, 0.2, hz(key), hz(key + 24), 0.35, release=0.05)] +
                      run(fx, 0.15, key + 12, (0, 4, 7, 12), 0.03, 0.3, 0.8, (0.5, 0.6)) +
                      sparkle(fx, 0.15, 0.6, key, 40))
        level = 0.65
    return fx.voice(fx.level(level), **splits(layers), **extra)
