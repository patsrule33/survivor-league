"""Score each league season and write the static site's data files.

    python build_site.py --refresh --current  # just the season now airing (the daily job)
    python build_site.py 51 --refresh         # one season, re-download survivoR first

FINISHED SEASONS ARE FROZEN: once a season's site data says it's complete, it is
never rescored again, even if the scoring rules change later (rule changes apply
to future seasons only). Owner ruling 2026-11-25.

Inputs per season:
  leagues/seasonNN.json    owners + rosters (survivoR short names), first_week_boot
  overrides/seasonNN.json  owner decisions from the review screen (optional)
Outputs:
  fixtures/survivoR_seasonNN.json  the season the engine scored
  docs/data/seasonNN.json          everything the site shows
  docs/data/index.json             list of seasons, newest first
GitHub Pages serves docs/.
"""
import argparse, datetime, glob, json, os, re, urllib.request
from collections import Counter
from scoring import score_season
from survivor_data import build_season, load_tables

ROOT = os.path.dirname(os.path.abspath(__file__))
P = lambda *a: os.path.join(ROOT, *a)
CATS = ["challenges", "votes", "survival", "special"]
# Each owner keeps one color slot in every season (color follows the person, never rank).
OWNER_SLOTS = {"Jamie": 1, "Mom": 2, "Will": 3, "Greg": 4, "Jimmy": 5}


def owner_slot(name):
    if name not in OWNER_SLOTS:
        OWNER_SLOTS[name] = max(OWNER_SLOTS.values()) + 1
    return OWNER_SLOTS[name]
CHALLENGE_LABEL = {
    "tribal_immunity_1": "Tribal immunity (1st)", "tribal_immunity_2": "Tribal immunity (2nd)",
    "tribal_reward_1": "Tribal reward (1st)", "tribal_reward_2": "Tribal reward (2nd)",
    "indiv_immunity": "Individual immunity", "indiv_reward": "Individual reward",
    "group_immunity": "Group immunity",
}
SPECIAL_LABEL = {
    "idol_found": "Found an idol", "advantage_used": "Used an advantage",
    "idol_in_pocket": "Voted out holding an idol", "medevac_pity": "Medevac",
}


def _load(path):
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    return None


def keep_stamp(path, data, stamp, ignore=()):
    """If nothing but the timestamp (and `ignore` keys) changed since the file on
    disk, reuse the old timestamp. Keeps scheduled runs from committing no-op
    changes, and keeps "last built" meaning "last changed"."""
    old = _load(path)
    if old is None:
        return data
    skip = {stamp, *ignore}
    new = json.loads(json.dumps(data))  # same types as the file (tuples -> lists)
    if {k: v for k, v in old.items() if k not in skip} == {k: v for k, v in new.items() if k not in skip}:
        data[stamp] = old.get(stamp, data[stamp])
    return data


def site_season(league, tables):
    n = league["season"]
    overrides = _load(P("overrides", f"season{n}.json"))
    season = build_season(n, league["first_week_boot"], tables, overrides=overrides,
                          survival_offset=league.get("survival_offset", 0))
    json.dump(season, open(P("fixtures", f"survivoR_season{n}.json"), "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)
    scores = score_season(season)
    short = {c["name"]: c["short"] for c in season["contestants"]}
    finish = {c["name"]: c.get("place") for c in season["contestants"]}
    s = lambda full: short.get(full, full)
    weeks = season["weeks"]
    n_weeks = len(weeks)

    owners_of = {}  # a contestant can be on two rosters (S49 double picks)
    for o in league["owners"]:
        for c in o["roster"]:
            owners_of.setdefault(c, []).append(o["name"])

    # contestant status
    out_week = {s(w["eliminated"]): w["week"] for w in weeks}
    place = {s(f): i + 1 for i, f in enumerate(season["final_placement"])}
    forfeit = {s(f) for f in season.get("forfeit", [])}

    contestants = []
    for full, wk in scores.items():
        c = s(full)
        weekly = [{k: wk[i][k] for k in CATS + ["total"]} for i in range(1, n_weeks + 1)]
        if c in forfeit:
            status = {"kind": "quit", "week": out_week.get(c)}
        elif c in place:
            status = {"kind": "winner" if place[c] == 1 else "finalist", "place": place[c]}
        elif c in out_week:
            status = {"kind": "out", "week": out_week[c]}
        else:
            status = {"kind": "in"}
        contestants.append({"name": c, "full_name": full, "owners": owners_of.get(c, []),
                            "status": status, "place": finish.get(full), "weekly": weekly,
                            "total": sum(w["total"] for w in weekly)})
    contestants.sort(key=lambda c: -c["total"])
    by_name = {c["name"]: c for c in contestants}

    missing = [c for o in league["owners"] for c in o["roster"] if c not in by_name]
    if missing:
        print(f"  warning S{n}: rostered but not in the scored pool (out before first_week_boot?): {missing}")
    owners = []
    for o in sorted(league["owners"], key=lambda o: owner_slot(o["name"])):
        weekly = [sum(by_name[c]["weekly"][k]["total"] for c in o["roster"] if c in by_name)
                  for k in range(n_weeks)]
        cum, run = [], 0
        for v in weekly:
            run += v; cum.append(run)
        alive = sum(1 for c in o["roster"] if by_name.get(c, {}).get("status", {}).get("kind") in ("in", "finalist", "winner"))
        owners.append({"name": o["name"], "slot": owner_slot(o["name"]), "roster": o["roster"], "weekly": weekly,
                       "cumulative": cum, "total": run, "alive": alive})
    ranked = sorted(owners, key=lambda o: -o["total"])
    for r, o in enumerate(ranked):
        o["rank"] = r + 1
    # rank movement is computed in the browser (it depends on elimination vs episode view)

    # per-week story
    week_detail = []
    for w in weeks:
        d = {"week": w["week"], "episode": w["episode"], "eliminated": s(w["eliminated"]),
             "challenges": [{"label": CHALLENGE_LABEL.get(c["type"], c["type"]),
                             "players": [s(p) for p in c["players"]]} for c in w.get("challenges", [])],
             "specials": [{"label": SPECIAL_LABEL.get(x["type"], x["type"]), "player": s(x["player"])}
                          for x in w.get("specials", [])]}
        council = w.get("council")
        if council:
            d["rounds"] = [sorted(Counter(s(b["target"]) for b in r if not b.get("negated")).items(),
                                  key=lambda kv: -kv[1]) for r in council["rounds"]]
            d["idol_plays"] = [{"player": s(p["player"]), "votes_negated": p["votes_negated"]}
                               for p in council.get("idol_plays", [])]
        if w.get("jury"):
            d["jury"] = sorted(Counter(s(v) for v in w["jury"].values()).items(), key=lambda kv: -kv[1])
        week_detail.append(d)

    return {
        "season": n, "title": season["title"], "league": league.get("league", ""),
        "test": bool(league.get("test")),  # test draft: shown, labelled, never counted all-time
        "first_week_boot": league["first_week_boot"],
        "built": datetime.datetime.now().isoformat(timespec="minutes"),
        "complete": bool(season["final_placement"]),
        "owners": owners, "contestants": contestants, "weeks": week_detail,
        "review_count": len(season.get("review", [])),
    }


def write_live(tables, version="US"):
    """docs/data/live.json: the newest season's cast for the draft room — who is
    still in the game, their current tribe (and its color), and boots so far."""
    cast = [c for c in tables["castaways"] if c.get("version") == version]
    n = max(c["season"] for c in cast)
    vs = f"{version}{n}"
    rows = {}
    for c in cast:
        if c["version_season"] == vs:
            rows[c["castaway_id"]] = c
    latest = {}
    for r in tables["boot_mapping"]:
        if r.get("version_season") == vs and r.get("sog_id") is not None:
            if r["castaway_id"] not in latest or r["sog_id"] > latest[r["castaway_id"]]["sog_id"]:
                latest[r["castaway_id"]] = r
    colour = {r["tribe"]: r.get("tribe_colour") for r in tables.get("tribe_colours", []) if r.get("version_season") == vs}
    eps = [e for e in tables.get("episodes", []) if e.get("version_season") == vs]
    out = []
    for cid, c in rows.items():
        b = latest.get(cid, {})
        gone = bool(c.get("order"))
        out.append({"name": c["castaway"], "full_name": c["full_name"], "id": cid,
                    "in_game": not gone, "boot": c.get("order") or None, "result": c.get("result"),
                    "tribe": None if gone else b.get("tribe"), "tribe_colour": None if gone else colour.get(b.get("tribe")),
                    "game_status": None if gone else b.get("game_status")})
    out.sort(key=lambda x: (not x["in_game"], x["tribe"] or "", x["name"]))
    boots = max((x["boot"] or 0 for x in out), default=0)
    live = {"season": n, "title": f"Survivor {n}", "boots_so_far": boots,
            "episodes_aired": max((e["episode"] for e in eps), default=0),
            "updated": datetime.datetime.now().isoformat(timespec="minutes"), "cast": out,
            "owners": sorted(OWNER_SLOTS, key=OWNER_SLOTS.get)}
    path = P("docs", "data", "live.json")
    json.dump(keep_stamp(path, live, "updated"), open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return live


def write_meta(live):
    """docs/data/meta.json: when survivoR itself was last updated (its last commit to
    dev/json, from the GitHub API) and how far its data goes, for the site footer."""
    meta_path = P("docs", "data", "meta.json")
    old = _load(meta_path) or {}
    updated = old.get("survivor_updated")
    try:
        url = "https://api.github.com/repos/doehm/survivoR/commits?path=dev/json&per_page=1"
        req = urllib.request.Request(url, headers={"User-Agent": "survivor-fantasy-league-site"})
        try:  # certifi's CA list, if installed (some Windows stores lack GitHub's intermediate)
            import certifi, ssl
            ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            ctx = None
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            updated = json.load(r)[0]["commit"]["committer"]["date"]
    except Exception as e:  # keep the last known date if GitHub can't be reached
        print(f"meta: couldn't read survivoR's last update ({e}); keeping {updated}")
    meta = {"survivor_updated": updated, "through_season": live["season"],
            "through_episode": live["episodes_aired"],
            "built": datetime.datetime.now().isoformat(timespec="minutes")}
    json.dump(keep_stamp(meta_path, meta, "built"), open(meta_path, "w"), indent=1)
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("seasons", nargs="*", type=int)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--current", action="store_true", help="only score the season now airing")
    a = ap.parse_args()
    try:  # finished drafts from the draft room -> league files
        from sync_draft import sync
        sync()
    except Exception as e:  # never block a scoring run on the draft room
        print(f"sync_draft failed: {e}")
    files = sorted(glob.glob(P("leagues", "season*.json")))
    leagues = [json.load(open(f, encoding="utf-8")) for f in files]
    if a.seasons:
        leagues = [l for l in leagues if l["season"] in a.seasons]
    tables = load_tables(a.refresh)
    if a.current:  # only the newest season in survivoR (the one airing)
        airing = max(c["season"] for c in tables["castaways"] if c.get("version") == "US")
        leagues = [l for l in leagues if l["season"] == airing]
        if not leagues:
            print(f"Survivor {airing}: no league rosters yet; updating the draft room's cast only")
    # finished seasons are frozen: never rescore them
    frozen = [l["season"] for l in leagues
              if (_load(P("docs", "data", f"season{l['season']}.json")) or {}).get("complete")]
    if frozen:
        print(f"frozen (finished, never rescored): {', '.join(f'S{n}' for n in frozen)}")
    leagues = [l for l in leagues if l["season"] not in frozen]
    os.makedirs(P("docs", "data"), exist_ok=True)
    for lg in leagues:
        data = site_season(lg, tables)
        path = P("docs", "data", f"season{lg['season']}.json")
        # "official" is added afterwards by write_career, so ignore it when comparing
        data = keep_stamp(path, data, "built", ignore=("official",))
        old = _load(path)
        if old and "official" in old:
            data["official"] = old["official"]
        json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        leader = min(data["owners"], key=lambda o: o["rank"])
        print(f"season {lg['season']}: {len(data['weeks'])} weeks, leader {leader['name']} ({leader['total']:g})")
    # index of every built season
    built = sorted(int(re.findall(r"\d+", os.path.basename(f))[0]) for f in glob.glob(P("docs", "data", "season*.json")))
    index = []
    for n in reversed(built):
        d = json.load(open(P("docs", "data", f"season{n}.json"), encoding="utf-8"))
        index.append({"season": n, "title": d["title"], "complete": d["complete"], "test": bool(d.get("test"))})
    json.dump(index, open(P("docs", "data", "index.json"), "w"), indent=1)

    write_career(built)
    live = write_live(tables)
    print(f"live: Survivor {live['season']}, {sum(c['in_game'] for c in live['cast'])} still in the game")
    meta = write_meta(live)
    print(f"meta: survivoR last updated {meta['survivor_updated']} (through S{meta['through_season']} ep {meta['through_episode']})")


# Career stats count the owner's official sheet totals through this season (they
# decided real winners); later seasons use the engine's totals (the sheets stop
# being complete at S48). Owner ruling 2026-11-25.
OFFICIAL_THROUGH = 47


def write_career(built):
    official = {s["season"]: s["totals"] for s in (_load(P("history", "official_totals.json")) or {}).get("seasons", [])}
    career = []
    for n in sorted(set(built) | {s for s in official if s <= OFFICIAL_THROUGH}):
        d = _load(P("docs", "data", f"season{n}.json"))
        if d and d.get("test"):
            continue  # test drafts never count toward all-time stats
        computed = {o["name"]: o["total"] for o in d["owners"]} if d else None
        use_official = n <= OFFICIAL_THROUGH and official.get(n)
        totals = official[n] if use_official else computed
        if not totals:
            continue
        complete = True if use_official else bool(d and d["complete"])
        winner = max(totals, key=totals.get) if complete else None
        career.append({"season": n, "totals": totals, "source": "official" if use_official else "calculated",
                       "complete": complete, "winner": winner, "calculated": computed})
    json.dump({"owner_slots": OWNER_SLOTS, "official_through": OFFICIAL_THROUGH, "seasons": career},
              open(P("docs", "data", "career.json"), "w"), indent=1)
    # official result on each old season's page
    for s in career:
        path = P("docs", "data", f"season{s['season']}.json")
        if s["source"] == "official" and os.path.exists(path):
            d = json.load(open(path, encoding="utf-8"))
            d["official"] = sorted(([k, v] for k, v in s["totals"].items()), key=lambda kv: -kv[1])
            json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main()
