# Method and evidence

Role statistics come from Spectral's "Immortal Rank Meta Trends" reports (stats.spectral.gg),
one report per patch, ranked All Pick games of roughly 5,600-8,500 MMR. Until October 2026 they
came from Dota2ProTracker's 6500+ MMR tables; D2PT then closed its API and its terms forbid
automated access, so the source was switched.

The method was designed and tested on 2026-09-17 on Dota2ProTracker data for Sep 10-17
(patch 7.41e -> 7.41f on Sep 15) and OpenDota's 7-day bracket statistics. "Backtest" = train on
3 of the 5 clean 7.41e days, test on the other 2, all 10 splits x 5 roles; the score is the
realized out-of-sample win-rate edge of the top-7 heroes per role. On 2026-10-19 the core
results were re-checked on Spectral data (marked "Spectral" below).

## Scoring

    score(hero, role) = shrunk role win-rate edge in Immortal ranked pubs
                      + personal tie-breaker (0.25 x your shrunk lifetime edge, max +-1.5pp)

    eligible if  the hero fills >= 0.3% of the role's slots
            and  its all-role win rate in YOUR OpenDota bracket is >= 49%   (the veto)
            and  you have not said you won't play it there

* **Shrinkage**: an empirical-Bayes beta prior per role, fitted by the method of moments
  (variance of observed win rates minus mean sampling variance, floored at a 1pp spread). True
  between-hero spread is only about 1.6-3.3pp depending on role, so a 60% win rate over 130
  games becomes about 52%.
* **Patch handling**: post-patch games are the current patch's report. While the patch is
  younger than 8.5 days, the previous patch's report forms the prior, scaled down to the games
  of the pre-patch part of an 8-day window (the setup tested below); it is widened by the
  expected patch drift (tau = 2.4pp for heroes the patch touched, ~0 for the rest) and updated
  with post-patch games. Before Spectral publishes a report for a new patch, the prior alone is
  used and the result is marked provisional.
* **Veto**: the only place the player's own rank enters. It removes heroes that are strong in
  Immortal pubs but losing in the player's bracket (e.g. Monkey King or Naga Siren at Ancient).

## What was tested

| Assumption | Test | Verdict |
|---|---|---|
| Shrunk win rate ranks better than raw win rate | Backtest: shrunk +2.88pp, raw (n>=50) +2.20, raw (n>=200) +2.69, Wilson lower bound +2.37. Prediction RMSE 2.62 vs 2.82pp | confirmed |
| Low-pick heroes should be cut at 1% of role slots | A 1% floor *lowers* the realized edge to +2.25pp; 0.3% is the best floor tested (+3.11pp) | rejected -> 0.3% floor |
| Niche picks' edge is fake | Cores: realized >= predicted (mid niche picks: predicted +5.1pp, realized +6.6pp). Supports: about -0.6pp on small samples | real for cores, no evidence for supports; whether it transfers to a non-specialist cannot be tested -> the player is asked |
| The prior mean should depend on pick rate | Regression prior: +2.89 vs +2.88pp | no gain, dropped |
| Model is calibrated | Predicted vs realized edge of selected heroes agree within ~0.5pp in core roles | confirmed |
| Heroes drift across a letter patch | Pre vs post win rates, 172 hero-roles: heroes the patch touched drift with SD 2.4pp beyond sampling noise; untouched heroes show no drift beyond noise | tau = 2.4pp / ~0 |
| The ranking holds on Spectral data | Spectral: rank on one week of 7.41f (Oct 4-11), measure the other (Oct 11-19), both directions. Top-1 +6.1pp, top-3 +4.2pp, top-7 +3.2pp; averaged over both directions predicted and realized agree within ~0.3pp (single directions: up to 1.2pp for the top-1 pick) | confirmed. With ~100k games a week, shrunk and raw (n>=200) rankings are nearly identical; shrinkage matters for small samples (niche heroes, fresh patches) |
| Immortal statistics transfer to lower ranks | Spectral: noise-corrected correlation of all-role hero win rates (last week) with OpenDota's 7-day bracket win rates: Divine 0.99, Ancient 0.88, Legend 0.76, Archon 0.62, Crusader 0.50, Guardian 0.42, Herald 0.31. Share of an edge that carries over (regression slope): 0.92 / 0.79 / 0.69 / 0.58 / 0.46 / 0.40 / 0.31. (D2PT 6500+: 0.91 / 0.74 / 0.57 / 0.47 / 0.33 / 0.24 / 0.15) | only partly - see limits |
| Bracket trends can be extrapolated | A hero's MMR gradient inside 6500+ vs its Divine-minus-Ancient gradient: r = 0.14 | rejected -> plain veto, no extrapolation |

Data notes, for anyone extending this:
* Spectral's position keys are core flag . lane: `1.1` carry, `1.2` mid, `1.3` offlane,
  `0.3` soft support (pos 4), `0.1` hard support (pos 5). Checked on known heroes (Crystal
  Maiden, Warlock, Dazzle are mostly `0.1`; Spirit Breaker, Rubick, Bounty Hunter mostly `0.3`);
  at least one public project has the two support keys swapped. Each key sums to twice the
  number of matches with positions.
* Wins are `matches_s x winrate_s`; the win rate has 4 decimals, so this is exact to ~0.005pp.
* The report for a patch is found by match dates, not by name: Spectral merges some letter
  patches ("7.41(a)" covers Valve's 7.41 and 7.41a) and has used names like "7.23(a/b)".
* Spectral has no role data per region (the endpoint errors) and no current reports below
  Immortal.

## Display-only signals
Shown next to each pick, never part of the score:
* **Ban rate** (`heroes/draft`, all roles): games where the hero was banned / games in the
  report. 7.41f: median hero 3%, Phantom Lancer 38%, Outworld Devourer 30%, Pudge 27%.
* **Learning curve** (`heroes/wrplayers`, all roles): win rate of players with 1-2 games on the
  hero in the patch vs the hero's average. Every hero shows a gap (7.41f: 4-16pp, median 6.5pp)
  because one-off games include off-role tries and weaker players; the hero-specific part is
  the excess. A gap of 10pp+ marks a hero as hard to learn (7.41f: Tinker, Visage, Meepo, Arc
  Warden, Broodmother, Io, Invoker, Lone Druid, Brewmaster, Kez, Dark Seer). Combined with
  under 20 lifetime games of the player's own (`stats.dat`, any role) the pick is flagged `!`.
  Both thresholds are judgment calls: there is no per-player outcome data to backtest a
  penalty, so the flag prompts a question instead of changing the ranking.

## Expected gain
Out of sample in Immortal pubs (Spectral, week to week): top-1 pick +6.1pp, top-3 +4.2pp,
top-7 +3.2pp over an average hero in the role. (D2PT 6500+, Sep 2026: +5.2 / +4.1 / +2.9pp.)

## Known limits
* **Built for Ancient and above.** The role statistics are Immortal games. About 79% of such an
  edge carries over at Ancient, 69% at Legend, 58% at Archon, under half below. The veto removes
  the worst mismatches but does not re-rank the list for low brackets. STRATZ's API has role x
  bracket statistics, but it needs a personal token (Steam login); with one, this would be the
  first thing to fix.
* Matches with a player above 8,500 MMR are hidden from public APIs since March 2025, so the
  very top of the ladder is not in the data.
* tau and the shrinkage/floor tests were measured on one week around one patch (D2PT data).
* OpenDota has no Immortal bucket (no veto there) and no role split (the veto is all-role).
  Its window is the last 7 days, so right after a patch the veto still reflects the old one.
* Role detection is Spectral's.
* It is unverified whether `stats.dat` lifetime standings include unranked or turbo games;
  the personal term is capped at +-1.5pp partly for that reason. In flat roles (supports) it
  can still reorder near-tied heroes - it is a tie-breaker, not evidence.
* Statistics describe the hero population, not drafts: counters, synergies and lane matchups
  are ignored.
