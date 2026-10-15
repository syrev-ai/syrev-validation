#!/usr/bin/env python3
"""Chan, He, Leung, Verspoor (Res Synth Methods 2025) 'Title and Abstract Screening Data for Systematic Review',
Mendeley Data doi:10.17632/7sgmg89zb6.1, CC BY 4.0 — the 22-review *manual search* compilation
(full search-result pools, labels = included in the Cochrane review or not).

Sampling per review (seed 20260925): all includes + up to 400 random non-includes, with inverse-probability
weights on non-includes. Criteria auto-derived from the review's own [SEL] selection-criteria text.
"""
import csv, json, re, yaml, glob
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
SEED = 20260925; NEX = 400; MAXC = 1500

def clean(s): return re.sub(r"\s+", " ", str(s if s == s and s is not None else "")).strip()

def tag(s, t):
    m = re.search(rf"\[{t}\](.*?)(?=\[[A-Z]{{2,4}}\]|$)", s or "", re.S)
    return clean(m.group(1)) if m else ""

man = []
for f in sorted(glob.glob(str(ROOT / "raw/chan/*_data_cleaned.csv"))):
    rid = Path(f).name.split("_")[0]
    df = pd.read_csv(f, low_memory=False)
    df["y"] = df["included"].astype(str).str.lower().eq("true").astype(int)
    rd = df["Review_data"].dropna().iloc[0]
    rtitle, sel, obj = tag(rd, "RTI"), tag(rd, "SEL"), tag(rd, "OBJ")
    inc, exc = df[df.y == 1], df[df.y == 0]
    ne = min(NEX, len(exc))
    se = exc.sample(n=ne, random_state=SEED).assign(weight=len(exc) / ne)
    s = pd.concat([inc.assign(weight=1.0), se]).sample(frac=1, random_state=SEED)
    stem = f"Chan2025-manual_{rid}"
    with open(ROOT / "data" / f"{stem}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["id", "title", "abstract", "label", "review_id", "weight"])
        for i, r in s.iterrows():
            ta = r["Title_Abstract"] if isinstance(r["Title_Abstract"], str) else ""
            w.writerow([f"{rid}_{r['Unnamed: 0']}", tag(ta, "TIT"), tag(ta, "ABS"), int(r["y"]), rid, round(float(r["weight"]), 6)])
    selc = sel[:MAXC] or obj[:MAXC]
    pre = f'Cochrane review: "{rtitle}". Selection criteria: {selc} '
    crit = [
        {"id": "study_design", "question": pre + "Question: does this record meet the review's eligible study design?", "required": True},
        {"id": "population", "question": pre + "Question: does this record study the review's eligible participants/population?", "required": True},
        {"id": "intervention_or_topic", "question": pre + "Question: does this record evaluate the review's eligible intervention / exposure / index test / topic?", "required": True},
    ]
    (ROOT / "criteria" / f"{stem}.criteria.yaml").write_text(f"# Auto-derived from the [SEL] selection criteria shipped with Chan 2025 manual-search data for {rid}.\n" +
        yaml.safe_dump({"criteria": crit}, sort_keys=False, allow_unicode=True, width=10**6), encoding="utf-8")
    man.append({"group": "Chan 2025 manual-search (Mendeley, CC BY 4.0)", "stem": stem, "review_id": rid, "n": len(s), "includes": int(inc.shape[0]),
                "pool_n": len(df), "pool_includes": int(inc.shape[0]), "sampled_excludes": ne, "review_title": rtitle, "sel_chars": len(sel)})
    print(rid, len(df), len(inc), len(s), len(sel))
json.dump(man, open(ROOT / "data" / "manifest_chan.json", "w"), indent=1)
print("total sampled", sum(m["n"] for m in man), "includes", sum(m["includes"] for m in man), "pool", sum(m["pool_n"] for m in man))
