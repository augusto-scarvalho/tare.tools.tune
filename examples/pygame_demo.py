"""Runtime use inside a Python game: press keys to make creatures call.

    pip install pygame
    python examples/pygame_demo.py

1-5: idle / alert / attack / hurt / death    T: talk    TAB: next creature    SPACE: new random creature
"""
import pygame

from creaturesynth import CALLS, Creature, to_pcm16
from creaturesynth.runtime import VoiceBank
from creaturesynth.speech import Speaker

SR = 44_100
CREATURES = [
    Creature("mammal", species=7, size=0.45, aggression=0.5, name="wolf"),
    Creature("monster", species=13, size=0.9, aggression=0.8, name="ogre"),
    Creature("slime", species=3, size=0.4, name="slime"),
    Creature("chip", species=5, size=0.3, name="pixel pal"),
]


def main():
    pygame.mixer.pre_init(SR, -16, 1)
    pygame.init()
    screen = pygame.display.set_mode((560, 160))
    font = pygame.font.SysFont(None, 26)
    bank = VoiceBank(sample_rate=SR, takes=4)
    for c in CREATURES:
        bank.warm(c)  # render in the background while the "level" loads

    index, seed, calls, running = 0, 100, list(CALLS), True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_TAB:
                    index = (index + 1) % len(CREATURES)
                elif event.key == pygame.K_SPACE:
                    seed += 1
                    CREATURES[index] = Creature.random(seed)
                    bank.warm(CREATURES[index])
                elif event.key == pygame.K_t:  # the creature talks, in a voice that fits its body
                    speaker = Speaker.from_creature(CREATURES[index])
                    audio = bank.line(speaker, "Olá, viajante! Cuidado com os lobos.", "pt", block=False)
                    if audio is not None:
                        pygame.mixer.Sound(buffer=to_pcm16(audio)).play()
                elif pygame.K_1 <= event.key <= pygame.K_5:
                    audio = bank.get(CREATURES[index], calls[event.key - pygame.K_1], block=False)
                    if audio is not None:  # still rendering: skip rather than stall the frame
                        pygame.mixer.Sound(buffer=to_pcm16(audio)).play()
        c = CREATURES[index]
        screen.fill((24, 24, 32))
        label = c.name or f"{c.archetype} #{c.species}"
        screen.blit(font.render(f"{label}  (size {c.size:.2f}, aggression {c.aggression:.2f})", True, "white"),
                    (16, 40))
        screen.blit(font.render("1-5: " + " / ".join(calls) + "   T: talk   TAB / SPACE", True, "gray"), (16, 90))
        pygame.display.flip()
        pygame.time.wait(16)
    bank.close()
    pygame.quit()


if __name__ == "__main__":
    main()
