# SyRev validation: 310 public systematic review datasets

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23399663.svg)](https://doi.org/10.5281/zenodo.23399663)

This repository holds the per-review results, criteria and scripts behind the validation published at
**https://syrev.ai/validation**. SyRev (https://syrev.ai) is a web app for AI-assisted title/abstract screening
in systematic reviews. (SyRev is not Sysrev, which is a separate, unrelated product.)

Report DOI: **10.5281/zenodo.23399663** (published on Zenodo: https://doi.org/10.5281/zenodo.23399663).

## Summary

| | Value |
|---|---|
| Public review datasets | 310 |
| Records scored | 442,208 (from search pools totalling 565,191 records) |
| Relevant studies (includes) in the scored records | 9,707 |
| Recall at Careful (default threshold, 0.001) | **96.5%** (344 relevant studies auto-excluded) |
| Recall at Rapid (threshold 0.005) | 91.5% |
| Reviews below 95% recall at Careful | 31 (29 of them among the 166 reviews with 5+ includes) |

**Records without a title or abstract.** 1,078 records had neither a title nor an abstract, so there was no text to
score and they were left out before scoring; the 442,208 figure excludes them. 26 of those records were relevant
studies. Counting those 26 as missed would put overall recall at Careful at **96.2%** instead of 96.5%.

Figures: `results/headline.json`; per review: `results/per_review_metrics.csv` and `results/metrics_table.md`.

## Definitions

* `p_include` is the product of the probabilities for each required eligibility criterion.
* A record is auto-excluded when `p_include` is below the threshold (Careful 0.001, Rapid 0.005); everything else goes to a person.
* Recall = relevant studies not auto-excluded / all relevant studies. Sampled datasets use inverse-probability weights for non-includes.
* WSS@95 = work saved over sampling at 95% recall.

## Repository layout

```
manifests/   one JSON per dataset group: review id, record counts, includes, criteria source
criteria/    the eligibility criteria used for each review (YAML), derived from each review's published selection criteria
results/     headline.json, per_review_metrics.csv, metrics_table.md
scripts/     prep_*.py (build datasets from the public sources), score.py (scoring), metrics.py (metrics)
```

## Reproducing the results

1. **Get the data** (not redistributed here; see the licences below) into `external/` and `raw/`, then run the
   `scripts/prep_*.py` scripts to build `data/<stem>.csv`. Sampling seeds are fixed in the scripts.
   `prep_swift_bb.py` calls NCBI E-utilities; set `NCBI_EMAIL` to your address.
2. **Score.** `scripts/score.py` reproduces how the SyRev app builds the text it scores and combines criterion
   probabilities. **Reproducing SyRev's exact scores needs access to SyRev's scorer, which is not publicly available.**
   The script talks to any endpoint you configure (`SCORER_URL`, `SCORER_API_KEY`; request/response shape in
   `call()`), so you can plug in your own scorer and compare. For access to the scorer or to the per-record scores,
   contact privacy@syrev.ai.
   ```
   pip install -r requirements.txt
   python scripts/score.py --manifest manifests/manifest_synergy.json --data-dir data --criteria-dir criteria --outdir synergy
   ```
3. **Metrics.** `python scripts/metrics.py` reads the score files in `out/` and writes `results/`.

The per-record scores and the scorer version for each result are available on request (privacy@syrev.ai).

## Data sources and licences

| Source | Where | Licence |
|---|---|---|
| CLEF TAR 2018 and 2019 | github.com/CLEF-TAR/tar | MIT |
| CSMeD and CSMeD-FT | github.com/WojciechKusa/systematic-review-datasets | Apache-2.0 code; CSMeD-FT data CC BY 4.0 |
| SWIFT-Review sets | Howard et al. 2016, doi.org/10.1186/s13643-016-0263-z (via CSMeD) | see source |
| SYNERGY | github.com/asreview/synergy-dataset | CC0 |
| Appenzeller-Herzog 2020 | doi.org/10.5281/zenodo.3625931 | CC BY 4.0 |
| Bannach-Brown et al. | zenodo.org/records/151190; held-out labels at github.com/abannachbrown/The-use-of-text-mining-and-machine-learning-algorithms-in-systematic-reviews | CC BY 4.0; held-out labels GPL-3.0 |
| Chan et al. 2025 | data.mendeley.com/datasets/7sgmg89zb6/1 | CC BY 4.0 |

## Limitations

Many gold labels are final (full-text) review decisions while SyRev scores titles and abstracts, so the test is
harder than normal abstract screening. Benchmarks contain errors (e.g. apparent record-linkage errors). Results
vary by review; 31 reviews were below 95% recall at Careful. See https://syrev.ai/validation for the discussion.
SyRev is a screening aid; final eligibility decisions stay with the review team.

## Licence

Code (`scripts/`): MIT, see `LICENSE`. Results, manifests and criteria: CC BY 4.0, see `LICENSE-RESULTS`.
Third-party datasets keep their own licences (table above).

## Citation

See `CITATION.cff`. Until the DOI is published, cite: SyRev Team (CERTAVI TECHNOLOGIES - FZCO). *SyRev validation on
310 public systematic review datasets*, v1.0, 2026. https://syrev.ai/validation

## Citation

SyRev Team (2026). *SyRev title/abstract screening: validation on 310 public systematic-review datasets* (v1.0). Zenodo. https://doi.org/10.5281/zenodo.23399663

See also [CITATION.cff](CITATION.cff).
