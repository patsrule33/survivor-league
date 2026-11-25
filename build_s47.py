"""Hand-transcribed Season 47 fixture, from the Wikipedia 'Survivor 47' page
(season summary, voting history, jury table and footnotes).
Weeks = one per Tribal Council from the draft onward (episode 13 has two)."""
import json, os

N = {
 "Kishan": 'Kishan Patel', "Anika": 'Anika Dhar', "Rome": 'Jerome "Rome" Cooney',
 "Tiyana": 'Tiyana Hallums', "Sierra": 'Sierra Wright', "Sol": 'Solomon "Sol" Yi',
 "Gabe": 'Gabe Ortis', "Kyle": 'Kyle Ostwald', "Caroline": 'Caroline Vidmar',
 "Andy": 'Andy Rueda', "Genevieve": 'Genevieve Mushaluk',
 "Teeny": 'Christine "Teeny" Chirichillo', "Sue": 'Sue Smey',
 "Sam": 'Sam Phalen', "Rachel": 'Rachel LaMont',
}
f = lambda s: N[s]
def B(spec):
    """'Rachel>Andy, Sue>Andy, Rome>Kishan*2, Andy>Rachel!' -> ballots.
    *2 = two ballots (vote steal); trailing ! = negated by an idol."""
    out = []
    for tok in spec.split(","):
        tok = tok.strip()
        if not tok: continue
        neg = tok.endswith("!"); tok = tok.rstrip("!")
        mult = 1
        if "*" in tok: tok, m = tok.split("*"); mult = int(m)
        v, t = tok.split(">")
        for _ in range(mult):
            b = {"voter": f(v), "target": f(t)}
            if neg: b["negated"] = True
            out.append(b)
    return out
def C(kind, *names): return {"type": kind, "players": [f(n) for n in names]}
def S(kind, name, src): return {"type": kind, "player": f(name), "source": src}

weeks = [
 dict(week=1, episode=4, eliminated=f("Kishan"),
      council=dict(rounds=[B("Genevieve>Kishan, Rome>Kishan*2, Sol>Kishan")]),
      challenges=[C("tribal_immunity_1","Andy","Anika","Rachel","Sam","Sierra"),
                  C("tribal_immunity_2","Caroline","Gabe","Kyle","Sue","Tiyana")],
      specials=[S("idol_found","Sue","recap"), S("advantage_used","Rome","footnote:vote_stealer")]),
 dict(week=2, episode=5, eliminated=f("Anika"),
      council=dict(rounds=[B("Sam>Anika, Andy>Anika, Sierra>Anika, Rachel>Andy")]),
      challenges=[C("tribal_reward_1","Caroline","Kyle","Rachel","Sam","Sue","Teeny","Tiyana"),
                  C("tribal_immunity_1","Caroline","Gabe","Kyle","Sue","Tiyana"),
                  C("tribal_immunity_2","Genevieve","Rome","Sol","Teeny")]),
 dict(week=3, episode=6, eliminated=f("Rome"),
      council=dict(rounds=[B("Rachel>Rome, Sam>Rome, Teeny>Rome, Genevieve>Rome, Andy>Rome, "
                             "Caroline>Rome, Sierra>Rome, Tiyana>Rome, Gabe>Rome, "
                             "Sue>Andy, Sol>Andy, Rome>Sam")]),
      challenges=[C("tribal_reward_1","Kyle","Rachel","Sam","Sierra","Sue","Teeny","Genevieve"),
                  C("indiv_immunity","Kyle")]),
 dict(week=4, episode=7, eliminated=f("Tiyana"),
      council=dict(rounds=[B("Sue>Tiyana, Kyle>Tiyana, Caroline>Tiyana, Gabe>Tiyana, Tiyana>Gabe")]),
      challenges=[C("indiv_reward","Andy","Sam","Sierra","Genevieve","Sol","Teeny"),
                  C("indiv_immunity","Kyle")],  # split-group: winning team = reward (owner ruling)
      specials=[S("advantage_used","Sol","recap")]),
 dict(week=5, episode=8, eliminated=f("Sierra"),
      council=dict(rounds=[
          B("Sol>Sam, Andy>Sam, Genevieve>Sam, Teeny>Sam, Sue>Sierra, Kyle>Sierra, "
            "Caroline>Sierra, Gabe>Sierra, Sierra>Gabe"),
          B("Sue>Sierra, Kyle>Sierra, Caroline>Sierra, Gabe>Sierra, Sol>Sierra, Andy>Sierra, "
            "Genevieve>Sierra, Teeny>Sierra, Sierra>Sam")]),
      challenges=[C("indiv_immunity","Sue","Kyle")],
      specials=[S("idol_found","Rachel","recap")]),
 dict(week=6, episode=9, eliminated=f("Sol"),
      council=dict(rounds=[B("Rachel>Sol, Sam>Sol, Sue>Sol, Teeny>Sol, Genevieve>Sol, Andy>Sol, "
                             "Kyle>Sol, Gabe>Sol, Sol>Sue")]),
      challenges=[C("indiv_reward","Gabe","Kyle","Sol","Teeny"), C("indiv_immunity","Gabe")]),
 dict(week=7, episode=10, eliminated=f("Gabe"),
      council=dict(rounds=[B("Rachel>Gabe, Sam>Gabe, Teeny>Gabe, Genevieve>Gabe, Andy>Gabe, "
                             "Kyle>Gabe, Caroline>Gabe, Sue>Genevieve, Gabe>Genevieve")]),
      challenges=[C("indiv_reward","Kyle","Rachel","Sam"), C("indiv_immunity","Kyle")]),
 dict(week=8, episode=11, eliminated=f("Kyle"),
      council=dict(rounds=[B("Rachel>Kyle, Sam>Kyle, Sue>Kyle, Teeny>Kyle, Genevieve>Kyle, "
                             "Caroline>Kyle, Andy>Genevieve, Kyle>Teeny")]),
      challenges=[C("indiv_immunity","Rachel")]),
 dict(week=9, episode=12, eliminated=f("Caroline"),
      council=dict(rounds=[B("Andy>Caroline, Genevieve>Caroline, Sam>Caroline, Teeny>Sam, "
                             "Sue>Sam, Rachel>Genevieve, Caroline>Genevieve")]),
      challenges=[C("indiv_reward","Sam"), C("indiv_immunity","Rachel")]),
 dict(week=10, episode=13, eliminated=f("Andy"),
      council=dict(rounds=[B("Rachel>Andy, Sue>Andy, Andy>Rachel!, Genevieve>Rachel!, Teeny>Rachel!")],
                   idol_plays=[dict(player=f("Rachel"), votes_negated=3)]),
      challenges=[C("indiv_immunity","Genevieve")]),
 dict(week=11, episode=13, eliminated=f("Genevieve"),
      council=dict(rounds=[B("Rachel>Genevieve, Sue>Genevieve, Sam>Genevieve, Genevieve>Sam, Teeny>Sam")],
                   idol_plays=[dict(player=f("Sue"), votes_negated=0)]),
      challenges=[C("indiv_immunity","Rachel")]),
 dict(week=12, episode=14, eliminated=f("Teeny"),
      challenges=[C("indiv_immunity","Rachel")],
      jury={f(j): f("Rachel") for j in ["Teeny","Genevieve","Andy","Caroline","Gabe","Sol","Sierra"]}
           | {f("Kyle"): f("Sam")}),
]

season = dict(
    season=47, title="Survivor 47",
    source="https://en.wikipedia.org/wiki/Survivor_47",
    contestants=[dict(name=v) for v in N.values()],
    final_placement=[f("Rachel"), f("Sam"), f("Sue")],
    weeks=weeks,
)
os.makedirs("fixtures", exist_ok=True)
json.dump(season, open("fixtures/season47.json", "w"), indent=1)
print("wrote fixtures/season47.json", len(weeks), "weeks")
