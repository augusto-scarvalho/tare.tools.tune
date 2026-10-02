"""In-game use from Python (pygame, pyglet, Arcade, Panda3D, Ren'Py...).

``VoiceBank`` renders calls in background threads, keeps a bounded cache and hands out a
different take each time so a creature (or a sword, a spell...) never repeats the exact same
sound twice in a row. ``AmbiencePlayer`` streams a place endlessly: its seamless loop plus
accents (thunder, birds, drips) at random moments.

    bank = VoiceBank(takes=4)
    bank.warm(wolf)                       # e.g. while the level loads
    sound = pygame.mixer.Sound(buffer=to_pcm16(bank.get(wolf, "attack")))
    clash = bank.get(Sfx("blade", "steel", species=3), "clash")
    storm = AmbiencePlayer(Sfx("ambience", "storm"))
    chunk = storm.read(1024)              # feed it to your audio stream, forever

Engines that cannot run Python use the same specs through an engine-side renderer, or the
baked packs from ``creaturesynth.bake`` (see docs/arquitetura.md).
"""
import random
import threading
from collections import OrderedDict
from collections.abc import Iterable
from concurrent.futures import Future, ThreadPoolExecutor

import numpy as np

from .calls import CALLS
from .creature import Creature
from .render import DEFAULT_SR, render
from .sfx import Sfx


class VoiceBank:
    def __init__(self, sample_rate: int = DEFAULT_SR, takes: int = 4, workers: int = 2,
                 max_items: int = 512, seed: int | None = None):
        self.sample_rate = sample_rate
        self.takes = takes
        self.max_items = max_items
        self._pool = ThreadPoolExecutor(workers, thread_name_prefix="creaturesynth")
        self._cache: OrderedDict[tuple, Future] = OrderedDict()
        self._last: dict[tuple, int] = {}
        self._lock = threading.Lock()
        self._random = random.Random(seed)

    def _future(self, creature: "Creature | Sfx", call: str, take: int) -> Future:
        k = (creature, call, take)
        with self._lock:
            fut = self._cache.get(k)
            if fut is None:
                fut = self._pool.submit(lambda: render(creature.voice(call, take), self.sample_rate))
                self._cache[k] = fut
                while len(self._cache) > self.max_items:
                    self._cache.popitem(last=False)
            else:
                self._cache.move_to_end(k)
            return fut

    def warm(self, creature: "Creature | Sfx", calls: Iterable[str] | None = None) -> list[Future]:
        """Start rendering every take of the given calls (sound effects: events) in the background."""
        calls = calls or getattr(creature, "calls", CALLS)
        return [self._future(creature, call, t) for call in calls for t in range(self.takes)]

    def ready(self, creature: Creature, call: str = "idle") -> bool:
        with self._lock:
            return any(f.done() for key, f in self._cache.items() if key[:2] == (creature, call))

    def get(self, creature: Creature, call: str = "idle", block: bool = True) -> np.ndarray | None:
        """A take of `call`, never the same one twice in a row.

        With ``block=False`` returns None instead of waiting when nothing is rendered yet
        (and keeps rendering in the background).
        """
        if call not in getattr(creature, "calls", CALLS):
            raise ValueError(f"unknown call {call!r}")
        last = self._last.get((creature, call))
        options = [t for t in range(self.takes) if t != last] or [0]
        if not block:
            with self._lock:
                done = [t for t in options if (f := self._cache.get((creature, call, t))) and f.done()]
            if not done:
                self.warm(creature, [call])
                return None
            options = done
        take = self._random.choice(options)
        self._last[(creature, call)] = take
        return self._future(creature, call, take).result()

    def line(self, speaker, text: str, lang: str = "pt", block: bool = True) -> np.ndarray | None:
        """A spoken line (cached); with ``block=False`` returns None until it is ready.
        `speaker`: a Speaker or speech.casting.Cast (which also carries the babble style)."""
        k = ("line", speaker, text, lang)
        with self._lock:
            fut = self._cache.get(k)
            if fut is None:
                fut = self._pool.submit(lambda: speaker.render(text, lang, self.sample_rate))
                self._cache[k] = fut
                while len(self._cache) > self.max_items:
                    self._cache.popitem(last=False)
        if not block and not fut.done():
            return None
        return fut.result()

    def close(self):
        self._pool.shutdown(wait=False, cancel_futures=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class AmbiencePlayer:
    """An endless place: the scene's seamless loop, plus accents scattered in time, mixed block by block.

        player = AmbiencePlayer(Sfx("ambience", "forest"), accents_per_minute=6)
        player.add(Creature("bird", species=4), "alert", per_minute=2)     # anything with .voice(event, take)
        chunk = player.read(1024)            # float32; silence until the loop has rendered

    Accents are rendered in the background (a few takes each); one that is not ready when
    its moment comes is skipped, so reading never blocks.
    """

    def __init__(self, scene: Sfx, sample_rate: int = DEFAULT_SR, accents_per_minute: float = 4.0, takes: int = 4,
                 gain: float = 1.0, seed: int | None = None, workers: int = 2):
        self.scene, self.sample_rate, self.takes, self.gain = scene, sample_rate, takes, gain
        self._pool = ThreadPoolExecutor(workers, thread_name_prefix="creaturesynth-ambience")
        self._random = random.Random(seed)
        self._bed = self._pool.submit(lambda: render(scene.voice("loop"), sample_rate))
        self._pos = 0
        self._layers: list[dict] = []
        self._playing: list[list] = []          # [audio, position]
        self._time = 0
        if accents_per_minute and "accent" in scene.events:
            self.add(scene, "accent", accents_per_minute)

    def add(self, source, event: str, per_minute: float, gain: float = 1.0):
        """Scatter `source`'s `event` over the ambience, `per_minute` times on average."""
        takes = [self._pool.submit(lambda t=t: render(source.voice(event, t), self.sample_rate))
                 for t in range(self.takes)]
        self._layers.append({"takes": takes, "rate": per_minute / 60 / self.sample_rate, "gain": gain,
                             "next": self._wait(per_minute / 60 / self.sample_rate)})

    def _wait(self, rate: float) -> int:
        return int(self._random.expovariate(rate)) if rate > 0 else 1 << 62

    @property
    def ready(self) -> bool:
        return self._bed.done()

    def read(self, n: int) -> np.ndarray:
        out = np.zeros(n, np.float32)
        if not self._bed.done():
            return out
        bed = self._bed.result()
        idx = (self._pos + np.arange(n)) % len(bed)
        out += bed[idx] * self.gain
        self._pos = (self._pos + n) % len(bed)
        for layer in self._layers:
            while layer["next"] < self._time + n:
                offset = max(layer["next"] - self._time, 0)
                ready = [f for f in layer["takes"] if f.done()]
                if ready:
                    self._playing.append([self._random.choice(ready).result() * layer["gain"] * self.gain, -offset])
                layer["next"] += max(self._wait(layer["rate"]), 1)
        still = []
        for audio, pos in self._playing:
            a, b = max(pos, 0), min(pos + n, len(audio))
            if b > a:
                out[a - pos:b - pos] += audio[a:b]
            if pos + n < len(audio):
                still.append([audio, pos + n])
        self._playing = still
        self._time += n
        return np.tanh(out)          # soft limit: a thunderclap on top of the bed never clips

    def close(self):
        self._pool.shutdown(wait=False, cancel_futures=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
