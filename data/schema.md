# Champion Data Schema

Every champion is a bundle of **facts a Master+ player already knows in their head**.
The engine reasons over these facts; it does not "know League" any other way. If a
field is wrong or missing, the coaching degrades gracefully (and we flag it).

All 0–3 and 1–5 scales are **coarse on purpose** — we want robust buckets, not a
false sense of precision. A human coach thinks "she's a lane bully who falls off,"
not "her 14-minute win rate is 51.3%."

## Fields

| Field | Type | Meaning |
|---|---|---|
| `name` | str | Display name. |
| `roles` | [str] | `top` `jungle` `mid` `adc` `support`. First entry = primary role. |
| `classes` | [str] | `tank` `bruiser` `marksman` `mage` `assassin` `enchanter` `catcher` `juggernaut`. |
| `damage_type` | enum | `physical` `magic` `mixed` `true`. Drives itemization advice (armor vs MR). |
| `damage_profile` | enum | `burst` `sustained` `dps` `poke` `mixed`. *How* the damage comes out. |
| `range_type` | enum | `melee` `ranged`. |
| `attack_range` | int | Auto-attack range (used for lane poke/zoning logic). |
| `curve` | {early,mid,late} | Relative strength 1–5 at each game stage. This is the heart of the model. |
| `engage` | 0–3 | Ability to *start* a fight on the enemy's terms (hard, gap-closing initiation). |
| `disengage` | 0–3 | Ability to *stop* a fight / peel / reset (knockbacks, speed, heavy shields). |
| `mobility` | 0–3 | Dashes/blinks for self-positioning and escape. |
| `waveclear` | 0–3 | How fast they clear a wave (matters for siege, roam windows, catch-up). |
| `cc` | [{type,hard}] | Crowd control. `hard=true` = stun/root/knockup/hook/suppress; `false` = slow/silence/nearsight. |
| `utility` | [str] | `shield` `heal` `speed` `resistances` `heal_cut` etc. |
| `tags` | [str] | Controlled vocabulary (see `tags.md`). This is how rules match. |
| `spikes` | [{when,note}] | Named power spikes: `level_2/3/6/9/11/16`, `item_1/2/3`, `three_item`. |
| `carry` | bool | Is this a primary damage source you build a game around / must protect? |
| `notes` | str | Human-readable scouting note (used as raw material, never as gospel). |

## Design rules
- **No numbers you can't defend to a challenger.** Coarse buckets only.
- **`tags` are the join key.** Rules should match on tags/curve, not on champion names,
  so the engine works for champions it has never "seen" as long as they're tagged.
- **`curve` is comparative, not absolute.** A 5 late means "this is a scaling win
  condition," not "objectively strong."
