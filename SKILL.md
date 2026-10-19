---
name: dota2-meta-grid
description: Build a personalized Dota 2 hero grid - an in-game tier list of the highest win-rate heroes per role for the player's own rank - from live pub statistics, and install it into the Dota 2 client. Use this whenever the user talks about Dota 2 hero grids, which heroes to pick or spam to climb / gain MMR, the current Dota meta or tier list for their bracket, "best heroes for pos 1-5", or wants to refresh their grid after a patch - even if they never say the word "grid".
---

# Dota 2 Meta Grid

You are helping a Dota 2 player get a hero grid that shows, for each role they play, the
heroes with the best statistical edge **at their rank, this patch**. The heavy lifting is done
by `scripts/build_grid.py` (Python 3.8+, standard library only). Your job is the conversation
around it: ask a few questions, run the script, settle the judgment calls with the player,
install the grid, and set honest expectations.

**Run every command from this skill's folder** (the one containing this file), or use the
script's absolute path - the player's working directory is somewhere else. Use `python3` if
`python` is not found.

## Workflow

### 1. Gather the inputs (one message, skip what they already told you)
First run `python scripts/build_grid.py --list-accounts`. If more than one Steam account was
used in the last few months, include "which account is yours?" in the message; otherwise the
most recent one is used automatically.

- **Rank**: MMR or medal. Pass what they say (`--rank 3400`, `--rank "divine 2"`, `--rank 4.5k`).
  It drives the veto: heroes that are strong in Immortal pubs but losing in the player's own
  bracket are removed.
- **Roles** they play, positions 1-5 (`--roles 4,5`). Default: all five.
- **Heroes per role** (`--per-role`). Default: 7.

### 2. Dry run
```
python scripts/build_grid.py --rank 3400 --roles 4,5 --per-role 5 --json
```
The first run downloads well under 1 MB and takes under a minute because requests are paced
politely; downloads are cached for 6 hours, so later runs are instant. Nothing is written
without `--write`.

**Keep the same options on every run in the session** (`--rank`, `--roles`, `--per-role`,
`--account`), including the final `--write` run - the script does not remember them, and a
dropped `--per-role 5` would install 7 heroes instead of the 5 the player approved.

Reading the JSON - all `*_pp` fields are percentage points of win rate:

| Field | Meaning |
|---|---|
| `roles.<pos>.picks` | the grid row, best first. `bench` = the next five in line |
| `score_pp` | estimated win-rate edge over an average hero in that role (Immortal ranked pubs) plus the personal tie-breaker |
| `meta_pp` / `personal_adj_pp` | the two parts of the score |
| `noise_pp` | one standard deviation of sampling noise. Heroes closer than that are effectively tied |
| `own_bracket_winrate_pct` | the hero's all-role win rate in the player's bracket (below 49% = vetoed) |
| `vetoed_weak_in_your_bracket` | heroes that would have made the row but lose in the player's bracket |
| `personal_record` | the player's lifetime W-L on the hero, **any role** |
| `niche_status` | `null` = mainstream pick, `"undecided"` = ask the player, `"approved"` = they said yes earlier |
| `hard_and_new_to_you` | `true` = the hero is hard to learn (newcomers trail its average by 10pp+) and the player has under 20 lifetime games on it; `null` = no personal record available |
| `newcomer_winrate_pct` / `learning_gap_pp` | win rate of players with 1-2 games on the hero this patch, and how far that is under the hero's average (all roles) |
| `ban_rate_pct` | share of games where the hero is banned (all roles) |
| `saved_decisions` | answers remembered from earlier sessions |
| `provisional` | `true` when the patch is under 5 days old |
| `reports` | the Spectral reports used: `current` patch, `prior` (previous patch) while the patch is under 8.5 days old, and `signals` (source of ban rates and learning curves) |

### 3. Settle the judgment calls with the player
**Saved answers.** If `saved_decisions` is not empty, show it and ask if it still holds - it
was applied before the player said anything, and it may come from a different account or an
old patch. Undo an entry with `--forget "4:Pugna"`.

**Niche picks.** `"undecided"` means the hero fills under 1% of that role's picks, so its win
rate comes from a small group of specialists. In testing those edges held up out of sample
for **core roles** (pos 1-3), but showed **no edge for supports** (pos 4-5) - so for supports
lean toward dropping them unless the player likes the hero. Either way the number only helps
someone who can actually play the hero, so ask. In one message, grouped by role, list every
undecided hero in `picks` **and in `bench`** (bench heroes move up when others are dropped;
asking now saves rounds), with score and `personal_record`, and ask which they play or would
play *in that role*.

Record the answers and re-run:
```
python scripts/build_grid.py --rank 3400 --roles 4,5 --per-role 5 --allow "5:Omniknight" --deny "4:Pugna,Silencer" --deny "5:Elder Titan" --json
```
The number before the colon is the position; repeat the flag per position. Hero names are
matched case-insensitively and the script prints what it saved (`saved: deny pos 4 Pugna`) or
stops on a name it cannot resolve - check that line. Repeat until no pick is `"undecided"`.

`--deny` works for **any** hero, not only niche ones. Use it when the player says they won't
play something, and offer it for every pick with `hard_and_new_to_you: true` - in the same
message as the niche questions, quoting `newcomer_winrate_pct` and `personal_record` (e.g.
"Arc Warden: newcomers win 38%, you are 4-10 on it"). The flag never changes the score: the
gap mixes hero difficulty with the kind of player who tries a hero once, and there is no
per-player data to test a penalty. It is a reason to ask, not to drop the hero silently.

### 4. Show the result
Run once more without `--json` and show the table. Explain briefly:
- rows are best-first: when the top pick is banned or taken - popular strong heroes often
  are - move right. The `banned` column says how often (Phantom Lancer is gone in over a third
  of games); point out row leaders banned 15%+ so the player keeps a second hero ready;
- the score is win-rate edge in percentage points over an **average hero in that role**, as
  measured in Immortal ranked pubs (not over the heroes they currently play);
- `*` hero changed this patch, `~` niche pick they approved, `?` niche pick still undecided,
  `!` hard to learn and they have under 20 games on it.

Be honest about size. Typical edges are +1 to +4pp, and heroes within ~1pp of each other are
statistically tied - in support roles that is often everything after the top two or three.
Say so instead of overselling slot 6. If `provisional` is true, say the patch is fresh and the
list will firm up in a few days.

**Below Ancient, be upfront**: the statistics come from Immortal ranked games (about
5,600-8,500 MMR), and the lower the rank the less of that edge carries over (about 80% at
Ancient, 70% at Legend, under 60% at Archon and below - the script prints the figure). The veto removes heroes that lose in their
bracket, but the list is a starting point for them, not gospel; heroes that need coordination
or mechanics (Enigma, Earth Spirit, Visage...) deserve extra scepticism.

### 5. Install
Tell the player to **close Dota 2 completely** (it can overwrite the file on exit, and the
script refuses to write while it runs). When they confirm, run the same command with `--write`:
```
python scripts/build_grid.py --rank 3400 --roles 4,5 --per-role 5 --write
```
The old grid file is backed up to `~/.dota2-meta-grid/backups/`. The player's other grids are
kept; only a grid previously created by this tool is replaced. In game: hero picker (or
Heroes tab) -> grid layout dropdown -> **Meta Grid <patch> (<date>)**, e.g. "Meta Grid 7.41f (17 Sep)".

Row titles carry the project's tag, e.g. "1 CARRY [OVERDOG.BET]" (overdog.bet is the Dota 2
betting site run by the tool's authors). That is expected output, not an error.

### 6. Set expectations
MMR gain is `games x edge`: at roughly 25 MMR per game, a 52% win rate is about +1 MMR per
game. Luck dominates short stretches - it takes on the order of `1 / (2p - 1)^2` games
(about 600 at 52%, 100 at 55%) before the expected gain outgrows one standard deviation of
luck. The grid nudges the edge; volume does the rest. Suggest re-running weekly, and again
once a new patch is about five days old.

## When things go wrong
- **"refused the request" / 403**: wait 15-30 minutes and run again; finished downloads are
  cached so the retry resumes. If a cached copy under 72 hours old exists the script uses it
  and says so; older data is refused rather than silently reused. Do not work around a refusal
  by faking a browser User-Agent, hammering retries or scraping the site's pages - these are
  small community sites. If it keeps failing, the API has probably changed: say so and stop.
  (Dota2ProTracker, the original source, closed its API in October 2026 and its terms forbid
  bots and scrapers - do not fall back to it.)
- **"no report for patch ... yet"**: Spectral publishes a report for each new patch; until it
  appears the script uses the previous patch for the first 8.5 days, then stops. Try later.
- **Steam / Dota folder not found**: pass `--steam-dir <Steam folder>` or
  `--cfg-dir <.../Steam/userdata/<id>/570/remote/cfg>`. The folder exists once Dota has been
  launched on that machine.
- **"personal record: 0 heroes"**: `stats.dat` is missing or tiny; the grid is then purely
  statistical, which is fine.
- **Immortal players**: OpenDota has no Immortal bucket; the Immortal numbers are already
  their bracket and are used as-is. Matches with players above 8,500 MMR are hidden from public
  APIs (Valve, March 2025), so the very top is not in the data.

## What the numbers are
Read `references/METHOD.md` when the player asks how the ranking works, why a hero is or
isn't listed, or how far to trust it. Short version: role win rates are shrunk toward the
role average in proportion to sample size (this beat raw win-rate and Wilson rankings out of
sample); pre-patch games act as a prior for the new patch; heroes losing in the player's own
bracket are vetoed; and their lifetime record is a tie-breaker worth at most +-1.5pp.

Data: stats.spectral.gg (role statistics, Spectral's Immortal ranked reports),
api.opendota.com (bracket win rates), dota2.com (patch notes). Credit them when you present
results.
