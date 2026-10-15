#!/usr/bin/env python3
"""Chan et al. 2025 manual-search set (Mendeley 10.17632/7sgmg89zb6.1, CC BY 4.0): EVERY record of the 22 full
search pools (no sampling). Same parsing and the same criteria files as scripts/prep_chan.py, so
each record id matches the 25 Sep sample (sampled records reuse their cached live scores)."""
import csv, json, re, glob, shutil
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]; X = ROOT

def clean(s): return re.sub(r"\s+", " ", str(s if s == s and s is not None else "")).strip()
def tag(s, t):
    m = re.search(rf"\[{t}\](.*?)(?=\[[A-Z]{{2,4}}\]|$)", s or "", re.S)
    return clean(m.group(1)) if m else ""

man = []
for f in sorted(glob.glob(str(X / "raw/chan/*_data_cleaned.csv"))):
    rid = Path(f).name.split("_")[0]
    df = pd.read_csv(f, low_memory=False)
    df["y"] = df["included"].astype(str).str.lower().eq("true").astype(int)
    stem = f"Chan2025-manual_{rid}"
    with open(ROOT / "data" / f"{stem}.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["id", "title", "abstract", "label", "review_id", "weight"])
        for _, r in df.iterrows():
            ta = r["Title_Abstract"] if isinstance(r["Title_Abstract"], str) else ""
            w.writerow([f"{rid}_{r['Unnamed: 0']}", tag(ta, "TIT"), tag(ta, "ABS"), int(r["y"]), rid, 1.0])
    shutil.copy(X / "criteria" / f"{stem}.criteria.yaml", ROOT / "criteria" / f"{stem}.criteria.yaml")
    man.append({"group": "Chan 2025 manual-search, full pools (CC BY 4.0)", "stem": stem, "review_id": rid, "n": len(df),
                "includes": int(df.y.sum()), "pool_n": len(df)})
    print(rid, len(df), int(df.y.sum()), flush=True)
json.dump(man, open(ROOT / "data" / "manifest_chan_full.json", "w"), indent=1)
print("total", sum(m["n"] for m in man), "includes", sum(m["includes"] for m in man))
