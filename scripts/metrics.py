#!/usr/bin/env python3
"""Metrics for the SyRev validation (definitions as on https://syrev.ai/validation):
  recall = weighted share of true includes with p_include >= threshold; auto-excluded = weighted share below threshold;
  precision = weighted includes among kept; WSS@95 per review = 1 - share of pool read (in p_include order, ties pessimistic)
  to reach 95% recall - 0.05; dataset WSS@95 = mean over reviews (the single value when one review).
  Careful = 0.001, Rapid (stored 'standard') = 0.005. Records with no title and no abstract are left out (no full text either
  in full-text mode). Records that could not be scored are left out (reported as unscored_records_excluded).
Writes results/{per_review_metrics.csv, metrics_summary.csv, metrics_table.md, headline.json}."""
import csv, json, statistics as st
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; M = ROOT / "manifests"; D = ROOT / "data"; O = ROOT / "out"; R = ROOT / "results"; R.mkdir(exist_ok=True)
csv.field_size_limit(10**9)
TH = {"careful": 0.001, "rapid": 0.005}
# (group label, manifest, data dir, out subdir, mode, headline_bucket)
G = [
 ("CLEF TAR 2019 Intervention (19 topics, sampled)", M/"manifest_clef.json", D, "clef2019_int", "abstract", "existing"),
 ("Chan 2025 manual-search (22 reviews, sampled)", M/"manifest_chan.json", D, "chan_sample", "abstract", "existing"),
 ("SWIFT-Review (5 sets, sampled)", M/"manifest_swift.json", D, "swift", "abstract", "existing"),
 ("Bannach-Brown 2019 (labelled set)", M/"manifest_bb.json", D, "bannach_brown", "abstract", "existing"),
 ("CSMeD-FT (211 reviews), title/abstract", [M/"manifest_csmed_ft.json", M/"manifest_csmed_ft_train.json"], D, "csmed_ft", "abstract", "existing"),
 ("CSMeD-FT (211 reviews), full text", [M/"manifest_csmed_ft.json", M/"manifest_csmed_ft_train.json"], D, "csmed_ft", "fulltext", "fulltext"),
 ("SYNERGY launch sets (8 reviews) + Appenzeller-Herzog 2020, public", M/"manifest_synergy.json", D, "synergy", "abstract", "synergy"),
 ("Bannach-Brown 2019 held-out validation set", M/"manifest_bb_heldout.json", D, "bb_heldout", "abstract", "new"),
 ("CLEF TAR 2019 DTA/Prognosis/Qualitative + CD012164 (12 topics, every record)", M/"manifest_clef2019_extra.json", D, "clef2019_extra", "abstract", "new"),
 ("Chan 2025 manual-search, full pools (22 reviews, every record)", M/"manifest_chan_full.json", D, "chan_full", "abstract", "chanfull"),
 ("CLEF TAR 2018 DTA (30 topics, sampled)", M/"manifest_clef2018_dta.json", D, "clef2018_dta", "abstract", "new2018s"),
 ("CLEF TAR 2018 DTA (30 topics, every record)", M/"manifest_clef2018_dta_full.json", D, "clef2018_dta_full", "abstract", "new2018f"),
]

def keep_ids(path, mode):
    ids = set()
    for r in csv.DictReader(open(path, encoding="utf-8")):
        has = (r.get("title") or "").strip() or (r.get("abstract") or "").strip()
        if mode == "fulltext": has = has or len((r.get("main_text") or "").strip()) > 500
        if has: ids.add(r["id"])
    return ids

ERRS = [0, []]
INTERNAL_ONLY = set()

def load(sp, dp, mode):
    ok = keep_ids(dp, mode); out = []
    for r in csv.DictReader(open(sp, encoding="utf-8")):
        if r["id"] not in ok: continue
        err = r["p_include"] == ""
        if err: ERRS[0] += 1; ERRS[1].append(sp.name); continue  # unscored records are left out, never counted as kept
        out.append({"y": int(r["label"]), "p": float(r["p_include"]), "w": float(r.get("weight") or 1), "err": False})
    return out

def at(rows, t):
    inc = sum(r["w"] for r in rows if r["y"]); tot = sum(r["w"] for r in rows)
    ex = [r for r in rows if r["p"] < t]; kept = [r for r in rows if r["p"] >= t]
    missed = sum(r["w"] for r in ex if r["y"]); ki = sum(r["w"] for r in kept if r["y"])
    return {"recall": (1 - missed / inc) if inc else None, "autoex": sum(r["w"] for r in ex) / tot if tot else None,
            "precision": ki / sum(r["w"] for r in kept) if kept else None, "missed": sum(1 for r in ex if r["y"])}

def wss95(rows):
    inc = sum(r["w"] for r in rows if r["y"]); tot = sum(r["w"] for r in rows)
    if not inc or inc == tot: return None
    rs = sorted(rows, key=lambda r: -r["p"]); cum_i = cum = 0.0; i = 0
    while i < len(rs):
        j = i; p = rs[i]["p"]
        while j < len(rs) and rs[j]["p"] == p:
            cum += rs[j]["w"]; cum_i += rs[j]["w"] if rs[j]["y"] else 0; j += 1
        if cum_i >= 0.95 * inc - 1e-9: return 1 - cum / tot - 0.05
        i = j
    return -0.05

def main():
    per, summ = [], []
    for label, mfs, ddir, od, mode, bucket in G:
        mfs = mfs if isinstance(mfs, list) else [mfs]
        man = [m for mf in mfs if Path(mf).exists() for m in json.load(open(mf))]
        if bucket == "synergy": man = [m for m in man if m["stem"] not in INTERNAL_ONLY]
        if bucket == "internal": man = [m for m in man if m["stem"] in INTERNAL_ONLY]
        suf = "live" + ("_ft" if mode == "fulltext" else "")
        allrows, revs = [], []
        for m in man:
            sp = O / od / f"{m['stem']}_{suf}_scores.csv"
            if not sp.exists(): continue
            rows = load(sp, Path(ddir) / f"{m['stem']}.csv", mode)
            if not rows: continue
            allrows += rows
            rec = {"group": label, "mode": mode, "review": m["review_id"], "n_scored": len(rows), "includes": sum(r["y"] for r in rows),
                   "pool_n": m.get("pool_n", len(rows)), "errors": sum(r["err"] for r in rows), "wss95": wss95(rows)}
            for k, t in TH.items():
                a = at(rows, t); rec.update({f"{k}_recall": a["recall"], f"{k}_autoex": a["autoex"], f"{k}_precision": a["precision"], f"{k}_missed": a["missed"]})
            revs.append(rec); per.append(rec)
        if not revs: continue
        s = {"group": label, "bucket": bucket, "mode": mode, "reviews": len(revs), "n_scored": len(allrows), "pool_n": sum(r["pool_n"] for r in revs),
             "includes": sum(r["y"] for r in allrows), "errors": sum(r["err"] for r in allrows), "complete": len(revs) == len(man)}
        for k, t in TH.items():
            a = at(allrows, t)
            s.update({f"{k}_recall": a["recall"], f"{k}_autoex": a["autoex"], f"{k}_precision": a["precision"], f"{k}_missed": sum(r[f"{k}_missed"] for r in revs)})
            wi = [r for r in revs if r["includes"] > 0]
            s[f"{k}_below95"] = sum(1 for r in wi if r[f"{k}_recall"] < 0.95)
            s[f"{k}_below95_5plus"] = sum(1 for r in wi if r[f"{k}_recall"] < 0.95 and r["includes"] >= 5)
            lo = min(wi, key=lambda r: (r[f"{k}_recall"], -r["includes"])) if wi else None
            s[f"{k}_lowest"] = f"{lo['review']} {lo['includes']-lo[f'{k}_missed']}/{lo['includes']}" if lo else ""
            lo5 = [r for r in wi if r["includes"] >= 5]
            lo5 = min(lo5, key=lambda r: r[f"{k}_recall"]) if lo5 else None
            s[f"{k}_lowest_5plus"] = f"{lo5['review']} {lo5['includes']-lo5[f'{k}_missed']}/{lo5['includes']}" if lo5 else ""
        w = [r["wss95"] for r in revs if r["wss95"] is not None]
        s["wss95"] = st.mean(w) if w else None; s["wss95_median"] = st.median(w) if w else None
        s["reviews_with_5plus"] = sum(1 for r in revs if r["includes"] >= 5)
        summ.append(s)
    rnd = lambda d: {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}
    with open(R / "per_review_metrics.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(per[0].keys())); w.writeheader(); [w.writerow(rnd(r)) for r in per]
    with open(R / "metrics_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0].keys())); w.writeheader(); [w.writerow(rnd(r)) for r in summ]
    pc = lambda x: "—" if x is None else f"{100*x:.1f}%"
    L = ["| Dataset | Text | Reviews | Scored (pool) | Includes | Recall C | Auto-excl C | Precision C | Recall R | Auto-excl R | WSS@95 | <95% C (all / ≥5 incl) | Lowest C (any / ≥5) | Errors |",
         "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|"]
    for s in summ:
        L.append(f"| {s['group']}{'' if s['complete'] else ' (INCOMPLETE)'} | {s['mode']} | {s['reviews']} | {s['n_scored']:,} ({s['pool_n']:,}) | {s['includes']:,} | {pc(s['careful_recall'])} | {pc(s['careful_autoex'])} | {pc(s['careful_precision'])} | "
                 f"{pc(s['rapid_recall'])} | {pc(s['rapid_autoex'])} | {pc(s['wss95'])} | {s['careful_below95']} / {s['careful_below95_5plus']} | {s['careful_lowest']} / {s['careful_lowest_5plus']} | {s['errors']} |")
    (R / "metrics_table.md").write_text("\n".join(L) + "\n"); print("\n".join(L))
    # headline pools (abstract only, no double counting): existing public set as on 25 Sep, then with additions
    def pool(buckets, swap_chan=False):
        rows = [r for r in per if any(s["group"] == r["group"] and s["bucket"] in buckets for s in summ)]
        if swap_chan and any(s["bucket"] == "chanfull" and s["complete"] for s in summ):
            rows = [r for r in rows if not r["group"].startswith("Chan 2025 manual-search (22 reviews, sampled)")]
        inc = sum(r["includes"] for r in rows); mc = sum(r["careful_missed"] for r in rows); mr = sum(r["rapid_missed"] for r in rows)
        wi = [r for r in rows if r["includes"] > 0]
        return {"reviews": len(rows), "records_scored": sum(r["n_scored"] for r in rows), "pool": sum(r["pool_n"] for r in rows), "includes": inc,
                "careful_missed": mc, "careful_recall": round(1 - mc / inc, 4) if inc else None, "rapid_recall": round(1 - mr / inc, 4) if inc else None,
                "careful_below95": sum(1 for r in wi if r["careful_recall"] < 0.95),
                "careful_below95_5plus": sum(1 for r in wi if r["careful_recall"] < 0.95 and r["includes"] >= 5), "reviews_5plus": sum(1 for r in wi if r["includes"] >= 5)}
    H = {"public_all": pool({"existing", "new", "chanfull", "new2018s", "synergy"} if not any(s["bucket"] == "new2018f" and s["complete"] for s in summ) else {"existing", "new", "chanfull", "new2018f", "synergy"}, swap_chan=True)}
    H["unscored_records_excluded"] = ERRS[0]; H["files_with_unscored"] = sorted(set(ERRS[1]))
    (R / "headline.json").write_text(json.dumps(H, indent=1)); print(json.dumps(H, indent=1))

if __name__ == "__main__":
    main()
