"""Build a season JSON (the shape scoring.py reads) from the survivoR dataset.

Source: github.com/doehm/survivoR (MIT). Tables are read straight from the
repo's dev/json folder and cached in data/survivoR/.

    python survivor_data.py 47 --first-week-boot 4 --overrides overrides/season47.json
    python survivor_data.py 51 --refresh          # in-season: re-download first

A "week" is one elimination event (survivoR boot `order`), starting at the boot
number given by --first-week-boot (the first elimination after the draft).
A medevac or quit is its own week even with no Tribal Council.

Auto-scored: votes, jury votes, challenges, idol found, idol played (votes
nullified), voted out holding an idol, medevac pity, quit (forfeit).
Everything that needs a judgment call goes to `review` in the output and is
NOT scored until an override accepts it (that's the review screen's job).
"""
import argparse, json, os, urllib.request
from collections import Counter, defaultdict

BASE = "https://raw.githubusercontent.com/doehm/survivoR/master/dev/json/"
TABLES = ["castaways", "vote_history", "challenge_results", "challenge_description",
          "advantage_movement", "advantage_details", "jury_votes", "boot_mapping", "tribe_colours",
          "episodes", "castaway_details"]
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "survivoR")


def load_tables(refresh=False, cache=CACHE):
    os.makedirs(cache, exist_ok=True)
    out = {}
    for t in TABLES:
        path = os.path.join(cache, f"{t}.json")
        if refresh or not os.path.exists(path):
            with urllib.request.urlopen(BASE + t + ".json", timeout=120) as r:
                data = r.read()
            with open(path, "wb") as f:
                f.write(data)
        with open(path, encoding="utf-8") as f:
            out[t] = json.load(f)
    return out


def _challenge_types(r):
    """survivoR won_* flags for one castaway in one challenge -> scoring.py challenge types.

    Pre-merge tribal challenges pay by finish (1st/2nd). Team challenges pay as
    tribal before the merge, and as individual reward / group immunity after it.
    A combined Reward/Immunity win in the same scope pays immunity only.
    Sitting out still pays if your side won (owner ruling 2026-11-25)."""
    merged = r.get("tribe_status") == "Merged"
    fin = r.get("order_of_finish")
    out = []
    # (scope, reward type, immunity type); the immunity flag wins within a scope
    for scope, rew_t, imm_t in (
        ("tribal", f"tribal_reward_{fin}", f"tribal_immunity_{fin}"),
        ("team", "indiv_reward" if merged else "tribal_reward_1",
                 "group_immunity" if merged else "tribal_immunity_1"),
        ("individual", "indiv_reward", "indiv_immunity"),
    ):
        if scope == "tribal" and fin not in (1, 2):
            continue
        if r.get(f"won_{scope}_immunity"):
            out.append(imm_t)
        elif r.get(f"won_{scope}_reward"):
            out.append(rew_t)
    return out


# Idols that were handed out rather than found don't earn the +10 find (owner
# ruling 2026-11-25, S44 summit idols); they go to review instead. Idols won at
# Ghost Island / Exile / Island of the Idols still count (the S36 sheet paid Chris).
HANDED_OUT = {"Found at Summit", "Given to player by Mr Beast", "Sent from Edge of Extinction",
              "Created when the three amulets were used together"}


# Review screen: what "award" means for each kind of review item (the default,
# with no decision, is no points).
REVIEW_KINDS = {
    "advantage_played": ("advantage_used", "+5 advantage used"),
    "shared_idol_found": ("idol_found", "+10 idol found (each)"),
    "handed_out_idol": ("idol_found", "+10 idol found"),
    "idol_never_active": ("idol_in_pocket", "−20 voted out holding it"),
}
ADJUST_CATEGORIES = ("challenges", "votes", "survival", "special")


def build_season(season_num, first_week_boot, tables, version="US", overrides=None, survival_offset=0):
    vs = f"{version}{season_num}"
    T = {k: [r for r in v if r.get("version_season") == vs] for k, v in tables.items()}
    if not T["castaways"]:
        raise SystemExit(f"no survivoR data for {vs}")

    cast = {}
    for c in T["castaways"]:  # a returning player can have several rows; keep the latest
        cast[c["castaway_id"]] = c
    name = {cid: c["full_name"] for cid, c in cast.items()}
    short = {c["castaway"]: cid for cid, c in cast.items()}
    to_week = lambda order: order - first_week_boot + 1

    # ---- elimination events -> weeks ----
    elim = sorted((c for c in cast.values() if c.get("order") and not c.get("finalist")),
                  key=lambda c: c["order"])
    elim = [c for c in elim if c["order"] >= first_week_boot]
    finalists = sorted((c for c in cast.values() if c.get("finalist")), key=lambda c: c["place"])
    pool = [c for c in cast.values() if (c.get("order") or 0) >= first_week_boot or c.get("finalist")]
    # alive players have order 0/None mid-season; include them
    pool += [c for c in cast.values() if not c.get("order") and c not in pool]

    weeks = {}
    for c in elim:
        k = to_week(c["order"])
        weeks[k] = {"week": k, "episode": c["episode"], "eliminated": name[c["castaway_id"]],
                    "challenges": [], "specials": []}
    # Players who came back (Edge of Extinction, Redemption Island) have only one
    # castaways row, holding their final result, so their first boot is missing
    # there. The vote record has it.
    for r in T["vote_history"]:
        o = r.get("order")
        if o and o >= first_week_boot and to_week(o) not in weeks and r.get("voted_out_id") in name:
            weeks[to_week(o)] = {"week": to_week(o), "episode": r["episode"], "eliminated": name[r["voted_out_id"]],
                                 "challenges": [], "specials": []}
    # Players voted out to Edge of Extinction / Redemption Island who later came
    # back earn no survival while away. (Exile Island players are still in the
    # game and do earn it.)
    away = defaultdict(set)  # boots so far -> castaway ids sitting out
    for r in T["boot_mapping"]:
        if r.get("n_boots") is not None and r.get("game_status") in ("Edge of Extinction", "Redemption Island"):
            away[r["n_boots"]].add(r["castaway_id"])
    for k, w in weeks.items():
        ids = away.get(first_week_boot + k - 2, set())  # state just before this boot
        if ids:
            w["away"] = sorted(name[i] for i in ids if i in name)
    review = []

    def week_of_order(order):
        return to_week(order) if order >= first_week_boot else None

    # ---- votes ----
    by_order = defaultdict(list)
    for r in T["vote_history"]:
        by_order[r["order"]].append(r)
    for order, rows in by_order.items():
        k = week_of_order(order)
        if k not in weeks:
            continue
        rounds = defaultdict(list)
        per_voter = Counter((r["vote_order"], r["castaway_id"]) for r in rows if r.get("vote_id"))
        for r in rows:
            if not r.get("vote_id"):
                continue  # lost vote, shot in the dark, fire challenge, etc.
            b = {"voter": name[r["castaway_id"]], "target": name[r["vote_id"]]}
            if r.get("nullified"):
                b["negated"] = True
            rounds[r["vote_order"]].append(b)
            # A stolen/extra vote is two ballots. survivoR usually has two rows for
            # the voter (S47 Rome) but sometimes one flagged "Extra vote" (S40 Sarah).
            if r.get("vote_event_outcome") == "Extra vote" and per_voter[(r["vote_order"], r["castaway_id"])] == 1:
                rounds[r["vote_order"]].append(dict(b))
        if rounds:
            weeks[k]["council"] = {"rounds": [rounds[i] for i in sorted(rounds)]}

    # ---- stage of game -> week (for advantage events) ----
    sog_boots = {}
    for r in T["boot_mapping"]:
        if r.get("sog_id") is not None and r.get("n_boots") is not None:
            sog_boots[r["sog_id"]] = r["n_boots"]
    sog_week = lambda s: week_of_order(sog_boots[s] + 1) if s in sog_boots else None

    # ---- challenges ----
    # A single combined Reward/Immunity challenge pays immunity only, even when
    # survivoR files the reward as a team win and the immunity as individual
    # (S44 ep 7). challenge_description says whether a challenge is combined;
    # challenge_results sometimes merges two separate challenges under one id
    # (S47 ep 6), so the description is the authority.
    combined = {c["challenge_id"] for c in T.get("challenge_description", [])
                if c.get("challenge_type") == "Immunity and Reward"}
    # Split-group immunity pays only the people who actually won, not those along
    # for the ride (owner ruling 2026-11-25). In a "Team / Individual" challenge the
    # real winners are the overall winner (best finish among "Won") and anyone who
    # won immunity on their own ("Won (immunity only)"); teammates who were made
    # immune keep only the team reward.
    by_chal = defaultdict(list)
    for r in T["challenge_results"]:
        by_chal[r.get("challenge_id")].append(r)
    riders = set()
    for cid, rows in by_chal.items():
        if "Team" not in (rows[0].get("outcome_type") or "") or "Individual" not in (rows[0].get("outcome_type") or ""):
            continue
        immune = [r for r in rows if r.get("won_individual_immunity")]
        if len(immune) <= 2:
            continue
        won = [r for r in immune if r.get("result") == "Won" and r.get("order_of_finish") is not None]
        best = min((r["order_of_finish"] for r in won), default=None)
        for r in immune:
            if r.get("result") == "Won (immunity only)" or (best is not None and r.get("order_of_finish") == best):
                continue
            riders.add((cid, r["castaway_id"]))
    chal = defaultdict(lambda: defaultdict(list))  # week -> type -> [names]
    for r in T["challenge_results"]:
        if r.get("n_boots") is None:
            continue
        k = week_of_order(r["n_boots"] + 1)
        if k not in weeks:
            continue
        types = _challenge_types(r)
        if (r.get("challenge_id"), r["castaway_id"]) in riders:
            types = [t for t in types if "immunity" not in t]
        elif r.get("challenge_id") in combined and any("immunity" in t for t in types):
            types = [t for t in types if "immunity" in t]
        for t in types:
            chal[k][t].append(name[r["castaway_id"]])
    for k, d in chal.items():
        weeks[k]["challenges"] = [{"type": t, "players": sorted(p)} for t, p in sorted(d.items())]

    # ---- advantages ----
    adv_type = {a["advantage_id"]: a["advantage_type"] for a in T["advantage_details"]}
    adv_where = {a["advantage_id"]: a.get("location_found") for a in T["advantage_details"]}
    # idols survivoR logs only as "Found (beware)" and never as "Found": the beware
    # condition was never met, so the idol never had power (whole history, any week)
    events_by_adv = defaultdict(set)
    for m in T["advantage_movement"]:
        events_by_adv[m["advantage_id"]].add(m["event"])
    never_active = {a for a, evs in events_by_adv.items() if "Found (beware)" in evs and "Found" not in evs}
    for m in sorted(T["advantage_movement"], key=lambda m: (m["advantage_id"], m["sequence_id"])):
        k = sog_week(m.get("sog_id"))
        if k not in weeks:
            continue
        typ = adv_type.get(m["advantage_id"], "?")
        is_idol = typ == "Hidden Immunity Idol"
        ev = m["event"]
        shared = "," in (m["castaway"] or "")
        who = None if shared else name.get(m["castaway_id"])
        where = adv_where.get(m["advantage_id"])
        # id is stable across rebuilds (one advantage, one event type); kind says
        # what decision the review screen offers (see REVIEW_KINDS)
        item = {"id": f"{m['advantage_id']}:{ev}", "week": k, "advantage": typ, "event": ev,
                "castaway": m["castaway"], "players": [p.strip() for p in (m["castaway"] or "").split(",") if p.strip()],
                "played_for": m.get("played_for"), "success": m.get("success"),
                "votes_nullified": m.get("votes_nullified"), "location": where}
        if is_idol and ev == "Found":
            item["kind"] = "shared_idol_found" if shared else "handed_out_idol"
        elif is_idol and ev == "Voted out with advantage":
            item["kind"] = "idol_never_active"
        elif ev == "Played" and not is_idol:
            item["kind"] = "advantage_played"
        else:
            item["kind"] = "info"  # nothing to score (e.g. found a non-idol advantage)
        if is_idol and ev == "Found" and who and where not in HANDED_OUT:
            weeks[k]["specials"].append({"type": "idol_found", "player": who, "source": "survivoR"})
        elif is_idol and ev == "Voted out with advantage" and who:
            # only an idol that had power counts; a "Beware" idol never activated
            # (e.g. S41 Brad: all three idols had to be found first) couldn't save anyone
            if m["advantage_id"] not in never_active:
                weeks[k]["specials"].append({"type": "idol_in_pocket", "player": who, "source": "survivoR"})
            else:
                review.append({**item, "note": "voted out holding an idol that was never activated: no penalty"})
        elif is_idol and ev == "Played" and who:
            council = weeks[k].setdefault("council", {"rounds": []})
            council.setdefault("idol_plays", []).append(
                {"player": who, "for": name.get(m.get("played_for_id")) or who,
                 "votes_negated": int(m.get("votes_nullified") or 0)})
        elif ev in ("Played", "Found") or shared:
            if ev != "Found (beware)":
                review.append(item)

    # ---- medevac / quit ----
    forfeit = []
    for c in elim:
        res = (c.get("result") or "").lower()
        k = to_week(c["order"])
        if "medically evacuated" in res:
            weeks[k]["specials"].append({"type": "medevac_pity", "player": name[c["castaway_id"]],
                                         "source": "survivoR"})
        if "quit" in res and "voted out" not in res:  # 'voted out; Quit EoE' left the Edge, not the game
            forfeit.append(name[c["castaway_id"]])

    # ---- jury (final week) ----
    if weeks and finalists:
        last = max(weeks)
        jury = {name[j["castaway_id"]]: name[j["finalist_id"]]
                for j in T["jury_votes"] if j.get("vote") == 1}
        if jury:
            weeks[last]["jury"] = jury

    season = {
        "season": season_num, "title": f"Survivor {season_num}",
        "source": "survivoR (github.com/doehm/survivoR)",
        "first_week_boot": first_week_boot,
        "survival_offset": survival_offset,
        "contestants": [{"name": name[c["castaway_id"]], "short": c["castaway"], "id": c["castaway_id"],
                         "place": c.get("place") or None}  # 1 = winner; None while still in the game
                        for c in sorted(pool, key=lambda c: (c.get("place") or 99), reverse=True)],
        "final_placement": [name[c["castaway_id"]] for c in finalists],
        "forfeit": forfeit,
        "weeks": [weeks[k] for k in sorted(weeks)],
        "review": review,
    }
    if overrides:
        apply_overrides(season, overrides, short, name)
    return season


def apply_overrides(season, ov, short, name):
    """Owner decisions from the review screen. Players are survivoR short names.
    {"specials": [{"week": 1, "type": "advantage_used", "player": "Rome"}],
     "challenges": {"4": [{"type": "indiv_immunity", "players": ["Kyle"]}]},   # replaces that week
     "remove_specials": [{"week": 3, "type": "idol_found", "player": "Teeny"}],
     "forfeit": ["Matthew"]}                                                   # counts as a quit"""
    full = lambda s: name[short[s]] if s in short else s
    wk = {w["week"]: w for w in season["weeks"]}
    for p in ov.get("forfeit", []):
        if full(p) not in season["forfeit"]:
            season["forfeit"].append(full(p))
        for w in season["weeks"]:  # a quit gets no medevac pity
            w["specials"] = [x for x in w["specials"] if not (x["type"] == "medevac_pity" and x["player"] == full(p))]
    for k, items in (ov.get("challenges") or {}).items():
        wk[int(k)]["challenges"] = [{"type": i["type"], "players": [full(p) for p in i["players"]]}
                                    for i in items]
    for s in ov.get("remove_specials", []):
        w = wk[s["week"]]
        w["specials"] = [x for x in w["specials"]
                         if not (x["type"] == s["type"] and x["player"] == full(s["player"]))]
    for s in ov.get("specials", []):
        wk[s["week"]]["specials"].append({"type": s["type"], "player": full(s["player"]),
                                          "source": "override"})
    # review-screen decisions: {"<item id>": "award" | "none"}
    items = {r["id"]: r for r in season.get("review", []) if "id" in r}
    for item_id, choice in (ov.get("decisions") or {}).items():
        item = items.get(item_id)
        if not item:
            continue
        item["decision"] = choice
        if choice == "award" and item.get("kind") in REVIEW_KINDS and item["week"] in wk:
            special = REVIEW_KINDS[item["kind"]][0]
            for p in item.get("players") or [item["castaway"]]:
                wk[item["week"]]["specials"].append({"type": special, "player": full(p), "source": "review"})
    # manual adjustments: [{"week", "player", "category", "points", "reason"}]
    for a in ov.get("adjust", []):
        k = int(a["week"])
        if k in wk and a.get("category") in ADJUST_CATEGORIES:
            wk[k].setdefault("adjustments", []).append(
                {"player": full(a["player"]), "category": a["category"], "points": float(a["points"]),
                 "reason": a.get("reason", "")})


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("season", type=int)
    ap.add_argument("--first-week-boot", type=int, default=4,
                    help="boot order of the first elimination after the draft (default 4)")
    ap.add_argument("--version", default="US")
    ap.add_argument("--overrides")
    ap.add_argument("--refresh", action="store_true", help="re-download survivoR tables")
    ap.add_argument("--out")
    a = ap.parse_args()
    ov = json.load(open(a.overrides, encoding="utf-8")) if a.overrides else None
    s = build_season(a.season, a.first_week_boot, load_tables(a.refresh), a.version, ov)
    out = a.out or f"fixtures/survivoR_season{a.season}.json"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(s, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"wrote {out}: {len(s['weeks'])} weeks, {len(s['review'])} items for review")
    for r in s["review"]:
        print(f"  review wk{r['week']}: {r['castaway']} {r['event']} {r['advantage']}"
              f" (for {r['played_for']}, success={r['success']})")
