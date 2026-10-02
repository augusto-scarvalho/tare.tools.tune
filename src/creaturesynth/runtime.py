"""In-game use from Python (pygame, pyglet, Arcade, Panda3D, Ren'Py...).

``VoiceBank`` renders calls in background threads, keeps a bounded cache and hands out a
different take each time so a creature never repeats the exact same sound twice in a row.

    bank = VoiceBank(takes=4)
    bank.warm(wolf)                       # e.g. while the level loads
    sound = pygame.mixer.Sound(buffer=to_pcm16(bank.get(wolf, "attack")))

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

    def _future(self, creature: Creature, call: str, take: int) -> Future:
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

    def warm(self, creature: Creature, calls: Iterable[str] | None = None) -> list[Future]:
        """Start rendering every take of the given calls in the background."""
        return [self._future(creature, call, t) for call in (calls or CALLS) for t in range(self.takes)]

    def ready(self, creature: Creature, call: str = "idle") -> bool:
        with self._lock:
            return any(f.done() for (c, k, _), f in self._cache.items() if c == creature and k == call)

    def get(self, creature: Creature, call: str = "idle", block: bool = True) -> np.ndarray | None:
        """A take of `call`, never the same one twice in a row.

        With ``block=False`` returns None instead of waiting when nothing is rendered yet
        (and keeps rendering in the background).
        """
        if call not in CALLS:
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

    def close(self):
        self._pool.shutdown(wait=False, cancel_futures=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
