# Credits and upstream data

This project is a derivative work. The scoring maths and the game data tables are
**not** original to it — they come from these two projects:

## Fribbels HSR Optimizer — MIT

<https://github.com/fribbels/hsr-optimizer> · <https://fribbels.github.io/hsr-optimizer/>

The scoring engine is a 1:1 port of the optimizer's relic scoring:

* per-character substat weights and main-stat weights
* the ideal-score calculation and the "value" a relic is worth for a character
* the letter rating tiers
* the low/mid/high roll values used to snap the game's truncated displayed
  numbers back onto real roll combinations

Extracted from `src/lib/relics/scoring/` (`currentScore.ts`, `relicScorer.ts`,
`optimalScore.ts`, `scoringMetadata.ts`, `scoringConstants.ts`) and the
per-character `scoring:` blocks under `src/lib/conditionals/character/`.
Those weights live here in `relic_grades/data/weights.json`.

## Mar-7th StarRailRes — AGPL-3.0

<https://github.com/Mar-7th/StarRailRes>

Game data used to map ids and names:

* `relic_grades/data/relics_min.json` — relic id to set, slot and rarity
* `relic_grades/data/characters_min.json` — character ids and names
* `relic_grades/data/relic_sets_min.json` — set names
* `relic_grades/data/relic_pieces.json` — relic piece name to set and slot

Because these tables are AGPL-3.0, this repository as a whole is licensed
**AGPL-3.0-or-later** (see `LICENSE`). That is the only reason for the license
choice: the MIT parts would happily live under anything.

## Honkai: Star Rail

Game names, terms and screenshots belong to HoYoverse / miHoYo. This is an
unofficial fan tool with no affiliation.
