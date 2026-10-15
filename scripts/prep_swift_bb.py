#!/usr/bin/env python3
"""SWIFT-Review (Howard et al. 2016, CSMeD 'swift' component, CC0 per CSMeD) + Bannach-Brown 2019 (Zenodo 151190, CC BY 4.0).

Sampling (seed 20260925) with inverse-probability weights so work-saved/precision can be
re-weighted back to the full pool. Recall is computed on sampled includes.
BPA / PFOS-PFOA / Transgenerational ship PMIDs only -> titles/abstracts fetched from PubMed E-utilities.
"""
import os, csv, json, random, re, time, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "raw"
SEED = 20260925
PLAN = {  # name: (n_includes_sampled or None=all, n_excludes_sampled)
    "BPA": (None, 1389), "PFOS-PFOA": (None, 1405), "Transgenerational": (300, 1200),
    "Fluoride": (None, 1449), "Neuropain": (300, 1200),
}

def clean(s): return re.sub(r"\s+", " ", str(s if s is not None and s == s else "")).strip()

def efetch(pmids):
    out = {}
    for i in range(0, len(pmids), 200):
        chunk = pmids[i:i+200]
        data = urllib.parse.urlencode({"db": "pubmed", "id": ",".join(chunk), "retmode": "xml", "tool": "syrev-validation", "email": os.environ.get("NCBI_EMAIL", "")}).encode()
        for attempt in range(12):
            try:
                xml = urllib.request.urlopen("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi", data=data, timeout=120).read(); break
            except Exception:
                if attempt == 11: raise
                time.sleep(10)
        root = ET.fromstring(xml)
        for art in root.findall(".//PubmedArticle"):
            pmid = art.findtext(".//MedlineCitation/PMID")
            title = "".join(art.find(".//ArticleTitle").itertext()) if art.find(".//ArticleTitle") is not None else ""
            abst = " ".join("".join(a.itertext()) for a in art.findall(".//Abstract/AbstractText"))
            out[pmid] = (clean(title), clean(abst))
        time.sleep(0.4)
    return out

def sample(df, label_col, plan, rng):
    inc = df[df[label_col] == 1]; exc = df[df[label_col] == 0]
    ni, ne = plan
    ni = len(inc) if ni is None or ni >= len(inc) else ni
    ne = min(ne, len(exc))
    si = inc.sample(n=ni, random_state=rng); se = exc.sample(n=ne, random_state=rng)
    si = si.assign(weight=len(inc) / ni); se = se.assign(weight=len(exc) / ne)
    return pd.concat([si, se]), {"pool_n": len(df), "pool_includes": len(inc), "sampled_includes": ni, "sampled_excludes": ne}

def main():
    manifest = []
    ohat = pd.ExcelFile(RAW / "swift_ohat.xlsx")
    for name, plan in PLAN.items():
        if name == "Neuropain":
            df = pd.read_excel(RAW / "swift_camarades.xlsx", sheet_name="Neuropain")
            df["y"] = (df["Label"] != "Excluded").astype(int); df["pid"] = [f"np{i}" for i in range(len(df))]
        elif name == "Fluoride":
            df = ohat.parse("Fluoride"); df["y"] = (df["Included"] != "EXCLUDED").astype(int); df["pid"] = df["Refid"].astype(str)
        else:
            df = ohat.parse(name); df["y"] = (df["Status"] == "Included").astype(int); df["pid"] = df["PMID"].astype(str)
        df = df.drop_duplicates("pid")
        s, info = sample(df, "y", plan, SEED)
        if name in ("BPA", "PFOS-PFOA", "Transgenerational"):
            fetched = efetch([p for p in s["pid"].tolist()])
            s["title"] = [fetched.get(p, ("", ""))[0] for p in s["pid"]]
            s["abstract"] = [fetched.get(p, ("", ""))[1] for p in s["pid"]]
            info["pubmed_missing"] = int(sum(p not in fetched for p in s["pid"]))
        else:
            s["title"] = s["Title"].map(clean); s["abstract"] = s["Abstract"].map(clean)
        stem = f"SWIFT_{name}"
        s = s.sample(frac=1, random_state=SEED)
        with open(ROOT / "data" / f"{stem}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["id", "title", "abstract", "label", "review_id", "weight"])
            for _, r in s.iterrows():
                w.writerow([r["pid"], r["title"], r["abstract"], int(r["y"]), name, round(float(r["weight"]), 6)])
        info.update({"group": "CSMeD SWIFT (Howard 2016)", "stem": stem, "review_id": name, "n": len(s), "includes": int(s["y"].sum()),
                     "empty_text": int(((s["title"] == "") & (s["abstract"] == "")).sum())})
        manifest.append(info); print(info, flush=True)
    json.dump(manifest, open(ROOT / "data" / "manifest_swift.json", "w"), indent=1)

    # Bannach-Brown 2019: full labelled set, no sampling
    rows = list(csv.DictReader(open(RAW / "bb_devtrain.txt", encoding="utf-8", errors="replace"), delimiter="\t"))
    stem = "Bannach-Brown_2019"
    with open(ROOT / "data" / f"{stem}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["id", "title", "abstract", "label", "review_id", "weight"])
        for r in rows:
            w.writerow([f"bb{r['ID']}", clean(r["Title"]), clean(r["Abstract"]), int(r["Incl(1)/Excl(0)"]), stem, 1.0])
    bbm = [{"group": "Bannach-Brown 2019 (preclinical depression)", "stem": stem, "review_id": stem, "n": len(rows),
            "includes": sum(int(r["Incl(1)/Excl(0)"]) for r in rows), "pool_n": len(rows)}]
    json.dump(bbm, open(ROOT / "data" / "manifest_bb.json", "w"), indent=1); print(bbm)

if __name__ == "__main__":
    main()
