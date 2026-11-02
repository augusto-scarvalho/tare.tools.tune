# Essential RPG sounds

[Documentation index](README.md) · [Project README](../README.md) · [Português brasileiro (alternative)](pt-BR/sons-rpg.md)

What an action or adventure RPG needs, in the order we are implementing it. Each sound follows the same method:

1. Measure real recordings.
2. Model the mechanism using those numbers.
3. Listen in context (swing and hit together, the entire shot).
4. Integrate.

Recordings are used only for measurement and are not included in the repository.

**Statuses:**

- **Approved:** measured and selected by ear.
- **Measured:** modeled from recordings; listening review pending.
- **Legacy:** the first version, designed without recordings.
- **Missing:** not implemented yet.

| # | Sound | Recipe and events | Status |
|---|---|---|---|
| 1 | Sword: swing, clash, hits (wood, stone, armor, flesh) | `blade` swing, clash, hit_* | approved |
| 2 | Sword: draw from scabbard, drop | `blade` draw, drop | measured |
| 3 | Bow: draw, release, flight, arrow hitting wood | `bow` draw, release, fly, hit_wood | approved |
| 4 | Bow: arrow hitting flesh and stone | `bow` hit_flesh, hit_stone | measured |
| 5 | Mace and hammer: swing, hits, drop | `blunt` | measured |
| 6 | Shield: block sword, mace, and arrow (wood, metal), bash | `shield` block_blade, block_blunt, block_arrow, bash | measured |
| 7 | Footsteps: 8 surfaces × walk, run, land, scuff | `footstep` | measured |
| 8 | Moving equipment: chainmail, plate, leather | `gear` move, run, equip | measured |
| 9 | Body falling to the ground (stone, wood, dirt) | `body` fall, drop | measured |
| 10 | Chest: open, close, locked, unlock | `chest` open, close, locked, unlock | measured |
| 11 | Door and gate: creaking open, close, locked, unlock, knock | `door` open, close, locked, unlock, knock | measured |
| 12 | Items: coins, potion, scroll, gem × pickup, use, drop | `item` pickup, use, drop | measured |
| 13 | Breaking: wooden crate or barrel, ceramic pot, glass | `breakable` hit, break | measured |
| 14 | Interface: click, open and close inventory, level up, quest complete, error | `ui` (fantasy, retro) | measured |
| 15 | World: lever, traps (darts, spikes, blade), torch, water (drip, splash, dive) | `lever`, `trap`, `torch`, `water` | measured |
| 16 | Spells: 8 elements × charge, cast, travel, impact | `spell` | measured |
| 17 | Ambience: 10 looping locations, with occasional events | `ambience` | measured (8 of 10 against recordings) |
| 18 | Explosions: nearby, distant, debris | `explosion` | measured |
