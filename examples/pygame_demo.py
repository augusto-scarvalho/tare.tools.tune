"""Runtime use inside a Python game: press keys to make creatures call and things clash.

    pip install pygame
    python examples/pygame_demo.py

1-5: idle / alert / attack / hurt / death    T: talk    B: babble    TAB: next creature    SPACE: new random creature
Q: sword swing   W: sword clash   E: fireball   R: lightning   A: storm ambience on/off
"""
import pygame

from creaturesynth import CALLS, Creature, Sfx, to_pcm16
from creaturesynth.runtime import AmbiencePlayer, VoiceBank
from creaturesynth.speech.casting import cast

SR = 44_100
CREATURES = [
    Creature("mammal", species=7, size=0.45, aggression=0.5, name="wolf"),
    Creature("monster", species=13, size=0.9, aggression=0.8, name="ogre"),
    Creature("slime", species=3, size=0.4, name="slime"),
    Creature("chip", species=5, size=0.3, name="pixel pal"),
]
SWORD = Sfx("blade", "steel", species=3)
EFFECTS = {pygame.K_q: (SWORD, "swing"), pygame.K_w: (SWORD, "clash"),
           pygame.K_e: (Sfx("spell", "fire", power=0.8), "impact"), pygame.K_r: (Sfx("spell", "lightning"), "impact")}


def main():
    pygame.mixer.pre_init(SR, -16, 1)
    pygame.init()
    screen = pygame.display.set_mode((560, 170))
    font = pygame.font.SysFont(None, 26)
    bank = VoiceBank(sample_rate=SR, takes=4)
    for c in CREATURES:
        bank.warm(c)  # render in the background while the "level" loads
    for sfx, ev in EFFECTS.values():
        bank.warm(sfx, [ev])
    ambience, channel, clock = None, pygame.mixer.Channel(7), pygame.time.Clock()

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
                elif event.key in (pygame.K_t, pygame.K_b):  # talk (T) or babble (B) in a voice that fits its body
                    who = cast("creature", creature=CREATURES[index],
                               style="speech" if event.key == pygame.K_t else None)
                    audio = bank.line(who, "Olá, viajante! Cuidado com os lobos.", "pt", block=False)
                    if audio is not None:
                        pygame.mixer.Sound(buffer=to_pcm16(audio)).play()
                elif event.key in EFFECTS:
                    audio = bank.get(*EFFECTS[event.key], block=False)
                    if audio is not None:
                        pygame.mixer.Sound(buffer=to_pcm16(audio)).play()
                elif event.key == pygame.K_a:  # an endless storm: its loop plus thunder at random moments
                    if ambience:
                        ambience.close()
                        ambience = None
                        channel.stop()
                    else:
                        ambience = AmbiencePlayer(Sfx("ambience", "storm", power=0.6), SR, accents_per_minute=4)
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
        screen.blit(font.render("Q/W: sword  E: fireball  R: lightning  A: storm", True, "gray"), (16, 120))
        pygame.display.flip()
        if ambience and ambience.ready and channel.get_queue() is None:  # keep half a second queued
            chunk = pygame.mixer.Sound(buffer=to_pcm16(ambience.read(SR // 2)))
            channel.queue(chunk) if channel.get_busy() else channel.play(chunk)
        clock.tick(60)
    bank.close()
    if ambience:
        ambience.close()
    pygame.quit()


if __name__ == "__main__":
    main()
