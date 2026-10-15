#!/usr/bin/env python3
"""CLEF TAR datasets (repo github.com/CLEF-TAR/tar, MIT). Same method as scripts/prep_clef.py:
abstract-level qrels (rel>0 = include); titles/abstracts from PubMed E-utilities; criteria auto-derived (fixed template,
no LLM, not tuned) from the 'Selection criteria' section of the latest Cochrane review version published by the CLEF year
(Europe PMC).
  prep_clef_extra.py clef2019_extra    -> 2019 Task 2 test: DTA (8), Prognosis (1), Qualitative (2), Intervention CD012164; every record
  prep_clef_extra.py clef2018_dta      -> 2018 Task 2 test (30 DTA topics): all includes + 500 random others per topic (seed 20260929, weighted)
  prep_clef_extra.py clef2018_dta_full -> 2018 Task 2 test: every record
"""
import csv, json, random, re, sys, time, urllib.parse, urllib.request, yaml
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from prep_swift_bb import efetch  # noqa: E402
T = ROOT / "external/CLEF-TAR"
SEED = 20260929; NEX = 500; MAXC = 1500

def review_info(cd, maxyear):
    q = f'{cd} AND JOURNAL:"Cochrane Database Syst Rev"'
    u = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?" + urllib.parse.urlencode({"query": q, "format": "json", "resultType": "core", "pageSize": 25})
    for attempt in range(12):
        try:
            rs = json.load(urllib.request.urlopen(u, timeout=60))["resultList"]["result"]; break
        except Exception:
            if attempt == 11: raise
            time.sleep(10)
    cands = []
    for r in rs:
        a = r.get("abstractText", "") or ""
        if cd.lower() not in (r.get("doi") or "").lower(): continue
        m = re.search(r"selection criteria\s*[:.]?\s*(?:</h4>)?(.*?)(?:<h4>|data collection and analysis|$)", a, re.I | re.S)
        if m: cands.append((int(r.get("pubYear") or 9999), r.get("doi"), re.sub(r"<[^>]+>", " ", r.get("title", "")), re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip()))
    cands.sort()
    early = [c for c in cands if c[0] <= maxyear]
    return (early[-1:] or cands[:1] or [None])[0]

def qrels(path):
    d = {}
    for ln in open(path):
        p = ln.split()
        if len(p) < 4: continue
        d.setdefault(p[0], {})[p[2]] = 1 if int(p[3]) > 0 else 0
    return d

JOBS = {
    "clef2019_extra": dict(year=2019, sample=False, sets=[
        ("CLEF TAR 2019 DTA", "CLEF2019-DTA", T / "2019-TAR/Task2/Testing/DTA", "qrels/full.test.dta.abs.2019.qrels", None),
        ("CLEF TAR 2019 Prognosis", "CLEF2019-Prog", T / "2019-TAR/Task2/Testing/Prognosis", "qrels/full.test.prognosis.abs.2019.qrels", None),
        ("CLEF TAR 2019 Qualitative", "CLEF2019-Qual", T / "2019-TAR/Task2/Testing/Qualitative", "qrels/full.test.qualitative.abs.2019.qrels", None),
        ("CLEF TAR 2019 Intervention", "CLEF2019-Int", T / "2019-TAR/Task2/Testing/Intervention", "qrels/full.test.intervention.abs.2019.qrels", {"CD012164"}),
    ]),
    "clef2018_dta": dict(year=2018, sample=True, sets=[("CLEF TAR 2018 DTA (sampled)", "CLEF2018-DTA", T / "2018-TAR/Task2/Testing", "qrels/full.test.abs.2018.qrels", None)]),
    "clef2018_dta_full": dict(year=2018, sample=False, sets=[("CLEF TAR 2018 DTA", "CLEF2018-DTAfull", T / "2018-TAR/Task2/Testing", "qrels/full.test.abs.2018.qrels", None)]),
}

def main(job):
    J = JOBS[job]; rng = random.Random(SEED); man = []
    for group, prefix, base, qf, only in J["sets"]:
        Q = qrels(base / qf)
        for topic in sorted(Q, key=lambda t: len(Q[t])):
            if only and topic not in only: continue
            d = Q[topic]; inc = [p for p, y in d.items() if y]; exc = [p for p, y in d.items() if not y]
            if J["sample"] and len(exc) > NEX:
                se = rng.sample(exc, NEX); samp = [(p, 1, 1.0) for p in inc] + [(p, 0, len(exc) / NEX) for p in se]
            else:
                samp = [(p, 1, 1.0) for p in inc] + [(p, 0, 1.0) for p in exc]
            rng.shuffle(samp)
            info = review_info(topic, J["year"]); time.sleep(0.3)
            tf = base / "topics" / topic; topic_title = ""
            if tf.exists():
                m = re.search(r"Title:\s*(.*)", tf.read_text()); topic_title = m.group(1).strip() if m else ""
            if not info:
                print("NO SELECTION CRITERIA — skipped", topic, flush=True); continue
            year, doi, rtitle, sel = info
            stem = f"{prefix}_{topic}"
            dpath = ROOT / "data" / f"{stem}.csv"
            if not dpath.exists():
                fetched = efetch([p for p, _, _ in samp])
                with open(dpath, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f); w.writerow(["id", "title", "abstract", "label", "review_id", "weight"])
                    for p, y, wt in samp:
                        t, a = fetched.get(p, ("", "")); w.writerow([p, t, a, y, topic, round(wt, 6)])
                missing = sum(p not in fetched for p, _, _ in samp)
            else:
                missing = None
            title = topic_title or rtitle
            pre = f'Cochrane review: "{title}". Selection criteria: {sel[:MAXC]} '
            crit = [
                {"id": "study_design", "question": pre + "Question: does this record meet the review's eligible study design?", "required": True},
                {"id": "population", "question": pre + "Question: does this record study the review's eligible participants/population?", "required": True},
                {"id": "intervention_or_topic", "question": pre + "Question: does this record evaluate the review's eligible intervention / exposure / index test / topic?", "required": True},
            ]
            (ROOT / "criteria" / f"{stem}.criteria.yaml").write_text(f"# Auto-derived from Selection criteria of {doi} ({year}) via Europe PMC.\n" +
                yaml.safe_dump({"criteria": crit}, sort_keys=False, allow_unicode=True, width=10**6), encoding="utf-8")
            mi = {"group": group, "stem": stem, "review_id": topic, "n": len(samp), "includes": len(inc), "pool_n": len(d),
                  "pool_includes": len(inc), "criteria_source": doi, "criteria_year": year, "pubmed_missing": missing}
            man.append(mi); print(mi, flush=True)
    json.dump(man, open(ROOT / "data" / f"manifest_{job}.json", "w"), indent=1)
    print("total", sum(m["n"] for m in man), "includes", sum(m["includes"] for m in man), "pool", sum(m["pool_n"] for m in man))

if __name__ == "__main__":
    main(sys.argv[1])
