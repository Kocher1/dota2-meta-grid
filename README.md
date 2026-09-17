# Dota 2 Meta Grid

**A data-driven Dota 2 tier list, living inside your hero picker.**

An agent skill for **Claude Code** and **Codex** (also a plain Python script) that pulls live
pub win rates, works out which heroes actually win in each role **on the current patch**, drops
the ones that lose in **your** rank bracket, and installs the rest as an in-game **hero grid** -
best pick on the left, next-best to the right, so you always know what to grab when your first
choice is banned.

No Dota Plus. No accounts. No API keys. Answer three questions and open Dota.

```
3 Offlane   (patch 7.41f, player at Ancient)      edge  +-noise   win rate in your bracket
   Enigma                                       +7.4pp   +-1.5          53.1%
   Visage                                       +4.1pp   +-1.4          52.7%
   Lycan                                        +3.8pp   +-1.3          49.2%
   Pudge                                        +3.8pp   +-0.8          50.4%
   ...
4 Support
   Bounty Hunter                                +7.2pp   +-1.1          55.2%
   Nyx Assassin                                 +3.8pp   +-1.0          52.5%
   Spirit Breaker                               +2.9pp   +-0.6          52.2%
   ...
   removed (losing in your bracket): Clockwerk (48.4%)
```

Built for **Ancient and above** - see [which ranks it fits](#which-ranks-does-it-fit).

## Quick start

### With Claude Code or Codex (the "voila" way)
Paste this into your agent:

> Install the skill from https://github.com/Kocher1/dota2-meta-grid and build my Dota 2 hero grid.

It will ask for **your rank**, **the roles you play** and **how many heroes per role**, check
with you before keeping any oddball specialist picks, then write the grid. Close Dota when it
asks, reopen, pick **Meta Grid** in the grid dropdown.

Prefer to install by hand?

```bash
# Claude Code
git clone https://github.com/Kocher1/dota2-meta-grid ~/.claude/skills/dota2-meta-grid
# Codex
git clone https://github.com/Kocher1/dota2-meta-grid ~/.codex/skills/dota2-meta-grid
```

Then just say *"build my Dota hero grid"*.

### Without any AI
Python 3.8+, nothing to install:

```bash
python scripts/build_grid.py --rank 3400                    # look first (writes nothing)
python scripts/build_grid.py --rank 3400 --roles 1,2 --write   # install it (close Dota first)
```

Works on Windows, Linux and macOS. Your existing grids are kept and the old file is backed up.
Re-run weekly, and a few days after every patch.

## How to climb MMR, statistically

There is no trick. Rank is **edge x volume**:

> **MMR gained ~ games played x (2 x win rate - 1) x 25**

A win and a loss are each worth about 25 MMR, so at 50% you go nowhere forever, and every
point above 50% is worth about half an MMR *per game*. It adds up - slowly, then obviously:

| Win rate | MMR per 100 games | Games for one medal (~770 MMR) | Games until skill outweighs luck* |
|---:|---:|---:|---:|
| 50% | 0 | never | never |
| 51% | +50 | ~1,540 | ~2,500 |
| 52% | +100 | ~770 | ~625 |
| 53% | +150 | ~510 | ~280 |
| 55% | +250 | ~310 | ~100 |

\* Luck over *N* games is about +-25 x sqrt(N) MMR. Your expected gain only overtakes it after roughly
1 / (2 x win rate - 1)^2 games. This is why 30 games on a "broken" hero tells you nothing, and why
people who grind 600 games at 52% climb while people who tilt-queue at 50% don't.

So there are exactly two levers: **play more games, and raise your edge.** Picking heroes that
are statistically winning right now is the cheapest edge there is - it costs no mechanical
skill. In out-of-sample tests the top 3 heroes this tool picks per role won **about 4 points
more** than an average hero in that role, and the top 7 about 3 points more (at 6500+ MMR;
see [the method](references/METHOD.md)). Even half of that is the difference between the 50%
row and the 52% row above.

The grid doesn't make you better. It stops you from giving away edge in the draft.

## How it works

- **Role-specific win rates** from 6500+ MMR pubs (the only open data with a position split),
  corrected for sample size - a hero at 60% over 130 games is treated as ~52%, not as a god.
- **A veto from your own bracket**: heroes below 49% in your rank bracket (OpenDota) are
  removed, however good they look at 6500+.
- **Patch-aware**: pre-patch games are a prior, not the truth; heroes touched by the patch are
  allowed to move.
- **Niche picks are your call.** Heroes played by a handful of specialists (Meepo, Visage,
  Lone Druid...) really do win - for those specialists. The skill asks before keeping them.
- **Your lifetime record** (read locally from Dota's own `stats.dat`) is a tie-breaker worth
  at most +-1.5 points. Meta first.

Every constant was chosen by backtest; the full evidence table and the known limits are in
[references/METHOD.md](references/METHOD.md).

## Which ranks does it fit?

The role statistics come from 6500+ MMR games, so the list fits best from **Ancient upward**.
Measured against each bracket's own win rates, about 91% of a 6500+ edge carries over at
Divine, 74% at Ancient, 57% at Legend and under half at Archon and below. Lower-ranked players
still get a sane list - the veto throws out heroes that lose in their bracket - but should
treat it as a starting point and be sceptical of heroes that need coordination to work.

## Dota 2 MMR ranks (approximate)

The script accepts either an MMR number or a medal:

| Medal | MMR | Medal | MMR |
|---|---|---|---|
| Herald | 0 - 769 | Legend | 3,080 - 3,849 |
| Guardian | 770 - 1,539 | Ancient | 3,850 - 4,619 |
| Crusader | 1,540 - 2,309 | Divine | 4,620 - 5,619 |
| Archon | 2,310 - 3,079 | Immortal | 5,620+ |

## FAQ

**Is this safe for my account?** It edits `hero_grid_config.json`, the same settings file the
in-game grid editor saves. It never touches the game process or memory, and it refuses to
write while Dota is running.

**Do I need Dota Plus?** No.

**Where does the data come from?** Role statistics from
[Dota2ProTracker](https://dota2protracker.com), bracket win rates from
[OpenDota](https://www.opendota.com), patch notes from dota2.com. The script is a polite
client: about a dozen small requests per run, paced and cached for six hours. If you use this a
lot, consider supporting those sites - they do the hard part.

**It says the site refused the request.** The stats site rate-limits scripts. Wait 15-30
minutes and run it again; finished downloads are cached.

**Does it consider counters and drafts?** No. It answers "what wins on average at my rank",
which is the right question for a first-phase pick and a hero pool - not for a last pick.

## Who made this

The team behind **[OVERDOG](https://overdog.bet)** - Dota 2 betting against other fans instead
of a bookmaker. Think you read the pro meta as well as your pubs? That's the place. *18+*

## License

MIT. Not affiliated with Valve, Dota2ProTracker or OpenDota. Dota 2 is a trademark of Valve Corporation.
