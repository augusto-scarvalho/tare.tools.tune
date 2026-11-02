# Tactical RPG sounds

[Documentation index](README.md) · [Project README](../README.md) · [Português brasileiro (alternative)](pt-BR/sons-tactics.md)

What a tactical RPG in the spirit of Final Fantasy Tactics, FFTA, FFTA2, Tactics Ogre, Unicorn Overlord, and Triangle Strategy needs, what tare.tools.tune already does, and what is missing. Each new sound follows the method in [RPG sounds](rpg-sounds.md): measure real recordings, model, listen in context, integrate.

**Current status:**

- **Available:** already generated, with the recipe shown in backticks;
- **Measured:** built from measured recordings; listening review and approval pending;
- **Designed:** built without reference recordings, based on the classics; listening review and approval pending;
- **Partial:** something similar exists, but it is not the right sound;
- **Missing:** not implemented yet.

**Priority:** how often the player hears the sound.

- **A:** every action;
- **B:** every battle;
- **C:** occasionally.

Abbreviations: FFT, FFTA (includes FFTA2), TO (Tactics Ogre), UO (Unicorn Overlord), TS (Triangle Strategy), OT (Octopath Traveler).

**Era.** Every sound can use three eras (`Sfx(..., era=...)`), measured in the games themselves: `hd` (TS, OT), `16bit` (TO, FFTA2), or the original design. The 8-bit sound is the `retro` style. With `dry=True`, sound has no room or tail, allowing the game to apply each map's reverb.

**Knobs.** Within each sound, `knobs` vary register, tempo, length, ring, brightness, sparkle, and the game's key (`tare.tools.tune sounds --knobs`).

## 1. Grid and menus

The most frequently heard sounds in a tactical RPG: the cursor crosses dozens of tiles every turn, so variations must be subtle enough to avoid fatigue. All four `ui` timbres (fantasy, crystal, wood, retro) were approved by ear; the game's creator chooses among them.

| Sound | Games | Current status | Priority |
|---|---|---|---|
| Cursor moving between tiles | all | available: `ui` cursor | A |
| Cursor over a unit (ally, enemy) | all | available: `ui` hover, target | A |
| Select unit, confirm, cancel | all | available: `ui` select, confirm, cancel | A |
| Impossible action (out of range, insufficient MP) | all | available: `ui` error | A |
| Open and close menu, scroll list, switch tab | all | available: `ui` open, close, scroll | A |
| Show movement or attack range on the ground | all | available: `ui` range | A |
| Text appearing letter by letter, colored by the speaker's voice | FFTA, TO | available: `ui` text (`size` deepens the voice); `animalese` babbling | A |
| Advance dialogue | all | available: `ui` advance | A |
| Choose the unit's facing direction | FFT, FFTA, TO | missing | B |
| Buy and sell, equip, change class | all | partial: `item` coins, letter, `gear` equip | B |
| Save and load | all | missing | C |

## 2. Battle pacing

| Sound | Games | Current status | Priority |
|---|---|---|---|
| Player, enemy, or ally phase/turn | FFTA, TO, UO, TS | available: `ui` turn, enemy_turn | A |
| A unit's turn, CT count | FFT, TO | available: `ui` turn, enemy_turn | A |
| Battle start | all | available: `ui` battle | B |
| Victory, defeat, level up, objective complete | all | available: `Cue` victory, gameover, levelup, quest | B |
| Learn ability, unlock new class | FFT, FFTA, TO | available: `ui` learn | B |
| Reinforcements arrive | all | missing | C |
| Rare item, treasure, crystal left by a fallen unit | FFT, TO | partial: `item` gem, `chest` | C |
| Fallen unit countdown | FFT, TO | missing | C |

## 3. Hit outcomes

| Sound | Games | Current status | Priority |
|---|---|---|---|
| Normal hit (flesh, armor, wood, stone) | all | available: `blade`, `blunt`, `bow` hit_* | A |
| Critical hit: more weight and a flash | all | measured in TO: `ui` critical, layered over the weapon hit | A |
| Miss, dodge | all | measured in TO and FFTA2: `ui` miss | A |
| Shield block, weapon parry | all | available: `shield`, `blade` clash | A |
| Damage number, healing number appearing | all | measured: `ui` damage, heal | A |
| Status effects: poison, sleep, silence, blindness, stop, slow and haste, berserk, charm, confusion, doom, petrify, toad, zombie, paralysis, regeneration; expiration and cure | all | measured in the games: `status` poison (TO), sleep, silence, blind, stop, paralysis, regen, expire (TS); designed: the others | A |
| Stat increase/decrease, protection, magic shield | all | measured: `status` buff, debuff, protect; designed: shell | A |
| Unit falls, revive | all | measured: `body` fall with `ui` ko; `ui` revive | A |
| Counterattack, joint attack | FFT, TS, UO | partial | B |
| MP restored | all | designed: `ui` mp | B |

## 4. Weapons by class

| Sound | Games | Current status | Priority |
|---|---|---|---|
| Swords, daggers, axes | all | available: `blade` | A |
| Maces, hammers, staves | all | available: `blunt` | A |
| Bows and crossbows | all | available: `bow` | A |
| Spears and halberds: thrust; dragoon jump (rise, fall) | all | measured in the games: `spear` | A |
| Unarmed: punch, kick | FFT, FFTA | measured: `fist` | A |
| Katana: draw and cut in one motion | FFT, FFTA | measured in the games: `blade` quickdraw | B |
| Firearms: shot, reload | FFT, FFTA | measured in the games: `gun` | B |
| Thrown weapons: shuriken, knives, bombs | FFT, FFTA | measured in the games: `thrown` | B |
| Whip, book, bard instrument, dance, cards, dice | FFT, FFTA | missing | C |
| Siege: catapult, ballista, battering ram | TO, UO, TS | missing | C |

## 5. Spells

| Sound | Games | Current status | Priority |
|---|---|---|---|
| Fire, ice, lightning, arcane, holy, shadow, nature, healing | all | available: `spell` | A |
| Water, wind, earth and earthquake, poison | all | measured in the games: `spell` water, wind, earth, poison | A |
| Tiers of the same spell (Fire, Fira, Firaga) | FFT, FFTA | partial: `power` | A |
| Time: haste, slow, stop, gravity, meteor | FFT, FFTA | available: `status` haste, slow, stop; designed: `spell` gravity, meteor | B |
| Summons: arrival, strike, departure | FFT, FFTA | measured in FFTA2: `summon` | B |
| Spell charging over several turns | FFT, TO | partial: `spell` charge | B |
| Terrain reactions: burning oil, electrified water, ice, wind pushing units | TS | partial: `spell`, `torch`, `water` | B |
| Geomancy, songs, dances | FFT, FFTA | missing | C |

## 6. Units and movement

| Sound | Games | Current status | Priority |
|---|---|---|---|
| Footsteps on 8 surfaces, jumps from heights, armor | all | available: `footstep`, `gear` | A |
| Cavalry: horse walking, galloping, charging, neighing | TO, UO, TS | measured in TS: `hoof` (6 surfaces, 4 looping gaits), `horse` | A |
| Flying units: wings (griffin, wyvern, hawkman), landing | TO, UO, FFTA | measured in TS and FFTA2: `wings` feather, leather | B |
| Troops marching on the map | UO | designed: `march` (loop, move, halt) | B |
| Chocobos and other mounts | FFT, FFTA | partial: `bird` creature | C |
| Teleportation | FFT, FFTA | measured in FFTA2 and TO: `warp` arcane, retro | C |

## 7. Monsters

| Sound | Games | Current status | Priority |
|---|---|---|---|
| Beasts, birds, insects, reptiles, amphibians, monsters, slimes, spirits | all | available: `Creature` archetypes | A |
| Undead: rattling bones, wailing | all | partial: `spirit` | B |
| Dragon: roar, breath | all | missing | B |
| Golem, stone construct | all | partial: `robot` | C |
| Plant (malboro), bomb (inflate and explode) | FFT, FFTA | partial: `slime`, `explosion` | C |

## 8. Voices

| Sound | Games | Current status | Priority |
|---|---|---|---|
| Attack, pain, death, and celebration shouts | all | available: `emote`, styles `tactics`, `gasp` (measured in TO), and `kiai` (measured in Utawarerumono). Listening review (round "gritos-de-audio", roboticness 1–5): vocoder 3.4, recording shifted with PSOLA 2.9, original CC0 recording 2.1, even the latter sounding "acted, emotionless"; with tape mode on (`TARE_TOOLS_TUNE_TAPE=1`, recordings downloaded) most play the recording itself (63–83% per style) | A |
| Short battle lines and story dialogue in Portuguese | all | partial: natural voice. Listening review (round "voz-natural", accent from 1 = Brazilian to 5 = foreign): 3.9 → 2.75 after linking final r to the following vowel ("po-res-te", "da-ru-ma"), preventing closed "o" from being replaced by open "o" ("novo" came from "nove") and nasal i by n ("poções" came from "monstro"), using questions that rise and stay high, exclamations with a peak and fall, and almost no pause at commas. Pending: "Tenho poções" still sounds like "tenhu puções" (the bank has the teacher's "pu-"; final "u" may be too long, or nasal "ẽ" before "nh" is missing), and female questions remain weak | A |
| The same lines in English | all | missing: English banks | B |
| Monsters and characters that "speak" without words | FFTA | partial: babbling | C |

The Portuguese words and listening round names above are retained to identify pronunciation issues and their original evidence.

## 9. Ambience

| Sound | Games | Current status | Priority |
|---|---|---|---|
| Rain, wind, fire, stream, cave, forest, night, storm, sea, dungeon | all | available: `ambience` | B |
| Battlefield, camp, castle hall, town and market, plains, desert, snow and mountains, swamp, ruins and temple, ship deck | all | measured in TS and TO: `ambience` battlefield, camp, castle, town, plains, deck; designed: desert, snow, swamp, ruins | B |

## 10. Music

| Sound | Games | Current status | Priority |
|---|---|---|---|
| Victory, level up, quest, defeat, town, exploration, tavern, dungeon, battle, 6 color harmony loops | all | available: `Cue` | B |
| Battle variants (normal, tense, boss, final), preparation, map briefing, world map, scenes (sorrow, intrigue, triumph, comedy), recruitment | all | available (measured in FFTA2, approved by ear): `Cue` skirmish, tense, boss, final, prepare, briefing, worldmap, sorrow, intrigue, triumph, comedy, recruit | B |
| Style: martial and medieval orchestra (brass, strings, snare, modes), like Sakimoto (FFT, FFTA, TO, UO) and Senju (TS) | all | available (approved by ear, orchestral and 16-bit): tactics cues (`music_tactics.py`) | B |

## 11. Game-specific mechanics

| Sound | Games | Current status | Priority |
|---|---|---|---|
| Judge: whistle, yellow and red cards | FFTA | missing | C |
| Tarot cards; rewind time | TO | missing | C |
| Troops engage, fortress captured, town liberated | UO | missing | C |
| Scales of Conviction: voting, conviction gained | TS | missing | C |

## 12. Story scenes (everyday life)

| Sound | Games | Current status | Priority |
|---|---|---|---|
| Doors: open, close, locked, knock, slam, break down | all | measured: `door` (slam and break in the games) | A |
| Books and pages: open, close, turn, flip through, set down, write | all | measured: `book` | A |
| Glasses, mugs, and plates: toast, set down, pour, drink, cutlery, stir, break | all | measured: `tableware` | A |
| Furniture: chair, sit, desk, drawer, bed | all | measured: `furniture` | B |
| Bells: church and wedding, hand, shop, ship | all | measured: `bell` | B |
| Letters and parcels passed between people; clothing (kneeling, bowing) | TS | measured: `item` letter, `gear` cloth | B |
| Dining hall, crowded tavern | TS | measured in TS: `ambience` dinner, tavern | C |

## Proposed order

1. **Grid, menus, and battle pacing** (sections 1 and 2): heard every second and most characteristic of tactical RPGs.
2. **Hit outcomes** (section 3): critical, miss, damage, healing, status effects, stats.
3. **Missing weapons** (section 4): thrust, unarmed, firearms, thrown weapons.
4. **Missing spells** (section 5): water, wind, earth, poison, time, summons.
5. **Cavalry and flying units** (section 6).
6. **Tactical RPG ambience and music** (sections 9 and 10).
7. **Monsters and game-specific mechanics** (sections 7 and 11).
