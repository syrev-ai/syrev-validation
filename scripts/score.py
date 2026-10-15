#!/usr/bin/env python3
"""Score screening datasets the way the SyRev app does, and write per-record scores.

  * Title/abstract text: title and abstract joined with a newline (empty parts dropped).
    Records with neither a title nor an abstract are not sent (and are excluded from all metrics).
  * Full text (mode=fulltext): the reference list is removed, the text is split into parts of at most
    60,000 characters (max 5), each part is sent together with the title/abstract, and each criterion's
    probability is the highest across parts.
  * p_include = product of the probabilities of the required criteria. Careful = 0.001, Rapid = 0.005.
  * A record that cannot be scored after retries is stored with error=1.
Results are appended to out/scores.jsonl and cached in out/cache.sqlite.

Reproducing SyRev's exact numbers requires access to SyRev's scorer, which is not public.
See README.md ("Reproducing the results").
"""
from __future__ import annotations
import argparse, csv, hashlib, json, os, re, sqlite3, sys, threading, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"; OUT.mkdir(exist_ok=True)
SCORES = OUT / "scores.jsonl"
CACHE = OUT / "cache.sqlite"
SCORER_URL = os.environ.get("SCORER_URL", "").strip()
CHUNK, MAXCH = 60_000, 5
csv.field_size_limit(10**9)
_lock = threading.Lock()
_stop = threading.Event()

REF = re.compile(r"(?:^|[\s.:;])(References|REFERENCES|Reference List|Bibliography|BIBLIOGRAPHY|Literature Cited|LITERATURE CITED|Works Cited)(?=[\s:.]|$)")

def citation_density(t):
    if not t: return 0
    years = len(re.findall(r"\b(?:19|20)\d{2}[a-z]?\b", t)); etal = len(re.findall(r"\bet al\b", t, re.I))
    dois = len(re.findall(r"\bdoi\b|10\.\d{4,9}/", t, re.I))
    return (years + etal + dois) * 1000 / len(t)

def references_start(t):
    mn = len(t) // 2
    for m in REF.finditer(t):
        at = m.start(1)
        if at < mn: continue
        tail = t[at:]
        if len(tail) < 300 or citation_density(tail) < 4: continue
        return at
    return -1

def split_parts(text, size):
    parts, rest = [], text.strip()
    while len(rest) > size:
        cut = -1; floor = int(size * 0.8)
        for sep in [". ", "? ", "! ", "; ", " "]:
            i = rest.rfind(sep, 0, size)  # JS lastIndexOf(sep, size - sep.length)
            if i >= floor: cut = i + len(sep); break
        if cut <= 0: cut = size
        parts.append(rest[:cut].strip()); rest = rest[cut:].strip()
    if rest: parts.append(rest)
    return parts

def ta_text(row):
    return "\n".join(s for s in [(row.get("title") or ""), (row.get("abstract") or "")] if s.strip())

def bodies(row, mode):
    base = ta_text(row).strip()
    if mode != "fulltext": return [base]
    ft = (row.get("main_text") or "").strip()
    if len(ft) <= 500: return [base]  # no usable full text: the app would keep the title/abstract score
    r = references_start(ft)
    body = ft[:r].strip() if r > 0 else ft
    parts = split_parts(body, CHUNK)[:MAXCH]
    out = []
    for i, p in enumerate(parts, 1):
        label = f"--- full text (PDF), part {i} of {len(parts)} ---" if len(parts) > 1 else "--- full text (PDF) ---"
        out.append(f"{base}\n\n{label}\n{p}")
    return out

def call(text, criteria, key):
    """Send one text and the review's criteria to the scorer; return ({criterion_id: probability}, model_label, input_tokens).
    The SyRev scorer is not publicly accessible. To reproduce, set SCORER_URL / SCORER_API_KEY for an endpoint that
    accepts {"text": ..., "criteria": [{"id", "question"}]} and returns {"probabilities": {id: p}}, or adapt this function."""
    body = json.dumps({"text": text, "criteria": [{"id": c["id"], "question": c["question"]} for c in criteria]}).encode()
    last = None
    for attempt in range(7):
        try:
            req = urllib.request.Request(SCORER_URL, data=body, method="POST", headers={
                "Content-Type": "application/json", "Accept": "application/json", "Authorization": "Bearer " + key})
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode())
            probs = {c["id"]: float(d["probabilities"][c["id"]]) for c in criteria}
            return probs, d.get("model"), (d.get("usage") or {}).get("input_tokens") or 0
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (400, 401, 402, 403, 404, 413, 422): break
            time.sleep(min(60, 2 ** attempt + (5 if e.code == 429 else 0)))
        except Exception as e:  # noqa: BLE001
            last = type(e).__name__ + ": " + str(e)[:120]
            time.sleep(min(60, 2 ** attempt))
    raise RuntimeError(last)

def db():
    con = sqlite3.connect(CACHE, timeout=300, check_same_thread=False)
    con.execute("pragma journal_mode=WAL")
    con.execute("create table if not exists s (k text primary key, stem text, id text, mode text, probs text, model text, tokens int, cost real, err text, ts real)")
    if con.execute("select count(*) from s").fetchone()[0] == 0 and SCORES.exists():
        for ln in open(SCORES):
            try: d = json.loads(ln)
            except Exception: continue
            con.execute("insert or replace into s values (?,?,?,?,?,?,?,?,?,?)", (d["k"], d["stem"], d["id"], d["mode"], json.dumps(d["probs"]) if d["probs"] else None, d["model"], d["tokens"], d["cost"], d["err"], d["ts"]))
        con.commit()
    return con

def spend(con): return con.execute("select coalesce(sum(cost),0) from s").fetchone()[0]

def p_include(probs, criteria):
    p = 1.0
    for c in criteria:
        if c.get("required", True): p *= max(0.0, min(1.0, probs[c["id"]]))
    return p

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--data-dir", required=True); ap.add_argument("--criteria-dir", required=True)
    ap.add_argument("--mode", choices=["abstract", "fulltext"], default="abstract")
    ap.add_argument("--outdir", required=True, help="subfolder of out/")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--cap", type=float, default=float("inf"), help="optional spend cap (unused unless you set a per-token price)")
    a = ap.parse_args()
    key = os.environ.get("SCORER_API_KEY", "").strip()
    man = json.load(open(a.manifest)); od = OUT / a.outdir; od.mkdir(parents=True, exist_ok=True)
    con = db(); suffix = "live" + ("_ft" if a.mode == "fulltext" else "")
    models = {}
    for m in man:
        stem = m["stem"]
        rows = list(csv.DictReader(open(Path(a.data_dir) / f"{stem}.csv", encoding="utf-8", newline="")))
        crit = yaml.safe_load((Path(a.criteria_dir) / f"{stem}.criteria.yaml").read_text())["criteria"]
        ch = hashlib.sha1(json.dumps(crit, sort_keys=True).encode()).hexdigest()[:10]
        res, todo = {}, []
        for r in rows:
            k = f"{a.mode}|{stem}|{r['id']}|{ch}"
            hit = con.execute("select probs from s where k=? and probs is not null", (k,)).fetchone()
            if not hit and "CLEF2018-DTAfull_" in stem:  # same topic, same criteria: reuse the sampled run's score
                hit = con.execute("select probs from s where k=? and probs is not null", (k.replace("CLEF2018-DTAfull_", "CLEF2018-DTA_"),)).fetchone()
            if hit: res[r["id"]] = json.loads(hit[0])
            elif ta_text(r).strip() or (a.mode == "fulltext" and len((r.get("main_text") or "").strip()) > 500): todo.append((k, r))
        s0 = spend(con)
        if s0 >= a.cap:
            print(f"BUDGET STOP before {stem}: ${s0:.3f} >= cap ${a.cap}", flush=True); break
        t0 = time.time(); errs = 0
        def job(it):
            k, r = it
            if _stop.is_set(): return k, r, None, None, 0, "skipped (budget)"
            got = []; model = None; tok = 0
            try:
                for b in bodies(r, a.mode):
                    pr, model, t = call(b, crit, key); got.append(pr); tok += t
                probs = {c["id"]: max(g[c["id"]] for g in got) for c in crit}
                return k, r, probs, model, tok, None
            except Exception as e:  # noqa: BLE001
                return k, r, None, model, tok, str(e)[:160]
        with ThreadPoolExecutor(a.workers) as ex:
            futs = [ex.submit(job, it) for it in todo]
            for i, f in enumerate(as_completed(futs), 1):
                k, r, probs, model, tok, err = f.result()
                if err == "skipped (budget)": continue
                cost = 0.0
                rec = {"k": k, "stem": stem, "id": r["id"], "mode": a.mode, "probs": probs, "model": model, "tokens": tok, "cost": cost, "err": err, "ts": time.time()}
                with _lock:
                    with open(SCORES, "a") as fh:
                        fh.write(json.dumps(rec) + "\n"); fh.flush(); os.fsync(fh.fileno())
                    con.execute("insert or replace into s values (?,?,?,?,?,?,?,?,?,?)", (k, stem, r["id"], a.mode, json.dumps(probs) if probs else None, model, tok, cost, err, rec["ts"]))
                    if i % 50 == 0:
                        con.commit()
                        if spend(con) >= a.cap: _stop.set(); print(f"BUDGET STOP mid {stem}", flush=True)
                if probs: res[r["id"]] = probs; models[model] = models.get(model, 0) + 1
                else: errs += 1; print("  ERR", stem, r["id"], err, flush=True)
        con.commit()
        out = []
        for r in rows:
            pr = res.get(r["id"])
            out.append({"id": r["id"], "label": int(float(r["label"])), "p_include": p_include(pr, crit) if pr else "",
                        "weight": r.get("weight") or 1.0, "review_id": r.get("review_id") or m.get("review_id", ""), "error": 0 if pr else 1,
                        **{f"p_{c['id']}": (pr or {}).get(c["id"], "") for c in crit}})
        with open(od / f"{stem}_{suffix}_scores.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)
        print(f"{stem} {suffix}: n={len(rows)} new={len(todo)} errs={errs} {time.time()-t0:.0f}s spend=${spend(con):.4f} models={models}", flush=True)
        if _stop.is_set(): break
    print(f"DONE spend=${spend(con):.4f} models={models}", flush=True)
    
if __name__ == "__main__":
    main()
