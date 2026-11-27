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
from survivor_data import build_season, load_tables, REVIEW_KINDS

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
    overrides = _load(P("overrides", f"season{n}.json")) or {}
    try:  # commissioner decisions from the review screen (Firestore, or the saved copy)
        from sync_draft import fetch_review
        review = fetch_review(n)
    except Exception as e:
        print(f"review: S{n} decisions unavailable ({e})")
        review = None
    if review:
        overrides = {**overrides, "decisions": {**overrides.get("decisions", {}), **review["decisions"]},
                     "adjust": [*overrides.get("adjust", []), *review["adjust"]]}
    season = build_season(n, league["first_week_boot"], tables, overrides=overrides or None,
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
                          for x in w.get("specials", [])],
             "adjustments": [{"player": s(a["player"]), "category": a["category"], "points": a["points"],
                              "reason": a.get("reason", "")} for a in w.get("adjustments", [])]}
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
        # judgment calls for the review screen (info-only items left out)
        "review": [{k: r.get(k) for k in ("id", "kind", "week", "advantage", "event", "castaway", "players",
                                         "played_for", "success", "votes_nullified", "location", "decision")}
                   for r in season.get("review", []) if r.get("kind") in REVIEW_KINDS],
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


def write_rules():
    """docs/data/rules.json: point values straight from the scoring engine, so the
    Rules page always matches how points are actually scored."""
    from scoring import RULES
    json.dump(RULES, open(P("docs", "data", "rules.json"), "w"), indent=1)


AGE_GROUPS = [(0, 30, "Under 30"), (30, 40, "30s"), (40, 50, "40s"), (50, 200, "50+")]


def write_owners(tables):
    """docs/data/owners.json: per-owner record, top players and what kinds of
    players score for them. Uses every non-test season on the site. Season totals
    and wins are the career numbers (official through S47); contestant points
    are the recalculated per-contestant scores."""
    career = _load(P("docs", "data", "career.json")) or {"seasons": []}
    official = {s["season"]: s for s in career["seasons"]}
    details = {r["castaway_id"]: r for r in tables.get("castaway_details", [])}
    by_season_cast = {}
    first_season = {}
    for r in tables["castaways"]:
        if r.get("version") != "US":
            continue
        by_season_cast[(r["season"], r["castaway_id"])] = r
        first_season[r["castaway_id"]] = min(first_season.get(r["castaway_id"], 999), r["season"])

    def traits(cid, season):
        d = details.get(cid, {})
        row = by_season_cast.get((season, cid), {})
        age = row.get("age")
        mbti = d.get("personality_type") or ""
        collar = d.get("collar")
        return {
            "Gender": {"Male": "Men", "Female": "Women"}.get(d.get("gender")),
            "Age": next((lbl for lo, hi, lbl in AGE_GROUPS if age is not None and lo <= age < hi), None),
            "Experience": None if cid not in first_season else ("First-timers" if first_season[cid] == season else "Returning players"),
            "Personality": {"I": "Introverts", "E": "Extroverts"}.get(mbti[:1]) if mbti else None,
            "Job": collar if collar in ("White collar", "Blue collar", "No collar") else None,
        }

    owners = {}
    for path in sorted(glob.glob(P("docs", "data", "season*.json"))):
        d = _load(path)
        if not d or d.get("test"):
            continue
        n = d["season"]
        fx = _load(P("fixtures", f"survivoR_season{n}.json")) or {"contestants": []}
        ids = {c["short"]: c["id"] for c in fx["contestants"]}
        cs = {c["name"]: c for c in d["contestants"]}
        car = official.get(n, {})
        totals = car.get("totals") or {o["name"]: o["total"] for o in d["owners"]}
        ranked = sorted(totals, key=lambda o: -totals[o])
        for o in d["owners"]:
            rec = owners.setdefault(o["name"], {"name": o["name"], "slot": o["slot"], "seasons": [], "picks": []})
            rec["seasons"].append({"season": n, "total": totals.get(o["name"], o["total"]),
                                   "rank": ranked.index(o["name"]) + 1 if o["name"] in ranked else None,
                                   "of": len(ranked), "won": car.get("winner") == o["name"],
                                   "source": car.get("source", "calculated"), "complete": d.get("complete", True)})
            for name in o["roster"]:
                c = cs.get(name)
                if not c:
                    continue
                cats = {k: sum(w[k] for w in c["weekly"]) for k in ("challenges", "votes", "survival", "special")}
                rec["picks"].append({"season": n, "name": name, "full_name": c["full_name"], "points": c["total"],
                                     "cats": cats, "place": c.get("place"), "status": c["status"]["kind"],
                                     "traits": traits(ids.get(name), n)})

    # Seasons differ a lot in length (S50 scored 21 eliminations), so compare picks
    # by an index: 100 = the average owned pick that season.
    season_avg = {}
    for o in owners.values():
        for p in o["picks"]:
            season_avg.setdefault(p["season"], []).append(p["points"])
    season_avg = {s: sum(v) / len(v) for s, v in season_avg.items()}
    for o in owners.values():
        for p in o["picks"]:
            avg = season_avg.get(p["season"]) or 0
            p["index"] = round(100 * p["points"] / avg) if avg > 0 else None

    def group_stats(picks):
        out = {}
        for dim in ("Gender", "Age", "Experience", "Personality", "Job"):
            groups = {}
            for p in picks:
                g = p["traits"].get(dim)
                if g and p.get("index") is not None:
                    groups.setdefault(g, []).append(p["index"])
            out[dim] = {g: {"n": len(v), "avg": round(sum(v) / len(v), 1)} for g, v in groups.items()}
        return out

    def mix(picks):
        tot = {k: sum(p["cats"][k] for p in picks) for k in ("challenges", "votes", "survival", "special")}
        s = sum(abs(v) for v in tot.values()) or 1
        return {k: round(100 * v / s, 1) for k, v in tot.items()}

    all_picks = [p for o in owners.values() for p in o["picks"]]
    out = []
    for o in sorted(owners.values(), key=lambda o: o["slot"]):
        picks = o["picks"]
        seasons = sorted(o["seasons"], key=lambda s: s["season"])
        done = [s for s in seasons if s["complete"]]
        out.append({
            "name": o["name"], "slot": o["slot"], "seasons": seasons,
            "wins": [s["season"] for s in seasons if s["won"]],
            "total": sum(s["total"] for s in seasons),
            "best": max(done, key=lambda s: s["total"], default=None),
            "worst": min(done, key=lambda s: s["total"], default=None),
            "picks_count": len(picks),
            "avg_pick": round(sum(p["points"] for p in picks) / len(picks), 1) if picks else 0,
            "avg_index": round(sum(p["index"] for p in picks if p.get("index") is not None)
                               / max(1, sum(1 for p in picks if p.get("index") is not None))),
            "winners_drafted": [p["season"] for p in picks if p["place"] == 1],
            "top_players": [{k: p[k] for k in ("season", "name", "full_name", "points", "place", "status", "index")}
                            for p in sorted(picks, key=lambda p: -p["points"])[:10]],
            "best_value": [{k: p[k] for k in ("season", "name", "full_name", "points", "place", "status", "index")}
                           for p in sorted((p for p in picks if p.get("index") is not None), key=lambda p: -p["index"])[:5]],
            "groups": group_stats(picks), "mix": mix(picks),
        })
    league = {"avg_pick": round(sum(p["points"] for p in all_picks) / len(all_picks), 1) if all_picks else 0,
              "groups": group_stats(all_picks), "mix": mix(all_picks)}
    json.dump({"owners": out, "league": league}, open(P("docs", "data", "owners.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return out


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
    write_rules()
    owners = write_owners(tables)
    summary = ", ".join("%s %d seasons" % (o["name"], len(o["seasons"])) for o in owners)
    print("owners: " + summary)
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
