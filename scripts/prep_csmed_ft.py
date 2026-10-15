#!/usr/bin/env python3
"""Normalize CSMeD-FT test (minus reviews already run) + dev into per-review CSV + criteria YAML.

Criteria are auto-derived from the Cochrane eligibility sections shipped in
CSMeD-FT *_reviews_metadata.json (no hand-tuning): study design, participants,
intervention/exposure/index-test/topic. Outcomes are NOT used (standard screening practice).
"""
import os, csv, json, zipfile, io, re, sys, yaml
from pathlib import Path
csv.field_size_limit(10**9)
ROOT = Path(__file__).resolve().parents[1]
ZIP = ROOT / "external/CSMeD/data/CSMeD/CSMeD-FT.zip"
ALREADY_RUN = {"CD013635", "CD012199"}  # prior CSMeD-FT runs (criteria/CD013635, CD012199)
MAXC = 1500

def clean(s): return re.sub(r"\s+", " ", (s or "")).strip()

def pick(crit: dict, keys):
    for k in keys:
        for ck, v in crit.items():
            if ck and ck.lower() == k.lower() and clean(v):
                return clean(v)[:MAXC]
    return None

def derive(meta):
    crit = meta.get("criteria") or {}
    if not isinstance(crit, dict): crit = {}
    title = clean(meta.get("title"))
    study = pick(crit, ["Types of studies"])
    part = pick(crit, ["Types of participants", "Participants", "Targeted population"])
    inter = pick(crit, ["Types of interventions", "Interventions", "Intervention", "Index tests",
                        "Types of phenomena of interest", "Topic of interest", "Types of prognostic factors"])
    out = []
    pre = f'Cochrane review: "{title}". '
    if study: out.append({"id": "study_design", "question": pre + f"Does this record meet the review's eligible study design? Review criterion: {study}", "required": True})
    if part: out.append({"id": "population", "question": pre + f"Does this record study the review's eligible participants/population? Review criterion: {part}", "required": True})
    if inter: out.append({"id": "intervention_or_topic", "question": pre + f"Does this record evaluate the review's eligible intervention / exposure / index test / topic? Review criterion: {inter}", "required": True})
    if not out:
        txt = clean(meta.get("criteria_text"))[:MAXC*2] or clean(meta.get("abstract"))[:MAXC]
        out.append({"id": "eligible", "question": pre + f"Does this record meet the review's eligibility criteria? Criteria: {txt}", "required": True})
    return out

def main():
    z = zipfile.ZipFile(ZIP)
    manifest = []
    import os
    splits = os.environ.get("SPLITS", "test,dev").split(",")
    for split in splits:
        meta = json.loads(z.read(f"CSMeD-FT/CSMeD-FT-{split}_reviews_metadata.json"))
        rows = list(csv.DictReader(io.TextIOWrapper(z.open(f"CSMeD-FT/CSMeD-FT-{split}.csv"), encoding="utf-8")))
        by = {}
        for r in rows:
            if split == "test" and r["review_id"] in ALREADY_RUN: continue
            by.setdefault(r["review_id"], []).append(r)
        for rid, rs in sorted(by.items()):
            stem = f"CSMeD-FT-{split}_{rid}"
            with open(ROOT / "data" / f"{stem}.csv", "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f); w.writerow(["id","title","abstract","label","review_id","weight","main_text"])
                for r in rs:
                    pid = clean(r.get("PubMed ID"))
                    rid_doc = f"{pid}" if pid and pid.lower() not in ("nan","none","") else r["document_id"]
                    w.writerow([f"{rid_doc}__{r['document_id']}", clean(r["title"]), clean(r["abstract"]),
                                1 if r["decision"] == "included" else 0, rid, 1.0, r.get("main_text") or ""])
            crit = derive(meta[rid])
            (ROOT / "criteria" / f"{stem}.criteria.yaml").write_text(
                f"# Auto-derived from CSMeD-FT {split} metadata for {rid} (Cochrane eligibility sections).\n" +
                yaml.safe_dump({"criteria": crit}, sort_keys=False, allow_unicode=True, width=10**6), encoding="utf-8")
            manifest.append({"group": f"CSMeD-FT ({split})", "stem": stem, "review_id": rid, "n": len(rs),
                             "includes": sum(r["decision"] == "included" for r in rs)})
    json.dump(manifest, open(ROOT / "data" / os.environ.get("MANIFEST", "manifest_csmed_ft.json"), "w"), indent=1)
    print(len(manifest), "reviews", sum(m["n"] for m in manifest), "docs", sum(m["includes"] for m in manifest), "includes")

if __name__ == "__main__":
    main()
