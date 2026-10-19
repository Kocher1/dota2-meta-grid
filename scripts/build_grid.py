#!/usr/bin/env python3
"""dota2-meta-grid: build a Dota 2 hero grid of the highest win-rate heroes per role.

    python build_grid.py --rank 4500                 dry run: print the ranking, touch nothing
    python build_grid.py --rank ancient --write      write the grid (Dota must be closed)
    python build_grid.py --rank 3200 --json          machine-readable output for an agent

Data (no accounts, no API keys):
  * stats.spectral.gg     role-split win rates in Immortal ranked pubs, one report per patch
  * api.opendota.com      win rates in YOUR rank bracket (no role split), used as a veto
  * dota2.com datafeed    latest patch and the heroes it changed
  * <steam>/userdata/<id>/570/remote/cfg/stats.dat   your own lifetime record (optional)

Method and the evidence behind every constant: references/METHOD.md. Stdlib only.
"""
import argparse, datetime as dt, difflib, gzip, hashlib, json, math, re, shutil, struct, subprocess, sys, time
import statistics as stt
import urllib.parse, urllib.request
from pathlib import Path

# ---- parameters (see references/METHOD.md for how each was chosen) ------------------
ROLE_SHARE_FLOOR = 0.003   # hero must fill >=0.3% of the role's slots to be considered there
NICHE_SHARE = 0.01         # below this the pick is "niche": ask the player before keeping it
TAU_CHANGED = 0.024        # sd of true WR drift across a patch, heroes the patch touched
TAU_UNCHANGED = 0.001      # ... heroes it did not touch (measured ~0)
PERSONAL_WEIGHT = 0.25     # your lifetime record is a tie-breaker ...
PERSONAL_CAP = 0.015       # ... and never moves a hero by more than 1.5pp
VETO_WR = 0.49             # drop heroes whose all-role win rate in YOUR bracket is below this
HARD_GAP = 0.10            # newcomers (1-2 games) trail the hero's average by this much: hard to learn
NEW_TO_YOU = 20            # ... and you have fewer lifetime games on it than this: flagged, not re-scored
# Share of an Immortal-pub edge that carries over to each OpenDota bracket (measured Oct 2026).
# Only used to warn players below Ancient that the list fits them less well.
TRANSFER = {1: 0.31, 2: 0.40, 3: 0.46, 4: 0.58, 5: 0.69, 6: 0.79, 7: 0.92, 8: 1.0}
MEDALS = ["herald", "guardian", "crusader", "archon", "legend", "ancient", "divine", "immortal"]
MMR_FLOORS = [0, 770, 1540, 2310, 3080, 3850, 4620, 5620]      # approximate medal boundaries; the
# July 2026 rescale compressed Immortal MMR only, Divine and below are unchanged

ROLES = {1: ("pos 1", "1 Carry"), 2: ("pos 2", "2 Mid"), 3: ("pos 3", "3 Offlane"),
         4: ("pos 4", "4 Support"), 5: ("pos 5", "5 Hard Support")}
OUR_CONFIG = re.compile(r"^Meta Grid \d+\.\d+\w? \(\d{2} \w{3}\)$")   # only grids this tool made
UA = "dota2-meta-grid/1.0 (+https://github.com/Kocher1/dota2-meta-grid)"
STATE = Path.home() / ".dota2-meta-grid"          # cache, backups, saved decisions
CACHE_HOURS = 6
STALE_HOURS = 72           # if a site refuses, older cached data is refused too, not silently reused
SPECTRAL = "https://stats.spectral.gg/lrg2/api/"
SPECTRAL_POS = {1: "1.1", 2: "1.2", 3: "1.3", 4: "0.3", 5: "0.1"}   # core flag . lane; 0.3 = soft support
PRIOR_DAYS = 8.5           # until the patch is this old, the previous patch's games form the prior
SPONSOR_TAG = "overdog.bet"   # shown in the grid's row titles


def die(msg):
    raise SystemExit("error: " + msg)


# ---- fetching: gzip + on-disk cache + polite pacing ------------------------------------
_last_hit = {}


def fetch_json(url, refresh=False):
    cache = STATE / "cache" / (hashlib.sha1(url.encode()).hexdigest() + ".json")
    age_h = (time.time() - cache.stat().st_mtime) / 3600 if cache.exists() else None
    if not refresh and age_h is not None and age_h < CACHE_HOURS:
        return json.loads(cache.read_text(encoding="utf-8"))
    host = urllib.parse.urlparse(url).netloc
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    raw = err = None
    for backoff in (0, 15, 45):                 # the stats site rate-limits scripts: go slowly
        time.sleep(max(backoff, 7.0 - (time.time() - _last_hit.get(host, 0))))
        _last_hit[host] = time.time()
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
            break
        except Exception as e:
            err = e
    if raw is None:
        if age_h is not None and age_h < STALE_HOURS:      # better a day-old table than no grid
            print(f"warning: {host} refused the request ({err}); reusing data from {age_h:.0f}h ago",
                  file=sys.stderr)
            return json.loads(cache.read_text(encoding="utf-8"))
        old = f" The cached copy is {age_h / 24:.0f} days old, too old to use." if age_h else ""
        die(f"{host} refused the request ({err}).{old}\nTry again in 15-30 minutes; downloads are cached, "
            "so a retry resumes where it stopped. If it keeps failing, the site may have changed its API.")
    data = json.loads(raw.decode("utf-8"))
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(cache)
    return data


def spectral_reports(patch_ts, refresh):
    """(current, previous) Spectral 'Immortal Rank Meta Trends' reports as (tag, days covered, matches).
    Matched by match dates, not names: Spectral merges some letter patches ("7.41(a)") that Valve
    lists separately. current is None until the report holds a day of games from this patch."""
    rows = fetch_json(SPECTRAL + "?mod=list&cat=ranked_patches", refresh).get("result", {}).get("reports", {})
    reps = sorted((int(r["first_match"]["date"]), int(r["last_match"]["date"]), r["tag"], int(r.get("matches") or 0))
                  for r in rows.values()
                  if r.get("tag", "").startswith("imm_ranked_") and "Meta Trends" in r.get("name", ""))
    if not reps:
        die("stats.spectral.gg listed no Immortal ranked reports - its API may have changed.")
    days = [(tag, (last - first) / 86400, n) for first, last, tag, n in reps]
    if reps[-1][1] >= patch_ts + 86400:
        return days[-1], (days[-2] if len(days) > 1 else None)
    return None, days[-1]


def role_games(tag, role, refresh):
    """hero_id -> (wins, matches) in one position of a Spectral report."""
    res = fetch_json(f"{SPECTRAL}?mod=heroes-positions&league={tag}", refresh).get("result")
    rows = res.get(SPECTRAL_POS[role]) if isinstance(res, dict) else None
    if not rows:
        die(f"stats.spectral.gg has no position data in report '{tag}' - its API may have changed.")
    return {int(h): (round(v["matches_s"] * v["winrate_s"]), v["matches_s"])
            for h, v in rows.items() if isinstance(v, dict) and v.get("matches_s")}


def hero_signals(rep, refresh):
    """hero_id -> {ban rate, newcomer win rate, average win rate} from a Spectral report (all roles).
    Display only: they never change the score. Missing endpoints just leave the fields empty."""
    tag, _, matches = rep
    out = {}
    draft = fetch_json(f"{SPECTRAL}?mod=heroes-draft&league={tag}", refresh).get("result")
    total = draft.get("total") if isinstance(draft, dict) else None
    for h, v in (total or {}).items() if matches else ():
        out.setdefault(int(h), {})["ban"] = int(v.get("matches_banned") or 0) / matches
    curve = fetch_json(f"{SPECTRAL}?mod=heroes-wrplayers&league={tag}", refresh).get("result")
    for h, v in (curve if isinstance(curve, dict) else {}).items():
        if isinstance(v, dict) and v.get("q1_wr_avg") is not None and v.get("winrate_avg") is not None:
            out.setdefault(int(h), {}).update(newcomer=v["q1_wr_avg"], average=v["winrate_avg"])
    return out


def latest_patch(refresh):
    plist = fetch_json("https://www.dota2.com/datafeed/patchnoteslist?language=english", refresh)["patches"]
    p = max(plist, key=lambda x: x["patch_timestamp"])
    notes = fetch_json("https://www.dota2.com/datafeed/patchnotes?language=english&version="
                       + urllib.parse.quote(p["patch_name"]), refresh)
    return p["patch_name"], p["patch_timestamp"], {h["hero_id"] for h in notes.get("heroes", [])}


# ---- Steam / local files ---------------------------------------------------------------
def steam_roots():
    roots = []
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                roots.append(Path(winreg.QueryValueEx(k, "SteamPath")[0]))
        except OSError:
            pass
        roots += [Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")]
    elif sys.platform == "darwin":
        roots.append(Path.home() / "Library/Application Support/Steam")
    else:
        roots += [Path.home() / ".steam/steam", Path.home() / ".local/share/Steam",
                  Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam"]
    return [r for r in roots if (r / "userdata").is_dir()]


def accounts(steam_dir=None):
    """[(account_id, cfg_dir, last_used_timestamp)], most recently used first."""
    if steam_dir and not (Path(steam_dir) / "userdata").is_dir():
        die(f"--steam-dir: no 'userdata' folder inside {steam_dir}. Point it at the Steam install folder.")
    out = {}
    for root in ([Path(steam_dir)] if steam_dir else steam_roots()):
        for acc in (root / "userdata").iterdir():
            cfg = acc / "570" / "remote" / "cfg"
            if cfg.is_dir() and acc.name not in out:
                out[acc.name] = (acc.name, cfg, max((f.stat().st_mtime for f in cfg.iterdir()), default=0))
    return sorted(out.values(), key=lambda a: -a[2])


def parse_vbkv(b):
    """Valve binary KeyValues (the format of stats.dat)."""
    if b[:4] != b"VBKV":
        raise ValueError("not a VBKV file")
    pos = 8

    def cstr():
        nonlocal pos
        end = b.index(b"\x00", pos)
        s = b[pos:end].decode("utf-8", "replace")
        pos = end + 1
        return s

    def node():
        nonlocal pos
        out = {}
        while pos < len(b):
            t = b[pos]
            pos += 1
            if t in (0x08, 0x0B):
                return out
            key = cstr()
            if t == 0x00:
                out[key] = node()
            elif t == 0x01:
                out[key] = cstr()
            elif t in (0x02, 0x03):
                out[key] = struct.unpack_from("<i" if t == 2 else "<f", b, pos)[0]
                pos += 4
            elif t in (0x07, 0x0A):
                out[key] = struct.unpack_from("<Q" if t == 7 else "<q", b, pos)[0]
                pos += 8
            else:
                raise ValueError(f"unknown VBKV type {t:#x}")
        return out
    return node()


def personal_records(cfg_dir):
    """hero_id -> (wins, losses, lifetime WR edge vs your own average, shrunk for sample size)."""
    try:
        st = parse_vbkv((cfg_dir / "stats.dat").read_bytes())["Stats"]["hero_standings"]["standings"]
    except Exception:
        return {}
    rows = [(v["hero_id"], v.get("wins", 0), v.get("losses", 0)) for v in st.values()]
    rows = [r for r in rows if r[1] + r[2] > 0]
    if sum(w + l for _, w, l in rows) < 100:
        return {}
    m, n0, _ = eb_prior([(w, w + l) for _, w, l in rows], min_n=30)
    return {h: (w, l, (w + m * n0) / (w + l + n0) - m) for h, w, l in rows}


# ---- statistics ------------------------------------------------------------------------
def eb_prior(rows, min_n=150):
    """Beta prior by method of moments: observed variance minus sampling variance."""
    fit = [(w, n) for w, n in rows if n >= min_n]
    if len(fit) < 8:
        return 0.5, 400.0, 0.025 ** 2
    m = sum(w for w, _ in fit) / sum(n for _, n in fit)
    ps = [w / n for w, n in fit]
    # floor at a 1pp spread: a tiny or stale sample can make the estimate collapse to ~0, which
    # would shrink every hero onto the mean and leave the personal record to order the row
    vt = max(stt.pvariance(ps) - stt.mean(p * (1 - p) / n for p, (_, n) in zip(ps, fit)), 0.01 ** 2)
    return m, m * (1 - m) / vt - 1, vt


def high_mmr_edges(pre, post, changed):
    """hero -> (edge vs role mean, sd) from Immortal data. Pre-patch games form a prior that is
    widened by the expected patch drift and then updated with post-patch games. With no
    pre-patch days in the window this is plain shrinkage of the post-patch numbers."""
    have_pre = sum(n for _, n in pre.values()) > 0
    m, n0, _ = eb_prior(list((pre if have_pre else post).values()))
    out = {}
    for h in set(pre) | set(post):
        wq, nq = post.get(h, (0, 0))
        if not have_pre:
            mu = (wq + m * n0) / (nq + n0)
            out[h] = (mu - m, math.sqrt(mu * (1 - mu) / (nq + n0)))
            continue
        wp, np_ = pre.get(h, (0, 0))
        mu = (wp + m * n0) / (np_ + n0)
        tau = TAU_CHANGED if h in changed else TAU_UNCHANGED
        var = mu * (1 - mu) / (np_ + n0) + tau * tau
        if nq > 0:
            pf = (wq + 0.5) / (nq + 1)
            vf = pf * (1 - pf) / nq
            mu, var = (mu / var + pf / vf) / (1 / var + 1 / vf), 1 / (1 / var + 1 / vf)
        out[h] = (mu - m, math.sqrt(var))
    return out


def bracket_winrates(od, bracket):
    """hero -> all-role win rate over the last 7 days in the player's own OpenDota bracket."""
    while bracket >= 1 and not sum(h.get(f"{bracket}_pick") or 0 for h in od):
        bracket -= 1                       # e.g. the Immortal bucket is empty in OpenDota
    if bracket < 1:
        return {}
    return {h["id"]: h[f"{bracket}_win"] / h[f"{bracket}_pick"] for h in od if (h.get(f"{bracket}_pick") or 0) >= 200}


# ---- input parsing ---------------------------------------------------------------------
def parse_rank(text):
    if text is None:
        return None
    t = str(text).lower().replace(",", "")
    for i, name in enumerate(MEDALS):
        if name in t:
            return i + 1
    k = re.search(r"(\d+(?:\.\d+)?)\s*k\b", t)
    num = re.search(r"\d+", t)
    if not (k or num):
        die(f"--rank: give an MMR number (e.g. 3400) or a medal ({', '.join(MEDALS)})")
    mmr = float(k.group(1)) * 1000 if k else int(num.group())
    return max(i + 1 for i, floor in enumerate(MMR_FLOORS) if mmr >= floor)


def parse_roles(text):
    roles = sorted({int(c) for c in re.findall(r"[1-5]", text or "")})
    if not roles or re.search(r"[06-9]", text or ""):
        die("--roles: list positions 1-5, e.g. --roles 4,5")
    return roles


def resolve_hero(typed, names):
    by_fold = {n.casefold(): n for n in names.values()}
    t = typed.strip().casefold()
    if t in by_fold:
        return by_fold[t]
    hits = [n for f, n in by_fold.items() if t and (t in f or f in t)]
    if len(hits) != 1:
        hits = [by_fold[f] for f in difflib.get_close_matches(t, by_fold, n=3, cutoff=0.75)]
    if len(hits) == 1:
        return hits[0]
    die(f"unknown hero '{typed}'" + (f" - did you mean: {', '.join(hits)}?" if hits else
                                     ". Use the hero name exactly as it appears in the output."))


def parse_decisions(specs, names):
    """'4:Disruptor,Silencer' or '4:Disruptor,5:Abaddon' -> [(role, hero)]"""
    out = []
    for spec in specs or []:
        role = None
        for token in spec.split(","):
            m = re.match(r"^\s*(?:pos\s*)?([1-5])\s*:\s*(.*)$", token, re.I)
            if m:
                role, token = m.group(1), m.group(2)
            if not token.strip():
                continue
            if role is None:
                die(f"'{spec}': start with the position, e.g. \"4:Disruptor,Silencer\"")
            out.append((role, resolve_hero(token, names)))
    return out


def load_decisions():
    try:
        d = json.loads((STATE / "decisions.json").read_text(encoding="utf-8"))
    except Exception:
        d = {}
    return {"allow": d.get("allow", {}), "deny": d.get("deny", {})}


def save_decisions(allow, deny, forget):
    d = load_decisions()
    for key, pairs in (("allow", allow), ("deny", deny), (None, forget)):
        for role, hero in pairs:
            for k in ("allow", "deny"):
                d[k][role] = sorted(set(d[k].get(role, [])) - {hero})
            if key:
                d[key][role] = sorted(set(d[key].get(role, [])) | {hero})
            print(f"saved: {key or 'forget'} pos {role} {hero}", file=sys.stderr)
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "decisions.json").write_text(json.dumps(d, indent=2), encoding="utf-8")


# ---- main ------------------------------------------------------------------------------
def pp(x):
    return None if x is None else round(100 * x, 2)


def build(cfg_dir, bracket, roles, per_role, personal_weight, refresh, od=None):
    patch, patch_ts, changed = latest_patch(refresh)
    patch_day = dt.datetime.fromtimestamp(patch_ts, dt.timezone.utc).strftime("%Y-%m-%d")
    patch_age = (time.time() - patch_ts) / 86400
    od = od or fetch_json("https://api.opendota.com/api/heroStats", refresh)
    names = {h["id"]: h["localized_name"] for h in od}
    own = bracket_winrates(od, bracket) if bracket and bracket < 8 else {}
    transfer = TRANSFER[bracket] if bracket else 1.0
    me = personal_records(cfg_dir) if cfg_dir else {}     # weight 0 still shows the record, adds nothing
    decisions = load_decisions()

    cur_rep, prev_rep = spectral_reports(patch_ts, refresh)
    if not cur_rep and patch_age >= PRIOR_DAYS:
        die(f"stats.spectral.gg has no report for patch {patch} yet, {patch_age:.0f} days after release. "
            "Try again later.")
    sig = hero_signals(cur_rep or prev_rep, refresh)
    res = {"patch": patch, "patch_age_days": round(patch_age, 1), "provisional": patch_age < 5,
           "rank_bracket": MEDALS[bracket - 1] if bracket else None, "transfer": transfer,
           "personal_heroes": len(me), "saved_decisions": decisions, "units": "all *_pp fields are "
           "win-rate percentage points vs an average hero in the role",
           "reports": {"current": cur_rep and cur_rep[0], "prior": None, "signals": (cur_rep or prev_rep)[0]},
           "roles": {}}
    # While the patch is young, the previous patch's report is the prior, scaled down to the
    # games of the pre-patch part of an 8-day window (the setup the method was tested on).
    prior_w = 0.0
    if prev_rep and patch_age < PRIOR_DAYS:
        prior_w = min(1.0, (PRIOR_DAYS - patch_age) / max(prev_rep[1], 1.0))
        res["reports"]["prior"] = prev_rep[0]
    for r in roles:
        pos, label = ROLES[r]
        post = role_games(cur_rep[0], r, refresh) if cur_rep else {}
        pre = {h: (w * prior_w, n * prior_w) for h, (w, n) in role_games(prev_rep[0], r, refresh).items()} \
            if prior_w else {}
        games = {h: pre.get(h, (0, 0))[1] + post.get(h, (0, 0))[1] for h in set(pre) | set(post)}
        total = sum(games.values()) or 1
        share = {h: n / total for h, n in games.items()}
        high = high_mmr_edges(pre, post, changed)

        allow = set(decisions["allow"].get(str(r), []))
        deny = set(decisions["deny"].get(str(r), []))
        rows, denied, vetoed = [], [], []
        for h, (edge, sd) in high.items():
            if h not in names or share.get(h, 0) < ROLE_SHARE_FLOOR:
                continue
            if names[h] in deny:
                denied.append(names[h])
                continue
            w, l, pe = me.get(h, (0, 0, 0.0))
            adj = max(-PERSONAL_CAP, min(PERSONAL_CAP, personal_weight * pe)) if personal_weight else 0.0
            niche = share[h] < NICHE_SHARE
            weak = h in own and own[h] < VETO_WR      # losing in the player's own bracket
            s = sig.get(h, {})
            gap = s["average"] - s["newcomer"] if "newcomer" in s else None
            row = {"hero_id": h, "hero": names[h], "score_pp": pp(edge + adj), "meta_pp": pp(edge),
                   "noise_pp": pp(sd), "own_bracket_winrate_pct": pp(own.get(h)),
                   "personal_adj_pp": pp(adj), "personal_record": f"{w}-{l}",
                   "role_pick_share_pct": round(100 * share[h], 1), "changed_this_patch": h in changed,
                   "niche_status": (("approved" if names[h] in allow else "undecided") if niche else None),
                   "ban_rate_pct": pp(s.get("ban")), "newcomer_winrate_pct": pp(s.get("newcomer")),
                   "learning_gap_pp": pp(gap),
                   "hard_and_new_to_you": (gap is not None and gap >= HARD_GAP and w + l < NEW_TO_YOU) if me else None}
            (vetoed if weak else rows).append(row)
        rows.sort(key=lambda x: -x["score_pp"])
        res["roles"][str(r)] = {
            "label": label, "picks": rows[:per_role], "bench": rows[per_role:per_role + 5], "denied": sorted(denied),
            "vetoed_weak_in_your_bracket": [f"{x['hero']} ({x['own_bracket_winrate_pct']:.1f}%)" for x in
                                            sorted(vetoed, key=lambda x: -x["score_pp"])
                                            if rows[:per_role] and x["score_pp"] > rows[:per_role][-1]["score_pp"]],
            "sample_matches": {"pre_patch": int(sum(n for _, n in pre.values()) // 2),
                               "post_patch": int(sum(n for _, n in post.values()) // 2)}}
    res["all_heroes"] = sorted(names, key=lambda i: names[i])
    return res


def print_table(res):
    rank = res["rank_bracket"] or "not given (using Immortal numbers as-is)"
    print(f"patch {res['patch']} ({res['patch_age_days']} days old) | rank: {rank} | "
          f"personal record: {res['personal_heroes']} heroes")
    if res["provisional"]:
        print("note: the patch is under 5 days old - estimates are provisional, re-run in a few days.")
    if res["rank_bracket"] and res["transfer"] < 0.7:
        print(f"note: win rates come from Immortal ranked games. At {res['rank_bracket']} only about "
              f"{round(100 * res['transfer'])}% of such an edge carries over - treat the list as a starting point; "
              "heroes that lose in your own bracket are already removed.")
    for role in res["roles"].values():
        m = role["sample_matches"]
        print(f"\n{role['label']}   [sample: {m['pre_patch']} matches before the patch, {m['post_patch']} since]")
        print(f"   {'hero':<20}     score  +-noise | Immortal WR edge    | your bracket WR | your record  "
              "| role pick share | banned")
        for x in role["picks"]:
            flag = ("*" if x["changed_this_patch"] else " ") + {"undecided": "?", "approved": "~", None: " "}[x["niche_status"]] \
                + ("!" if x["hard_and_new_to_you"] else " ")
            own = f"{x['own_bracket_winrate_pct']:.1f}%" if x["own_bracket_winrate_pct"] is not None else "n/a"
            ban = f"{x['ban_rate_pct']:.0f}%" if x["ban_rate_pct"] is not None else "n/a"
            print(f"   {x['hero']:<20}{flag} {x['score_pp']:+5.1f}pp +-{x['noise_pp']:.1f} | {x['meta_pp']:+18.1f}  | "
                  f"{own:>14}  | {x['personal_record']:>7} {x['personal_adj_pp']:+.1f} | "
                  f"{x['role_pick_share_pct']:>14.1f}% | {ban:>6}")
        hard = [x for x in role["picks"] if x["hard_and_new_to_you"]]
        if hard:
            print("   ! hard to learn and new to you: " + ", ".join(
                f"{x['hero']} (newcomers win {x['newcomer_winrate_pct']:.1f}%, "
                f"{x['learning_gap_pp']:.0f}pp under its average; you {x['personal_record']})" for x in hard))
        if role["vetoed_weak_in_your_bracket"]:
            print("   removed (losing in your bracket): " + ", ".join(role["vetoed_weak_in_your_bracket"]))
        if role["denied"]:
            print("   skipped (you said you don't play them here): " + ", ".join(role["denied"]))
    print("\n* changed in this patch   ~ niche pick you approved   ? niche pick (<1% of the role's picks): "
          "do you play it? answer with --allow / --deny\n"
          f"! hard to learn (newcomers trail its average by {round(100 * HARD_GAP)}pp+) and you have under "
          f"{NEW_TO_YOU} games on it   banned = share of games where the hero is banned (all roles)")


def dota_running():
    try:
        if sys.platform == "win32":
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq dota2.exe"], capture_output=True).stdout
            return b"dota2.exe" in out.lower()
        return subprocess.run(["pgrep", "-x", "dota2"], capture_output=True).returncode == 0
    except Exception:
        return False


def write_grid(cfg_dir, res, log=print):
    tag = f" [{SPONSOR_TAG}]"
    path = cfg_dir / "hero_grid_config.json"
    grid = {"version": 3, "configs": []}
    if path.exists():
        grid = json.loads(path.read_text(encoding="utf-8-sig"))
        (STATE / "backups").mkdir(parents=True, exist_ok=True)
        bak = STATE / "backups" / f"hero_grid_config.{dt.datetime.now():%Y%m%d-%H%M%S-%f}.json"
        shutil.copy2(path, bak)
        log(f"backup -> {bak}")
    cats = [{"category_name": role["label"] + tag, "x_position": 0, "y_position": 95 * i, "width": 455,
             "height": 75, "hero_ids": [x["hero_id"] for x in role["picks"]]}
            for i, role in enumerate(res["roles"].values())]
    cats.append({"category_name": "All Heroes", "x_position": 500, "y_position": 0, "width": 600,
                 "height": 600, "hero_ids": res["all_heroes"]})
    name = f"Meta Grid {res['patch']} ({dt.date.today():%d %b})"
    assert OUR_CONFIG.match(name), name
    grid["configs"] = [{"config_name": name, "categories": cats}] + [
        c for c in grid.get("configs", []) if not OUR_CONFIG.match(str(c.get("config_name", "")))]
    path.write_text(json.dumps(grid, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    log(f"wrote '{name}' -> {path}")


def main():
    ap = argparse.ArgumentParser(description="Build a Dota 2 hero grid of the best heroes per role for your rank.")
    ap.add_argument("--rank", help="your MMR (e.g. 3400) or medal (e.g. legend)")
    ap.add_argument("--roles", default="1,2,3,4,5", help="positions to include, e.g. 4,5")
    ap.add_argument("--per-role", type=int, default=7)
    ap.add_argument("--personal-weight", type=float, default=PERSONAL_WEIGHT, help="0 ignores your own hero record")
    ap.add_argument("--allow", action="append", metavar="POS:Hero,Hero", help="niche picks you do play (saved)")
    ap.add_argument("--deny", action="append", metavar="POS:Hero,Hero", help="heroes you won't play in that role (saved)")
    ap.add_argument("--forget", action="append", metavar="POS:Hero,Hero", help="remove a saved --allow/--deny answer")
    ap.add_argument("--write", action="store_true", help="write the grid file (Dota must be closed)")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    ap.add_argument("--refresh", action="store_true", help=f"ignore the {CACHE_HOURS}h download cache")
    ap.add_argument("--list-accounts", action="store_true")
    ap.add_argument("--account", help="Steam account id (default: most recently used)")
    ap.add_argument("--steam-dir", help="Steam install folder, if it is not found automatically")
    ap.add_argument("--cfg-dir", help="explicit .../570/remote/cfg folder (overrides detection)")
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    if a.list_accounts:
        for acc, cfg, ts in accounts(a.steam_dir):
            grid = "has a grid file" if (cfg / "hero_grid_config.json").exists() else "no grid file yet"
            print(f"{acc}  last used {dt.datetime.fromtimestamp(ts):%Y-%m-%d}  ({grid})  {cfg}")
        return
    roles, bracket = parse_roles(a.roles), parse_rank(a.rank)
    if not 1 <= a.per_role <= 12:
        die("--per-role: choose between 1 and 12")

    cfg_dir = Path(a.cfg_dir) if a.cfg_dir else None
    if cfg_dir and not cfg_dir.is_dir():
        die(f"--cfg-dir: {cfg_dir} does not exist")
    if not cfg_dir:
        accs = accounts(a.steam_dir)
        if a.account:
            accs = [x for x in accs if x[0] == str(a.account)] or die(
                f"--account {a.account}: no such Steam account here. Run --list-accounts.")
        cfg_dir = accs[0][1] if accs else None
    if a.write and not cfg_dir:
        die("could not find Dota's config folder. Pass --steam-dir <Steam folder> or --cfg-dir "
            "<.../Steam/userdata/<id>/570/remote/cfg>. It exists once Dota has been launched on this machine.")

    od = fetch_json("https://api.opendota.com/api/heroStats", a.refresh)
    if a.allow or a.deny or a.forget:
        names = {h["id"]: h["localized_name"] for h in od}
        save_decisions(*(parse_decisions(s, names) for s in (a.allow, a.deny, a.forget)))

    res = build(cfg_dir, bracket, roles, a.per_role, a.personal_weight, a.refresh, od)
    res["cfg_dir"] = str(cfg_dir) if cfg_dir else None
    print(json.dumps(res, indent=1)) if a.json else print_table(res)
    log = (lambda m: print(m, file=sys.stderr)) if a.json else print
    if a.write:
        if dota_running():
            die("Dota 2 is running - close it first, it can overwrite the grid file on exit.")
        write_grid(cfg_dir, res, log)
    elif not a.json:
        print("\ndry run - nothing written. Add --write (same options) once Dota is closed.")


if __name__ == "__main__":
    main()
