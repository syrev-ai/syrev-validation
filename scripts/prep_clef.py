#!/usr/bin/env python3
"""CLEF eHealth TAR 2019 Task 2, Intervention test topics (CSMeD 'tar2019' component; repo MIT) — all topics
except CD012164 (already run). Abstract-level qrels (label>0 = include). Titles/abstracts from PubMed E-utilities.
Sampling (seed 20260925): topics with <=600 PMIDs in full; larger: all includes + 500 random non-includes (weighted).
Criteria auto-derived from the latest (<=2019) version of the 'Selection criteria' section of the Cochrane review abstract (Europe PMC).
"""
import csv, json, random, re, sys, time, urllib.request, urllib.parse, yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from prep_swift_bb import efetch  # noqa: E402
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "external/CLEF-TAR/2019-TAR/Task2/Testing/Intervention"
SEED = 20260925; FULL_MAX = 600; NEX = 500; MAXC = 1500

def review_info(cd):
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
    pre2020 = [c for c in cands if c[0] <= 2019]
    return (pre2020[-1:] or cands[:1] or [None])[0]  # latest version published by 2019 (CLEF 2019 era)

rows_q = {}
for qf in BASE.glob("qrels/full.test.intervention.abs.2019.qrels"):
    for ln in open(qf):
        t, _, pmid, rel = ln.split()
        rows_q.setdefault(t, {})[pmid] = 1 if int(rel) > 0 else 0
man = []
rng = random.Random(SEED)
for topic in sorted(rows_q, key=lambda t: len(rows_q[t])):
    if topic == "CD012164": continue
    d = rows_q[topic]
    inc = [p for p, y in d.items() if y]; exc = [p for p, y in d.items() if not y]
    if len(d) <= FULL_MAX:
        samp = [(p, 1, 1.0) for p in inc] + [(p, 0, 1.0) for p in exc]
    else:
        se = rng.sample(exc, min(NEX, len(exc)))
        samp = [(p, 1, 1.0) for p in inc] + [(p, 0, len(exc) / len(se)) for p in se]
    rng.shuffle(samp)
    info = review_info(topic); time.sleep(0.3)
    topic_title = ""
    tf = BASE / "topics" / topic
    if tf.exists():
        m = re.search(r"Title:\s*(.*)", tf.read_text()); topic_title = m.group(1).strip() if m else ""
    if not info:
        print("NO SELECTION CRITERIA", topic); continue
    year, doi, rtitle, sel = info
    fetched = efetch([p for p, _, _ in samp])
    stem = f"CLEF2019-Int_{topic}"
    with open(ROOT / "data" / f"{stem}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["id", "title", "abstract", "label", "review_id", "weight"])
        for p, y, wt in samp:
            t, a = fetched.get(p, ("", ""))
            w.writerow([p, t, a, y, topic, round(wt, 6)])
    title = topic_title or rtitle
    pre = f'Cochrane review: "{title}". Selection criteria: {sel[:MAXC]} '
    crit = [
        {"id": "study_design", "question": pre + "Question: does this record meet the review's eligible study design?", "required": True},
        {"id": "population", "question": pre + "Question: does this record study the review's eligible participants/population?", "required": True},
        {"id": "intervention_or_topic", "question": pre + "Question: does this record evaluate the review's eligible intervention / exposure / index test / topic?", "required": True},
    ]
    (ROOT / "criteria" / f"{stem}.criteria.yaml").write_text(f"# Auto-derived from Selection criteria of {doi} ({year}) via Europe PMC.\n" +
        yaml.safe_dump({"criteria": crit}, sort_keys=False, allow_unicode=True, width=10**6), encoding="utf-8")
    mi = {"group": "CLEF TAR 2019 Intervention (CSMeD tar2019)", "stem": stem, "review_id": topic, "n": len(samp), "includes": len(inc),
          "pool_n": len(d), "pool_includes": len(inc), "criteria_source": doi, "pubmed_missing": sum(p not in fetched for p, _, _ in samp)}
    man.append(mi); print(mi, flush=True)
json.dump(man, open(ROOT / "data" / "manifest_clef.json", "w"), indent=1)
print("total", sum(m["n"] for m in man), "includes", sum(m["includes"] for m in man))
