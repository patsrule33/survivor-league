"""Survivor fantasy scoring engine.

Input : a normalized season dict (see fixtures/season47.json for the shape).
Output: {contestant: {week: {challenges, votes, survival, special, total}}}

Scoring is per CONTESTANT, independent of who owns them. The app/browser sums
contestant points by roster, which makes waiver moves trivial.
"""
from collections import defaultdict

RULES = {
    "challenge": {
        "tribal_reward_1": 2, "tribal_reward_2": 1,
        "tribal_immunity_1": 4, "tribal_immunity_2": 2,
        "indiv_reward": 3, "indiv_immunity": 6,
        "group_immunity": 6,   # split-group challenge: winners of a group's immunity
    },
    "vote_for_eliminated": 2,     # you voted for the person who went home
    "vote_switched_to_eliminated": 1,  # revote only: voted for them in the last round but not the first
    "vote_received": -1,          # per counted vote against you (first round only)
    "revote_eliminated_extra": -1,  # tie -> revote: eliminated loses 1 more
    "jury_vote": 2,
    "special": {
        "idol_found": 10,
        "advantage_used": 5,          # idol or other advantage, successfully used
        "idol_played_success": 5,     # idol play that nullified >=1 vote
        "idol_in_pocket": -20,
        "medevac_pity": 5,
    },
}


def _blank():
    return {"challenges": 0.0, "votes": 0.0, "survival": 0.0, "special": 0.0}


def score_season(season, rules=RULES):
    pts = defaultdict(lambda: defaultdict(_blank))
    pool = [c["name"] for c in season["contestants"]]
    weeks = season["weeks"]
    if not weeks:  # rosters set, nothing scored yet (e.g. drafted mid-season)
        return {c: {} for c in pool}
    n_weeks = len(weeks)
    eliminated_at = {}  # name -> week

    for w in weeks:
        k = w["week"]
        eliminated_at[w["eliminated"]] = k

        # ---- challenges ----
        for item in w.get("challenges", []):
            p = rules["challenge"][item["type"]]
            for who in item["players"]:
                pts[who][k]["challenges"] += p

        # ---- votes ----
        council = w.get("council")
        if council:
            rounds = council["rounds"]
            for b in rounds[0]:
                if not b.get("negated") and b.get("target"):
                    pts[b["target"]][k]["votes"] += rules["vote_received"]
            final = rounds[-1]
            first_correct = {b["voter"] for b in rounds[0] if b.get("target") == w["eliminated"]}
            for b in final:
                if b.get("target") == w["eliminated"] and not b.get("negated"):
                    full = b["voter"] in first_correct
                    pts[b["voter"]][k]["votes"] += rules["vote_for_eliminated" if full
                                                         else "vote_switched_to_eliminated"]
            if len(rounds) > 1:
                pts[w["eliminated"]][k]["votes"] += rules["revote_eliminated_extra"]
            # An idol play counts only if it saved someone: without it, the person
            # it was played for would have had the most votes (alone or tied).
            first = rounds[0] if rounds else []
            for play in council.get("idol_plays", []):
                target = play.get("for") or play["player"]
                against = sum(1 for b in first if b.get("target") == target)
                others = defaultdict(int)
                for b in first:
                    if b.get("target") and b["target"] != target and not b.get("negated"):
                        others[b["target"]] += 1
                if against > 0 and against >= max(others.values(), default=0):
                    pts[play["player"]][k]["special"] += rules["special"]["idol_played_success"]
        for juror, finalist in (w.get("jury") or {}).items():
            pts[finalist][k]["votes"] += rules["jury_vote"]

        # ---- specials (advantages, idol finds, etc.) ----
        for s in w.get("specials", []):
            pts[s["player"]][k]["special"] += rules["special"][s["type"]]

        # ---- commissioner adjustments from the review screen ----
        for a in w.get("adjustments", []):
            pts[a["player"]][k][a["category"]] += a["points"]

    # ---- survival ladder ----
    # Surviving week k's council earns k points. In the final week the
    # finalists keep climbing the ladder: 3rd gets k, 2nd k+(k+1), 1st k+(k+1)+(k+2).
    # survival_offset (old seasons only): survival started that many weeks late,
    # so surviving week k earns k - offset (never below 0).
    off = season.get("survival_offset", 0)
    rung = lambda k: max(0, k - off)
    final_week = weeks[-1]["week"]
    placement = season["final_placement"]  # ordered best -> worst finalists
    # Survive week k = still in the game after that Tribal. A returnee (Edge of
    # Extinction, Redemption Island) can be eliminated more than once: they earn
    # nothing the week they go out or while listed as "away", and are alive until
    # their final elimination (finalists: through the end).
    elim_weeks = defaultdict(set)
    for w in weeks:
        elim_weeks[w["eliminated"]].add(w["week"])
    week_away = {w["week"]: set(w.get("away", [])) for w in weeks}
    for c in pool:
        last_alive = final_week if c in placement else (max(elim_weeks[c]) - 1 if c in elim_weeks else final_week)
        for k in range(1, last_alive + 1):
            if k not in elim_weeks[c] and c not in week_away.get(k, ()):
                pts[c][k]["survival"] += rung(k)
    n = len(placement)
    for rank, c in enumerate(placement):          # rank 0 = winner
        bonus = sum(rung(final_week + 1 + i) for i in range(n - 1 - rank))
        pts[c][final_week]["survival"] += bonus

    # ---- totals ----
    forfeit = set(season.get("forfeit", []))  # quitting forfeits all points
    result = {}
    for c in pool:
        result[c] = {}
        for k in range(1, n_weeks + 1):
            d = pts[c][k] if k in pts[c] else _blank()
            d = _blank() if c in forfeit else dict(d)
            d["total"] = d["challenges"] + d["votes"] + d["survival"] + d["special"]
            result[c][k] = d
    return result


def contestant_totals(scores):
    return {c: sum(w["total"] for w in wk.values()) for c, wk in scores.items()}


def owner_totals(scores, rosters):
    """rosters: {owner: [contestant, ...]}  (static rosters; waivers come later)."""
    tot = contestant_totals(scores)
    return {o: sum(tot[c] for c in cs) for o, cs in rosters.items()}
