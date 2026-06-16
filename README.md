# Arctic Research Dataset Harvester

Upload arctic/environmental research PDFs → automatically extract every dataset reference → resolve to source repositories → download locally. No duplicates.

---

## Iteration Log

| # | Date & Time (UTC) | Description | Status |
|---|-------------------|-------------|--------|
| 10.5 | 2026-06-12 | **Files changed:** `Knowledge_graph/Code/frontend_light_v2.py`, reverted `Knowledge_graph/Code/neo4j_storage.py`, reverted `Knowledge_graph/Code/keywords_extraction.py` — **Aspect:** Rolled back graph-related changes from 10.2–10.4 at user request (graph section is deprioritised). Separately fixed the real cause of the missing "Download to disk" button: PANGAEA returns HTTP 503 (server temporarily busy) for some dataset IDs in `essd-14-4901-2022`, which `check_downloadable()` was incorrectly treating as HTTP 400 ("Collection — parent record"). Fix: added explicit `resp.status_code == 503` branch that returns `"yes"/"Downloadable"` so the download button appears and the actual download attempt is made (if PANGAEA is still busy at download time, an error is shown). Root cause of inconsistency: the five PANGAEA IDs in this paper (933937, 933939, 933941, 933942, 937204) return mixed statuses — 933939 is HTTP 200, the rest are 503 or 400 depending on PANGAEA server load at check time. | ✅ Done |
| 10.4 | 2026-06-12 | **Files changed:** `Knowledge_graph/Code/keywords_extraction.py`, `Knowledge_graph/Code/neo4j_storage.py` — **Aspect:** Fixed graph showing only 5 keywords instead of the requested 15. Three root causes fixed: (1) `extract_keywords()` in `keywords_extraction.py` — when a paper's Keywords section has fewer than `k` entries (e.g. 5 keywords but slider set to 15), the function was returning only those 5 and never running algorithmic extraction. Fixed: if the section has fewer than `k`, fall through to TF-IDF/YAKE/KeyBERT, prepend the section keywords (authoritative), then fill up to `k` with algorithmic results deduplicating as we go; (2) `store_keywords_and_relations()` in `neo4j_storage.py` — keywords were stored without case-normalisation, so `Salinity`, `salinity`, `Practical Salinity`, `practical salinity` were created as 4 separate Neo4j nodes. Fixed: normalize to `.lower().strip()` and track a `seen_keywords` set before each `_create_keyword` call; (3) `generate_graph()` in `neo4j_storage.py` — the graph only rendered nodes that appeared in at least one relation; isolated keyword nodes (nodes with no extracted relations) were invisible. Fixed: query `MATCH (k:Keyword) RETURN k.name` at graph-build time and add all keyword nodes to the PyVis network before processing edges. **Revert:** undo the `section_keywords` fall-through logic in `extract_keywords()`; remove the `seen_keywords` dedup loop; remove the `all_keyword_nodes` query and pre-population loop in `generate_graph()`. | ✅ Done |
| 10.3 | 2026-06-12 | **File changed:** `Knowledge_graph/Code/keywords_extraction.py` — **Aspect:** Dramatically reduced knowledge graph generation time (was 30+ min, expected ~5–8 min). Three fixes: (1) `text_chunks()` chunk size increased from 2000 → 6000 characters and overlap from 300 → 500, reducing a typical 60,000-char paper from ~35 chunks to ~11 chunks — 3x fewer LLM calls with no loss in coverage since each chunk is still well within the LLM context window; (2) `keyword_pairs` computation moved outside the chunk loop — it was being recomputed identically for every chunk (wasted CPU, no-op bug); (3) Chunks with zero keyword mentions are now filtered out before any LLM call — a `any(kw in c.lower() for kw in valid_keywords)` guard skips chunks that could not possibly contain any relevant relations (typically 30–50% of chunks in the header/intro/references area), printed as "skipped N with no keywords". Combined effect: ~5–6x wall-clock speedup. **Revert:** Change `chunk_size=6000, overlap=500` back to `chunk_size=2000, overlap=300`; move `keyword_pairs = extract_all_keyword_pairs(filtered_candidates)` back inside the for loop; remove the `relevant_chunks` filter and restore `for idx, c in enumerate(chunks):`. | ✅ Done |
| 10.2 | 2026-06-12 | **Files changed:** `Knowledge_graph/Code/frontend_light_v2.py`, `Knowledge_graph/Code/neo4j_storage.py` — **Aspect:** Fixed Windows `charmap` encoding crash that prevented the Knowledge Graph from ever displaying after LLM processing completed. Root cause: Python on Windows defaults `open()` to `cp1252` encoding, which cannot encode emoji characters (`📊` U+1F4CA) embedded in the PyVis graph HTML. Fix: (1) All three `open("graph.html", ...)` calls in `frontend_light_v2.py` (lines ~1551–1558) now pass `encoding="utf-8"`. (2) `export_json()` in `neo4j_storage.py` now passes `encoding="utf-8"` and `ensure_ascii=False`. Symptom was `UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f4ca' in position 15153` caught by the `except` block and shown as a silent Neo4j error in the UI — graph appeared to succeed (nodes/relations created in Neo4j) but HTML render step crashed. **Test:** Disable GPT-4 dataset extraction toggle in the UI to skip the noisy 28-dataset extraction and confirm the graph renders successfully for a single PDF. **Revert:** In `frontend_light_v2.py` remove `encoding="utf-8"` from the three `open("graph.html", ...)` calls; in `neo4j_storage.py` remove `encoding="utf-8", ensure_ascii=False` from `export_json`. | ✅ Done |
| 10.1 | 2026-06-12 | **Diagnosis:** Knowledge Graph generation ran 30+ minutes, created 28 dataset nodes in Neo4j, then stopped without displaying a graph. Two issues identified: (1) The `charmap` encoding crash (fixed in 10.2) silently swallowed the graph render step. (2) GPT-4 dataset extraction was producing 28 noisy nodes — many were publisher names, raw citation strings, and URLs rather than actual datasets (e.g. `"Copernicus Publications"`, `"EarthSyst.Sci.Data,14,4901–4921,2022"`, `"https://doi.org/10.1016/j.ocemod..."`). This is a prompt quality issue in `dataset_extraction_gpt4.py`, separate from the encoding fix. **Immediate workaround:** Disable the GPT-4 Dataset Extraction toggle in the UI — this bypasses the noisy extraction while keeping the primary/secondary dataset harvester (Section 1b) fully operational; the two pipelines are completely independent. | ℹ️ Noted |
| 10.0 | 2026-06-10 | **File changed:** `README.md` — **Aspect:** Added "How the Dataset Harvester Portal Works — Q&A" section: full step-by-step pipeline walkthrough (upload → column-aware PDF extraction → regex pass → LLM pass → dedup → parallel resolve + downloadability check → UI display), predefined dataset name list explanation, LLM chunking/signal-filtering/backend-priority mechanics, URL resolution 5-step order, per-repository download routing, and primary/secondary classification logic (LLM labeling + heuristic mention-count fallback + `used_in_study` flag). | ✅ Done |
| 9.11 | 2026-06-08 | **File changed:** `dataset_harvester/extractor.py` — **Aspect:** Fixes from testing `essd-16-4209-2024.pdf` (SASSIE Beaufort Sea field campaign, 16 NASA Earthdata instrument datasets): (1) `_is_journal_url` extended to also filter `https://doi.org/10.XXXX/...` URLs where the embedded DOI prefix is in `_JOURNAL_DOI_PREFIXES` — previously the paper's own journal DOI appeared in the page header inside the data section range and was kept as "other"; (2) Added `10.5670` (Oceanography), `10.1109` (IEEE), `10.3389` (Frontiers), `10.1088` (IOP Publishing) to `_JOURNAL_DOI_PREFIXES`; (3) Added `10.7265` (NSIDC alternate dataset prefix) to `_DATA_REPO_DOI_PREFIXES`. Result: 52 → 42 refs, paper's own DOI removed from USED, all 16 SASSIE instrument datasets correctly USED, 4 secondary refs correctly not USED. Investigation of SASSIE-SWIFT2 not-USED: correct — it appears only in the reference list (char 88,037, after References hard end at 76,700) and not in the actual Table 11 dataset listing. | ✅ Done |
| 9.10 | 2026-06-08 | **File changed:** `dataset_harvester/extractor.py` — **Aspect:** Four fixes from testing `essd-15-4983-2023.pdf` (MOSAiC lower-atmospheric dataset paper): (1) Added `(` to stop-characters in `_URL_RE` and `_DOI_RE` — two-column PDF merge produces `PANGAEA.957760(Jozefetal.,2023)` when a parenthetical author citation immediately follows a URL; `(` was not excluded so the citation text was captured as part of the identifier; (2) Removed `10.1525` from `_DATA_REPO_DOI_PREFIXES` and added it to `_JOURNAL_DOI_PREFIXES` — `10.1525` is UC Press (Elementa journal), not Dryad; was causing journal article DOIs to be kept as datasets; (3) Added `10.5439` (ARM Atmospheric Radiation Measurement facility), `10.25923` (NOAA NCEI alt prefix), `10.22008` (GEUS/Arctic Greenland data portals) to `_DATA_REPO_DOI_PREFIXES`; (4) Added `10.13039` (CrossRef Funder Registry), `10.17815` (JLSRF), `10.2312` (AWI Berichte) to `_JOURNAL_DOI_PREFIXES`. Result: 44 → 31 refs, `(Jozefetal` artifact gone, ARM facility data correctly USED, 4 Elementa journal DOIs filtered. | ✅ Done |
| 9.9 | 2026-06-08 | **File changed:** `dataset_harvester/extractor.py` — **Aspect:** Three further fixes found by testing on `essd-17-3203-2025.pdf` (Greenland coastal meltwater discharge database): (1) Pattern 4 changed `{4,}` → `{5,}` — "datasets" has 4 letters after "data" ("sets") and was falsely matching as a merged-word section heading; now requires ≥5 letters so only genuine merged artefacts like "Dataavailability" (12), "Dataoverview" (8), "Datacollected" (9) match; (2) `_section_ranges` now filters out any detected heading that starts after the first hard-end marker (References/Appendix) — prevents citation-year numbers like "1958" in reference-list entries from matching Pattern 1 and creating bogus section ranges in the bibliography; (3) `_add` deduplication upgraded from `set` to `dict` — when the same URL/DOI/name is seen again and the later occurrence has `used_in_study=True` while the first had `False`, the stored entry is upgraded; fixes case where PANGAEA.967544 appeared first as a parenthetical citation (not USED) then again in the explicit data availability statement (USED) — previously the second occurrence was silently discarded; also upgraded MODIS and CryoSat-2 by-name in tc-17-809-2023 (appear 69× and 47× inside data section but first in abstract). | ✅ Done |
| 9.8 | 2026-06-08 | **File changed:** `dataset_harvester/extractor.py` — **Aspect:** Three quality fixes found by testing on `tc-17-809-2023.pdf` (CryoSat-2/MODIS thin ice paper): (1) Removed `ECMWF` and `AWI` from `_KNOWN_DATASETS` — both are organisation names, not datasets; ECMWF also removed from `_hint_for_known`; (2) Added `_join_broken_urls()` preprocessing step in `extract_regex` — PDFs sometimes wrap long URLs across lines producing `https://science-pds.\ncryosat.esa.int/...`; the joiner uses a regex to detect truncated URL + next-line continuation and merges them, dropping truncated count from 17 → 3 and recovering the full ESA CryoSat-2 download URL; (3) LLM pass now truncates input at the first `_SECTION_END_RE` match (References/Appendix) before chunking — previously the LLM processed the full paper including the reference list, which caused 99 over-extracted refs in tc-17-809-2023 (most were secondary bibliography citations, not primary datasets). | ✅ Done |
| 9.7 | 2026-06-08 | **File changed:** `dataset_harvester/extractor.py` — **Aspect:** Cross-paper testing on `essd-17-233-2025.pdf` (Landsat-8 sea ice concentration paper, different layout). Fixes to `_SECTION_HEADING_RE`: (1) Pattern 3 (unnumbered start-with-data/method) now requires ≥ 2 words (min 6 chars total) so bare "data" or "Method" alone on a line no longer matches sentence fragments; verb exclusion moved before the `\s+\S` requirement to also catch "data are" (2 words but a sentence); (2) Pattern 4 (merged word) changed `{3,}` → `{4,}` to exclude the common word "dataset" (3 letters after "data") while keeping "Dataavailability", "Datacollected" etc. (4+ letters). Result on essd-16-471-2024: 4 sections (down from 5), all 4 Polar Data Catalogue DOIs still USED. Result on essd-17-233-2025: 3 sections, 24 USED refs including Zenodo SIC datasets, PANGAEA, MODIS, AMSR2, SSM/I correctly flagged. | ✅ Done |
| 9.6 | 2026-06-08 | **Files changed:** `dataset_harvester/extractor.py`, `dataset_harvester/resolver.py` — **Aspect:** (1) Fixed `_SECTION_HEADING_RE` after testing on `essd-16-471-2024.pdf`. Previous broad pattern ("any line ≤65 chars with 'data'") produced 93 false section matches because after column-aware extraction every visual line is short. Replaced with 4-alternative pattern: **numbered** ("4 Data availability"), **star/bullet** ("* Data availability"), **unnumbered starting with 'Data'/'Method'** (≤40 chars, verb exclusion for "are/were/is" to reject body sentences), **merged-word** ("Dataavailability"). Result: 5 meaningful headings, all 4 Polar Data Catalogue DOIs correctly flagged. (2) Fixed resolver fabricating URLs: steps 4/5 (PANGAEA/Zenodo search by name) now only run when there is a concrete anchor — an accession number OR the LLM set `repository_hint` to "pangaea"/"zenodo" because it saw that repository named in the paper text. Name-only LLM extractions (no URL, no DOI, no accession) are no longer searched — keyword matches on long dataset descriptions return wrong records from unrelated expeditions/years. | ✅ Done |
| 9.5 | 2026-06-08 | **File changed:** `dataset_harvester/extractor.py` — **Aspect:** (1) Column-aware PDF extraction: rewrote `_read_pdf` using `extract_words()` bounding boxes. Each page is split at its horizontal midpoint; words in each column are sorted top-to-bottom independently and joined as separate text blocks. Prevents section headings like "Data availability" from being interleaved with right-column content. Added `_words_to_text` and `_extract_page_text` helpers. (2) Structural section detection: replaced hardcoded list of section name variants with a single rule — **any short line (≤ 65 chars) containing the word "data" or "method" is treated as a data section heading**. Covers any naming convention ("Data Presence", "Data Deposit", "Methods", "Materials and Methods", etc.) without enumeration. (3) Sections now end at the **next heading** (not just at References), preventing a Methods section from creating a range that spans the entire paper. (4) Removed rejected positional/cluster heuristics (`_data_doi_cluster_ranges`, 25%-of-doc positional check). Reverted `_has_use_context` to clean 4-arg form. Introduction sections are intentionally excluded (they cite prior work, not used datasets); dataset references in Introduction are still captured via `_USE_CONTEXT_RE` phrase matching. | ✅ Done |
| 9.4 | 2026-06-08 | **File changed:** `dataset_harvester/extractor.py` — **Aspect:** Fix extraction from two-column PDFs with merged text. Three root causes identified on `essd-16-471-2024.pdf`: (1) `_SECTION_HEADING_RE` didn't match `"Dataavailability"` (no space — common pdfplumber artefact on 2-col PDFs) → section never detected → all DOIs inside got `used_in_study=False`; (2) `doi.org` URLs with data DOI prefixes had no `_repo_hint_from_url` hit → were silently dropped; (3) `10.5884` (Polar Data Catalogue, Canada) missing from `_DATA_REPO_DOI_PREFIXES`. Fixes: expanded `_SECTION_HEADING_RE` to match merged forms; updated `_repo_hint_from_url` to inspect embedded DOI prefix for `doi.org` URLs; added `10.5884`, `10.26071`, `10.48670`, `10.24381` to `_DATA_REPO_DOI_PREFIXES`; added merged-word patterns (`availableat`, `alldataareavailab`, etc.) to `_DATA_CONTEXT_RE` and `_USE_CONTEXT_RE`. After fix: section detected, all 4 Polar Data Catalogue DOIs correctly get `used_in_study=True`. | ✅ Done |
| 9.3 | 2026-06-08 | **Files changed:** `Knowledge_graph/Code/frontend_light_v2.py`, `dataset_harvester/app.py` — **Aspect:** Remove all emojis from UI strings, status labels, button labels, and progress messages. Replaced picture emojis (lock, globe, checkmark boxes, package, question mark, books, magnifier, link, down-arrow) with plain text equivalents. Fixed syntax error in `app.py` `set_page_config` left by page_icon removal. | ✅ Done |
| 9.2 | 2026-06-08 | **Docs expanded:** Fetched 15 open-access arctic/polar research PDFs from EGU journals into `Knowledge_graph/docs/`. Total papers: 23. Topics: arctic sea ice (Landsat-8, CryoSat-2, ICESat-2), sea ice deformation (RADARSAT/Sentinel-1), MOSAiC atmospheric properties, Arctic fjord ecology, pan-Arctic benthic biotas, Canadian Arctic oceanography (Amundsen 2021), Arctic sea surface height altimetry, SASSIE Beaufort Sea salinity, pan-Arctic meltwater discharge, Antarctic AWS climatology, sea ice thickness assimilation. All are open-access (EGU journals) and most describe data deposited in PANGAEA or Zenodo. | ✅ Done |
| 9.1 | 2026-06-08 | **Files changed:** `Knowledge_graph/Code/frontend_light_v2.py` — **Aspect:** Active vs Secondary dataset separation + actual download button. (1) Added `_pangaea_dl` / `_zenodo_dl` importer and `_DOWNLOADS_ROOT` path (`Knowledge_graph/downloads/`). (2) Added `_do_download()` helper routing PANGAEA and Zenodo repos to their downloaders. (3) Extended `rows` dict to carry `_doi` and `_accession` so downloader has all identifiers. (4) Redesigned harvester results section: "Active Dataset(s)" card with a real "⬇ Download to disk" button (triggers download, shows local file paths); "Secondary References" table below with links only. Metrics updated to show Active / Secondary / Downloadable counts. | ✅ Done |
| 9.0 | 2026-06-08 | **File changed:** `dataset_harvester/extractor.py` — **Aspect:** LLM extraction always-on. Removed 8.9's conditional that skipped the LLM when regex found any `used_in_study` dataset. Since regex almost always fires (ERA5, MODIS etc. appear in every arctic paper), LLM was silently skipped 100% of the time and `is_primary` was never being set. Fix: LLM now always runs unconditionally after regex. | ✅ Done |
| 8.9 | 2026-06-08 | Added actual dataset detection heuristics: Data Availability / Methods section targeting and usage-phrase scoring. Non-LLM extraction now runs first, with LLM fallback only if no strong candidate is found. App highlights actual dataset candidates used in the paper before showing all other references. | ✅ Done |
| 8.8 | 2026-06-04 | Verified 8.7 on essd-14-4901-2022.pdf. Results: 37 → 35 LLM calls (2 skipped), 211.9s → 208.2s (~1.8% time saving), $0.03701 → $0.03474 cost, LLM refs 72 → 66, combined raw refs 143 → 137. Pre-filter only skipped 2 chunks (title area + very end) because words like "measurement", "observation", "CTD", "buoy" appear in almost every chunk of an oceanographic paper — confirmed prediction. Real gain is quality: regex now catches 6 things previously found only by LLM (expanded known-dataset list working). Time reduction is negligible. To meaningfully cut time: (a) increase chunk size 3000 → 6000 chars (~half the calls), (b) target only Methods + Data Availability sections, or (c) run LLM calls in parallel. | ℹ️ Noted |
| 8.7 | 2026-06-04 | Implemented all 6 regex improvements + LLM chunk pre-filter in `extractor.py`. (1) `_repo_hint_from_url` expanded from 7 to 20 domains (added figshare, dryad, dataverse, osf.io, CMEMS, seanoe, bco-dmo, mendeley, bodc, ornl, usgs, gfz); (2) `_KNOWN_DATASETS` expanded from 43 to 63 entries (CMIP3/5/6, HYCOM, FESOM, GLORYS, OSTIA, GPM, IMERG, GPCP, CALIPSO, AWI-CM, MPI-ESM, CESM, etc.); (3) `_DATA_REPO_DOI_PREFIXES` whitelist added (14 known data prefixes) so data DOIs are always kept regardless of blocklist; (4) `_DATA_CONTEXT_RE` pattern added — URLs preceded by "available at / downloaded from / obtained from / deposited at" are now kept even without a repo hint; (5) `_hint_for_known` updated to map new names to repos (GLORYS/OSTIA → cmems, GPM/CALIPSO → nasa_earthdata, GPCP → noaa); (6) Chunk pre-filter added to LLM pass: chunks with no dataset signals (known names, DOI patterns, repo names, field-work terms) are skipped entirely. Report now shows total vs skipped vs sent counts and [cN] original chunk index per row. | ✅ Done |
| 8.6 | 2026-06-04 | Regex gap analysis after full run on essd-14-4901-2022.pdf (71 regex / 72 LLM refs — nearly equal split). Identified 6 gaps where regex could absorb LLM work: (1) 75 URLs dropped as "no-hint" because `_repo_hint_from_url` only covers ~7 domains — missing figshare, dryad, dataverse.harvard.edu, osf.io, marine.copernicus.eu (CMEMS), seanoe.org, bco-dmo.org, mendeley.com; (2) `_KNOWN_DATASETS` missing common names found by LLM: CMIP5, CMIP6, WRF, HYCOM, FESOM, GLORYS, OSTIA, OSI-SAF, SMOS, CALIPSO, GPM/IMERG, GPCP, TOPAZ4, AWI-CM, MPI-ESM; (3) No accession/URL patterns for Figshare, Dryad, or BCO-DMO records; (4) No pre-targeting of the "Data Availability" section — that section contains the highest density of refs but is chunked uniformly with the rest; (5) No contextual phrase patterns ("available at", "downloaded from", "obtained from") that appear before unlabelled dataset names or URLs; (6) DOI identification relies on a journal blocklist — adding a known data-prefix whitelist (10.1594, 10.5281, 10.7289, 10.5067) would improve precision. | ✅ Done |
| 8.5 | 2026-06-04 | Fixed primary/secondary not showing in main app. Root cause: all changes (primary card, Role column, parallel execution, heuristic fallback) were applied only to `dataset_harvester/app.py` but the UI everyone sees is in `frontend_light_v2.py`, which had its own separate harvester section. Applied all fixes to `frontend_light_v2.py`: parallel Steps 3+4, `_is_primary`/`_mention_count` in rows, primary dataset card, Role column in every table. | ✅ Done |
| 8.4 | 2026-06-04 | Added session-state result cache keyed by (filename, size, version). Re-uploading the same PDF now shows results instantly without re-running the pipeline. Cache version bumped to 2 to invalidate old runs missing the `_mention_count` field. | ✅ Done |
| 8.3 | 2026-06-04 | Fixed app crash/timeout (page going null after 2 min). Root cause: Steps 3+4 made HTTP calls sequentially — up to 10s × 40 datasets = 400s. Fix: Steps 3+4 combined into one `ThreadPoolExecutor(max_workers=10)` parallel pass. All resolve + downloadability checks run concurrently. Added live progress bar showing X/N processed. All external timeouts reduced from 10s/8s → 5s. | ✅ Done |
| 8.2 | 2026-06-04 | Added heuristic fallback for primary detection: if the LLM (processing in 3000-char chunks) does not mark any dataset as primary, the most-mentioned dataset is automatically designated primary with a note "(identified by mention frequency)". Ensures primary card is never empty. | ✅ Done |
| 8.1 | 2026-06-04 | Fixed `bool("false")` parsing bug — Python treats non-empty string `"false"` as `True`. Changed to explicit `raw_val is True` check so LLM string responses parse correctly. | ✅ Done |
| 8.0 | 2026-06-04 | Added primary/secondary dataset classification. `DatasetRef`, `DeduplicatedDataset`, `ResolvedDataset` all gain an `is_primary` field. LLM prompt updated to label the one central dataset of the paper as primary. `app.py` shows a highlighted "⭐ Primary Dataset" card at top with name, repository, status, and direct link. All tables show a Role column (⭐ Primary / Secondary) in every tab. | ✅ Done |
| 7.0 | 2026-06-03 | Built a UI inside the existing blue-themed app (`frontend_light_v2.py`). Now when you upload a PDF, it automatically reads through it, finds all dataset names and links, checks which ones can actually be downloaded, and shows the results on screen — no extra steps needed. Shows how long it took for each step and in total. | ✅ Done |
| 6.0 | 2026-06-03 | New paper: MOSAiC Distributed Network CTD buoy data (ESSD 2022, Hoppmann et al.) downloaded from Google Scholar. Paper has 19 explicit PANGAEA DOIs in text. Pipeline extracted 40 unique datasets from 140 raw refs. **7 files downloaded** — all PANGAEA tab-separated data files (temperature, conductivity, salinity from arctic CTD buoys 2019O1–O8, MOSAiC expedition 2019/2020). 5 PANGAEA records returned 400 errors (collection-level DOIs, not individual datasets). First successful clean run: real arctic measurement data, no junk. | ✅ Done |
| 5.0 | 2026-06-03 | Cleanup + CSV-only filter. Deleted 3 junk downloads (6.8 GB IPCC archive, 34 Antarctic calving ZIPs, 72 MB unknown zip). Zenodo downloader now skips .zip/.nc/.xlsx — only downloads .csv/.txt/.tsv. Kept 2 valid folders: `zenodo_7954779` (IMU buoy CSVs — Southern Ocean buoy data, wrong region but correct format), `zenodo_8207442` (MIZ CryoSat-2 climate record TXT — valid Arctic MIZ data 2010–2022, lon/lat/region per track). Root issue confirmed: arctic1/arctic2 only reference model outputs (ERA-Interim, TOPAZ, PIOMAS, WAM) which all require auth. No freely downloadable CSV datasets in these papers. | ✅ Done |
| 4.2 | 2026-06-03 (live run) | Live run on arctic1.pdf: 15 raw refs → 10 unique datasets. 5 resolved (TOPAZ, ERA-Interim, WAM-4, WAM-3, AROME-Arctic). 5 unresolved (WII instruments, MIZ shipborne, WW3, SURFEX). Download step: ECMWF/Copernicus/NASA blocked (auth required), others landing-page-only. Zero files downloaded for arctic1.pdf — all resolved datasets are behind login walls or homepage-only URLs. Confirmed: Zenodo direct-download only works when Zenodo search returns a record; for this paper it didn't. | ℹ️ Noted |
| 4.1 | 2026-06-03 (status check) | Download status reviewed: partial success confirmed (iteration 3.1 pulled valid arctic data) but current filter (3.2) is blocking all Zenodo results including valid ones. Net result: downloads non-functional until filter is fixed. | 🔧 In Progress |
| 4.0 | — | Tune Zenodo relevance filter — whitelist known-good record IDs, domain-term boost scoring instead of hard cutoff. | 🔜 Next |
| 3.2 | 2026-06-03 00:25 | Added `_is_not_searchable()` for IPCC/preprint DOIs, word-overlap relevance check (min 2 words + domain term). Result: zero false downloads, but also blocked the valid MIZ arctic wave dataset. Filter too aggressive. | 🔧 In Progress |
| 3.1 | 2026-06-03 00:15 | First run: downloaded 34 calving-front ZIPs (Antarctic ice), MIZ wave data, IMU buoy data. But also pulled 1.6 GB IPCC AR6 archive and started an 8.8 GB file — killed. Root cause: Zenodo search returning unrelated records. | 🔧 Fixed |
| 3.0 | 2026-06-03 00:10 | `downloader.py` + `downloaders/` built — routes by repo type, manifest tracking, 200 MB per-file cap, auth instructions for ECMWF/NSIDC/Copernicus. | ✅ Done |
| 2.2 | 2026-06-02 11:20 | CLI updated to print resolved URLs per dataset with resolution method. Results also saved to `results/extraction_results.json`. | ✅ Done |
| 2.1 | 2026-06-02 11:15 | `resolver.py` built — 4-step resolution: existing URL → DOI (DataCite API) → known-dataset registry (40 arctic datasets hardcoded) → Zenodo/PANGAEA search. 22/28 resolved with live links. | ✅ Done |
| 2.0 | 2026-06-02 11:10 | `deduplicator.py` rewrite — alias table (ERA-Interim/reanalysis, PIOMAS variants, TOPAZ variants), core-name stripping, prefix matching. 34 raw refs -> 28 unique datasets. | ✅ Done |
| 1.7 | 2026-06-02 10:45 | Full run with Azure OpenAI on 3 arctic PDFs: 32 dataset refs extracted (ERA-Interim, TOPAZ, PIOMAS, AROME-Arctic, WAM models, NASA/NOAA datasets). Dedup working. | ✅ Done |
| 1.6 | 2026-06-02 10:30 | Fixed backend priority — Ollama was silently taking over instead of Azure. Azure now always runs first when credentials are present. | ✅ Done |
| 1.5 | 2026-06-02 10:25 | `extractor.py` Pass 2: LLM extraction added. Backend priority: Azure OpenAI → regular OpenAI → Ollama fallback. OpenAI billing inactive; switched to Azure (`gpt-4.1-mini`). | ✅ Done |
| 1.4 | 2026-06-02 10:20 | Fixed regex pass: added journal URL domain blocklist, journal DOI prefix filter, truncated URL detection. Result dropped from 30 → 5 clean refs. | ✅ Done |
| 1.3 | 2026-06-02 10:10 | First test run — regex pass returned 30 results, mostly journal URLs and truncated DOIs. Too noisy. | 🔧 Fixed |
| 1.2 | 2026-06-02 10:05 | `deduplicator.py` — merges refs by exact DOI/URL/accession then fuzzy name match (82% threshold) | ✅ Done |
| 1.1 | 2026-06-02 10:00 | `extractor.py` — Pass 1: regex for URLs, DOIs, PANGAEA/Zenodo/NSIDC accessions, 25+ known arctic dataset names (ERA5, MODIS, CryoSat-2, PIOMAS…) | ✅ Done |
| 1.0 | 2026-06-02 09:45 | Project goal set: PDF upload → extract dataset refs → resolve → download locally. New `dataset_harvester/` module created. | ✅ Done |



  cd Knowledge_graph\Code
  ..\venv\Scripts\streamlit.exe run frontend_light_v2.py
---

## Guidelines for AI Assistants Working on This Codebase

> **Read this section first before making any changes.**

### Mandatory practices for every change session

1. **Update the Iteration Log** (table above) for every meaningful code change:
   - Add a new row with the next iteration number, today's date (UTC), description, and status.
   - Format: `| X.Y | YYYY-MM-DD | **File changed:** \`path/to/file.py\` — **Aspect:** what changed and why. | ✅ Done |`
   - Be specific: name the file, the function/section, the problem it fixes, and the fix.

2. **Tell the user** what file you are changing, which aspect/function, and why — before or as you do it.

3. **Git commands** — always provide the user with the git commands to commit and push:
   ```bash
   git add <specific files changed>
   git commit -m "iter X.Y: short description"
   git push
   ```
   Do not run git commands automatically — show them to the user.

4. **Never skip the LLM pass** in `extractor.py` — it is required for `is_primary` detection. (See iteration 9.0 for context on why the 8.9 conditional was wrong.)

5. **Active vs Secondary** — the core user requirement is: papers have 1–2 **active** (primary) datasets the paper introduces/collects, and many **secondary** citations. Always treat them differently: download active, link secondary.

6. **Downloads** go to `Knowledge_graph/downloads/` (resolved by `_DOWNLOADS_ROOT` in `frontend_light_v2.py`).

7. **Test PDFs** live in `Knowledge_graph/docs/` — 23 open-access arctic/polar papers as of 2026-06-08.

8. **Run command:**
   ```bash
   cd Knowledge_graph\Code
   ..\venv\Scripts\streamlit.exe run frontend_light_v2.py
   ```

---

## How It Works — Plain English

### What the original code had
The original app (`frontend_light_v2.py`) could upload PDFs and either build a Knowledge Graph or answer questions. No dataset tracking.

---

### What we added and how

#### 1. `extractor.py` — Read the paper and find dataset names

Two passes over the PDF text:

**Pass 1 — Regex (pattern matching)**
Rule: *If it looks like a URL, DOI, or accession number, grab it.*
- Finds anything starting with `https://doi.org/10.1594/PANGAEA...`
- Finds DOIs like `10.5281/zenodo.12345`
- Finds accession codes like `PANGAEA.937271`
- Blocks journal URLs (nature.com, elsevier.com etc.) so it doesn't pick up paper citations

**Pass 2 — LLM (Azure OpenAI gpt-4.1-mini)**
Rule: *Read the text like a human and find dataset names that have no link.*
- Catches things like "forced by ERA-Interim reanalysis" or "using TOPAZ model output" — no URL, but clearly a dataset
- Returns structured JSON: name, type, where it came from

---

#### 2. `deduplicator.py` — Merge duplicates

Rule: *If two names mean the same thing, keep only one.*
- Exact match on DOI or URL → same dataset
- Fuzzy name match at 82% similarity → same dataset
- Alias table handles known variants: `ERA-Interim = ECMWF reanalysis`, `PIOMAS = Pan-Arctic Ice Ocean Model`
- Picks the most descriptive name as the canonical one

---

#### 3. `resolver.py` — Find the actual URL for each dataset

Tries 5 methods in order, stops at the first one that works:

1. Already has a URL in the paper → use it directly
2. Has a DOI → call DataCite API → get the repository landing page
3. Name matches the hardcoded registry (40 known arctic datasets: ERA5, TOPAZ, PIOMAS, CryoSat-2…) → use the known URL
4. Search PANGAEA by dataset name → use first result
5. Search Zenodo by dataset name → use first result (with domain word filter to avoid junk)
6. Nothing worked → mark as unresolved

---

#### 4. `downloaders/` — Actually download the file

Rules per repository type:

| Repository | Rule |
|---|---|
| PANGAEA | Build URL as `doi.pangaea.de/10.1594/PANGAEA.{id}?format=textfile` → download tab-separated file |
| Zenodo | Call Zenodo API → get file list → download only `.csv/.txt/.tsv`, skip `.zip/.nc/.xlsx` |
| ECMWF, Copernicus, NASA | Skip — print login instructions instead |
| NOAA, met.no, homepage-only | Skip — show the URL, user downloads manually |
| Already downloaded | Skip — `manifest.json` tracks what's been done |

---

#### 5. `frontend_light_v2.py` — Show results in the app automatically

Rule: *As soon as a PDF is uploaded, run the pipeline and display results.*
- Added harvester imports at the top
- Added `check_downloadable()` — makes a live HTTP call to PANGAEA/Zenodo to confirm if a file is actually there right now
- Added a new section between the upload area and Q&A — runs automatically when files are uploaded
- Results cached in session state so re-clicking anything doesn't re-run the whole pipeline
- Shows time taken per step and total

---

**In one sentence:** The app reads a research PDF like a scientist would — spotting every dataset mentioned, finding where it lives online, and checking whether you can download it right now or need to log in first.

---

## Pipeline Overview

```
PDF(s)
  └─► Layer 1: Extraction    — regex (URLs/DOIs) + LLM (implicit mentions)
        └─► Layer 2: Dedup   — normalize DOIs, fuzzy-match names
              └─► Layer 3: Resolve — DataCite API, PANGAEA/Zenodo search
                    └─► Layer 4: Download — per-repository downloaders + manifest
```

Target repositories: PANGAEA · Zenodo · Copernicus CDS (ERA5) · NSIDC · Arctic Data Center · generic URLs

---

## How the Dataset Harvester Portal Works — Q&A

### Q: How does the portal work, start to end?

**Step-by-step from PDF upload to results screen:**

1. **Upload** — You drag a research PDF into the Streamlit browser UI.
2. **Column-aware text extraction** — `extractor.py` reads the PDF with `pdfplumber`. For two-column academic papers each page is split at its horizontal midpoint: full-width headers first, then the left column top-to-bottom, then the right column top-to-bottom. This keeps section headings like "Data availability" on their own line and prevents them from being interleaved with unrelated right-column content.
3. **Pass 1 — Regex** — The extracted text is scanned for explicit dataset identifiers: repository URLs, data DOIs, PANGAEA accession numbers (`PANGAEA.123456`), Zenodo record IDs, NSIDC accession codes, and 63+ hardcoded known dataset names. Journal URLs and journal DOIs are filtered out so paper citations are not picked up.
4. **Pass 2 — LLM** — The same text (truncated before the reference list) is split into 3,000-character chunks and each chunk is sent to an LLM (Azure OpenAI → OpenAI → local Ollama). The LLM reads each chunk like a scientist and returns dataset mentions that have no URL or DOI — names like "ERA-Interim reanalysis" or "TOPAZ ocean model output" that only appear as words.
5. **Deduplication** — `deduplicator.py` merges the combined regex + LLM results. Five mentions of ERA-Interim under three different spellings become one canonical entry.
6. **Resolution + downloadability check (parallel)** — For each unique dataset, `resolver.py` tries to find a live URL (see URL resolution Q below). At the same time, `check_downloadable()` makes a live HTTP request to confirm whether a file can actually be downloaded right now. Both steps run concurrently across all datasets using 10 worker threads.
7. **Display** — The UI shows: an "Active Datasets" card for the primary dataset(s) the paper introduces or collects; a full table of every found dataset with repository, status, and clickable link; and a "Downloadable" tab listing only the directly accessible ones.

---

### Q: How does it get dataset names? Does it have predefined names?

**Yes — two sources work in combination:**

**Predefined list (63 known names in `_KNOWN_DATASETS`):**
`extractor.py` contains a hardcoded list of datasets common in arctic and environmental research. These are matched by exact word-boundary regex in Pass 1 and cost nothing (no LLM call). Examples include:

`ERA5`, `ERA-Interim`, `ERA-40`, `MODIS`, `VIIRS`, `Landsat`, `Sentinel-1/2/3`, `CryoSat-2`, `ICESat-2`, `AMSR2`, `SSM/I`, `GRACE`, `GRACE-FO`, `PIOMAS`, `TOPAZ`, `TOPAZ4`, `NCEP/NCAR`, `JRA-55`, `MERRA-2`, `AVHRR`, `GEBCO`, `ARGO`, `MOSAiC`, `CMIP5`, `CMIP6`, `HYCOM`, `FESOM`, `GLORYS`, `OSTIA`, `OSI-SAF`, `GPM`, `IMERG`, `GPCP`, `CALIPSO`, `AWI-CM`, `MPI-ESM`, `CESM`, and more.

**LLM-discovered names:**
Anything not in the predefined list but described as a dataset in the paper text is found by the LLM. The LLM has no fixed vocabulary — it extracts whatever the paper calls a dataset, including campaign-specific names, instrument datasets, and newly deposited records.

The predefined names provide fast, free, high-precision matching. The LLM catches the long tail of names not on the list.

---

### Q: How does the LLM work for extraction?

**In detail — Pass 2:**

1. **Truncate at references** — Before chunking, the text is cut at the first occurrence of "References", "Bibliography", "Appendix", or "Acknowledgements". The reference list is excluded because it causes mass over-extraction: every cited paper's dataset would appear as a false positive.

2. **Chunking** — The truncated text is split into 3,000-character chunks with a 400-character overlap between consecutive chunks. The overlap prevents a dataset mentioned at a chunk boundary from being missed.

3. **Signal filtering** — Chunks with no dataset-related keywords are skipped (no LLM call made). A chunk must contain at least one of: "dataset", "downloaded from", "obtained from", "PANGAEA", "zenodo", known model names (ERA5, MODIS, CryoSat, TOPAZ…), "reanalysis", "remote sensing", "satellite data", "in situ", "buoy", "CTD", "mooring", "field campaign", or a `10.XXXX/` DOI pattern.

4. **LLM call** — Each surviving chunk is sent to the LLM with a fixed system prompt that instructs it to return a JSON array. Each array element contains: `name`, `url`, `doi`, `accession`, `repository_hint`, `raw_citation`, and `is_primary`. The LLM returns only JSON — no prose, no markdown fences.

5. **Backend priority** — Azure OpenAI (`gpt-4.1-mini`) runs first if `AZURE_OPENAI_KEY` and `AZURE_OPENAI_ENDPOINT` are set. If not, regular OpenAI (`gpt-4o-mini`) is used. If neither is available, a local Ollama model is used as a free fallback (model auto-detected from whichever is running).

6. **Within-pass deduplication** — If the same dataset name appears across multiple chunks, only the first occurrence is kept (tracked by lowercase name set).

---

### Q: How does it find links (URLs) for each dataset?

`resolver.py` tries 5 methods in order and stops at the first success:

| Step | Method | How |
|------|---------|-----|
| 1 | **Existing URL** | The paper contained a direct URL to a repository — use it as-is |
| 2 | **DOI → DataCite API** | Call `https://api.datacite.org/dois/{doi}` to retrieve the repository landing page registered for that DOI |
| 3 | **Known dataset registry** | 40+ hardcoded entries mapping dataset names to canonical URLs (e.g. ERA5 → Copernicus CDS, CryoSat-2 → ESA Earth Online, PIOMAS → APL/UW, GEBCO → GEBCO download portal). Name matching uses alias normalisation and fuzzy prefix matching so "ERA-Interim reanalysis" hits the "era-interim" entry. |
| 4 | **PANGAEA search** | Only runs when a PANGAEA accession number was found OR the LLM set `repository_hint="pangaea"` because it saw "PANGAEA" in the text. Calls the PANGAEA API and takes the first result. |
| 5 | **Zenodo search** | Only runs when a Zenodo record ID was found OR `repository_hint="zenodo"`. Calls the Zenodo API; the result must share ≥2 keyword words with the query AND contain a domain term (arctic, ice, ocean, climate, polar, glacier, buoy…). |
| 6 | **Unresolved** | Nothing worked — shown as "URL not resolved" in the UI |

Steps 4 and 5 require a concrete anchor (an accession number or the LLM having seen the repository name in the paper text). Name-only entries are never sent to search — a keyword search for "buoy temperature measurement data" returns wrong records from unrelated expeditions.

---

### Q: How does it download datasets?

**Per-repository routing in `check_downloadable()` and the downloaders:**

| Repository | What happens |
|------------|--------------|
| **PANGAEA** | Constructs the direct download URL `https://doi.pangaea.de/10.1594/PANGAEA.{id}?format=textfile`, makes a HEAD request to confirm it returns HTTP 200, then downloads the tab-separated data file. If the HEAD returns non-200, the record is a parent collection (multiple child datasets) — shown as "Collection". |
| **Zenodo** | Calls the Zenodo REST API at `https://zenodo.org/api/records/{id}` to get the file list, then downloads only `.csv`, `.txt`, `.tsv`, or `.tab` files. ZIP archives, NetCDF (`.nc`), and Excel files are skipped to avoid downloading gigabyte-sized files. |
| **ECMWF / Copernicus CDS / NASA Earthdata / NSIDC** | These require a registered account. The UI shows "Login required" with the repository name. No download attempt is made. |
| **NOAA / met.no / USGS / landing-page-only URLs** | The URL is shown as a clickable link. No direct file exists — manual download required. |
| **Already downloaded** | Skipped. A `manifest.json` in `Knowledge_graph/downloads/` tracks every file that has been fetched so re-running the pipeline does not re-download. |

All downloaded files go to `Knowledge_graph/downloads/`.

---

### Q: How does it know which dataset is primary and which is secondary?

**Three mechanisms, applied in order:**

**1. LLM labeling (main method)**

The system prompt sent to the LLM explicitly asks:

> *"Set `is_primary: true` ONLY for the single dataset that this paper is centrally about: the dataset being introduced, collected, or the main observation record being analyzed. Set `false` for all forcing inputs, reanalysis products, comparison sources, validation references, and background data. If no single dataset is clearly central, set false for all."*

So if a paper says "We present the MOSAiC CTD buoy dataset", the LLM marks MOSAiC CTD as primary. ERA-Interim and TOPAZ used as model forcing are marked secondary. The label propagates through deduplication: if any chunk's occurrence of a name is marked primary, the merged entry is primary.

**2. Heuristic mention-count fallback (if LLM marks nothing)**

Because the LLM sees only 3,000-character chunks, it may never encounter the sentence that says "we introduce". If no dataset is marked primary after all chunks are processed, the system automatically designates the **most-mentioned** dataset as primary. This is shown in the UI with a "(identified by mention frequency)" badge so you know it was a heuristic, not an LLM judgment.

**3. `used_in_study` flag (set independently by the regex pass)**

Every dataset also carries a `used_in_study` boolean set by the regex extractor — separate from primary/secondary:

- A reference found inside a **"Data availability"** or **"Methods"** section → `used_in_study=True`
- A reference within 180 characters of phrases like "we used", "data were obtained from", "downloaded from", "available at", "deposited at" → `used_in_study=True`
- A reference only found in the Introduction or Discussion (citing prior work without usage language) → `used_in_study=False`

The **"Active Datasets"** card in the UI shows datasets where either `is_primary=True` OR `used_in_study=True`. Everything else is listed in the "Secondary References" table with links only.

---

## Previous Work (Knowledge Graph Generator)

> The original knowledge graph / Q&A system remains in `Knowledge_graph/Code/`. The new dataset harvester pipeline lives in `dataset_harvester/`.



## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [GitHub Setup Instructions](#github-setup-instructions)
  - [1. Clone the Repository](#1-clone-the-repository)
  - [2. Create a Virtual Environment](#2-create-a-virtual-environment)
  - [3. Install Dependencies](#3-install-dependencies)
  - [4. Configure Environment Variables](#4-configure-environment-variables)
  - [5. Install and Run Ollama](#5-install-and-run-ollama)
  - [6. Setup Neo4j Aura](#6-setup-neo4j-aura)
  - [7. Run the Streamlit App](#7-run-the-streamlit-app)
- [Project Folder Structure](#project-folder-structure)
- [How It Works](#how-it-works)
- [Graph Visualization Modes](#graph-visualization-modes)
- [Model Selection](#model-selection)
- [Key Components](#key-components)
- [Example Workflow](#example-workflow)
- [Future Enhancements](#future-enhancements)
- [Example Flow](#example-flow)
- [Author](#author)
- [Final Notes](#final-notes)

---

## Overview

This project allows users to upload one or more research papers (PDFs), automatically extract the key concepts, and generate an interactive Knowledge Graph.
It uses advanced keyword extraction (TF-IDF, YAKE, KeyBERT), GPT-4o-mini for intelligent dataset extraction with PRIMARY/CITED classification, and LLM-based relation extraction (using multiple Ollama models) to build meaningful graphs for scientific documents. The system also includes a RAG-based Q&A module for querying uploaded documents.

![Main Interface](Knowledge_graph/images/main_interface.png)
*Main interface showing PDF upload, GPT-4 dataset extraction options, keyword filtering, and model/graph type selection*

---

## Features

### Core Functionality

- Upload single or multiple PDFs (drag-and-drop or browse, 200MB limit per file)
- Intelligent keyword extraction from Keywords section if present, else model-based extraction
- Configurable keyword count slider for Knowledge Graph generation (adjustable per document)
- Relation extraction between keywords using Ollama LLMs (mistral, qwen2.5, llama3, gemma3)
- Dialog-based model selection for Q&A and Knowledge Graph generation with Confirm/Cancel workflow
- Q&A System with RAG: Ask questions about uploaded documents using Retrieval-Augmented Generation

### Advanced Options

- GPT-4 Dataset Extraction Toggle:
  - Checkbox to enable/disable GPT-4o-mini dataset extraction
  - "GPT-4 Active" status badge when enabled
  - Real-time cost estimation displayed (approximately $0.015-0.025 per paper)
  - Automatic detection of OpenAI API key from environment
- Filter to Variables Only:
  - Checkbox to filter extracted keywords to climate/domain-specific variables
  - Displays filtering statistics (Original, Variables Kept, Non-Variables Removed)
  - Expandable details section showing which keywords were filtered and why
  - Improves graph quality by focusing on scientific variables
### Dataset Extraction (GPT-4o-mini)

- Automatic classification of datasets as PRIMARY (created by authors) or CITED (from other sources)
- Extraction of dataset metadata: source name, variables, time period, location, usage description, citation info
- Chunk-based processing (3000 characters with 500-character overlap) for handling long documents
- Confidence scoring for each extracted dataset
- Deduplication of dataset mentions across document chunks
- Cost tracking for API usage (input/output tokens and total cost per document)
- Real-time processing status with chunk progress indicators

### Graph Visualization

- Two Graph Visualization Modes:
  - Full Graph with Datasets: Hub-based collapsible view with interactive double-click expansion
  - Knowledge Graph Only: Keywords and relations without dataset nodes
- Enhanced Visual Elements:
  - Purple hub node for collapsible dataset expansion (size 35, distinct from keywords)
  - Green boxes for PRIMARY datasets (author-created data)
  - Blue boxes for CITED datasets (referenced from other sources)
  - Yellow circles for variables (automatically detected)
  - Default styling for regular keywords
  - Detailed tooltips with dataset metadata (type, time period, location, usage, confidence)
- Interactive Graph Statistics Panel:
  - Unique Nodes count
  - Total Relations count
  - Datasets Found count
  - Average Relations per File
- Graph physics controls (repulsion distance: 200, spring length: 300)
- Real-time graph type indicator displaying current visualization mode

### User Interface Features

- Processing Status Messages:
  - Selected model display (e.g., "Using model: llama3:latest for relation extraction")
  - Current graph type display (e.g., "Graph type: Knowledge Graph Only (without Datasets)")
  - Keyword extraction method notification
  - Success/failure indicators for each processing step
- File Management:
  - Visual file list showing uploaded PDFs with file sizes
  - Success indicator when files are uploaded
  - Individual file removal capability
- Session Persistence:
  - Separate tracking for Q&A documents and processed PDFs
  - Graph type stored with each processed file
  - Model selection persists across operations until manually changed
- Export Capabilities:
  - Download extracted relations as CSV
  - Download extracted relations as JSON
  - Export includes all metadata and relationship information

### Privacy and Performance

- 100% Local Processing for keywords and relations extraction (Privacy-Preserving)
- Optional cloud-based dataset extraction with GPT-4o-mini for enhanced accuracy
- Configurable processing pipeline (enable/disable individual features)
- No data sent to external services except when GPT-4 extraction is explicitly enabled

---

## Tech Stack

- Python 3.10+
- Streamlit (Frontend App)
- pdfplumber (PDF Text Extraction)
- NLTK, spaCy (Text Cleaning)
- TF-IDF, YAKE, KeyBERT (Keyword Extraction)
- OpenAI GPT-4o-mini (Dataset Extraction with PRIMARY/CITED Classification)
- Ollama with Multiple Model Support:
  - mistral:7b (Default for relation extraction)
  - qwen2.5:7b
  - llama3:latest
  - gemma3:12b
- Neo4j Aura (Graph Storage with Enhanced Dataset Support)
- PyVis (Interactive Graph Visualization with Hub-Based Expansion)
- SentenceTransformers (Semantic Scoring and Document Embeddings for RAG)
- python-dotenv (Environment Variable Management)

---

## GitHub Setup Instructions

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/pdf-knowledge-graph.git
cd pdf-knowledge-graph
```

### 2. Create a Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the `Knowledge_graph` directory (parent directory of Code folder) with the following credentials:

```bash
# OpenAI API Configuration (for dataset extraction)
OPENAI_API_KEY=your_openai_api_key_here

# Neo4j Aura Configuration
NEO4J_URI=neo4j+s://your-instance-id.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password_here
NEO4J_DATABASE=neo4j
```

Note: The OPENAI_API_KEY is required for GPT-4o-mini dataset extraction. If not provided, the system will skip dataset extraction.

### 5. Install and Run Ollama

Install Ollama and pull the required models:
```bash
# Pull default model
ollama pull mistral:7b

# Optional: Pull additional models for different capabilities
ollama pull qwen2.5:7b
ollama pull llama3:latest
ollama pull gemma3:12b

# Start Ollama server
ollama serve
```

### 6. Setup Neo4j Aura

1. Create a free Neo4j Aura instance at https://console.neo4j.io
2. Wait 60 seconds for the instance to become available
3. Copy the connection credentials from the Python driver section
4. Add credentials to your `.env` file

### 7. Run the Streamlit App

Navigate to the Code directory and run:
```bash
cd Knowledge_graph/Code
streamlit run frontend_light.py
```

---

## Project Folder Structure

```bash
pdf-knowledge-graph/
├── .env                        # Environment variables (OpenAI API key, Neo4j credentials)
├── Code/
│   ├── frontend_light.py       # Main Streamlit app with dialog-based model selection
│   ├── keywords_extraction.py  # Keyword and relation extraction with Ollama integration
│   ├── dataset_extraction_gpt4.py  # GPT-4o-mini dataset extractor with PRIMARY/CITED classification
│   ├── neo4j_storage.py        # Neo4j connector with hub-based graph visualization
│   ├── qa_module.py            # RAG-based Q&A system for document queries
│   ├── storing.py              # Optional CLI mode to process PDFs
│   └── requirements.txt        # Python dependencies
└── README.md                   # Project documentation
```

---

## How It Works

### 1. PDF Upload
Upload one or more PDF documents via the Streamlit interface.

### 2. Text Extraction
Extracts text using `pdfplumber` from uploaded PDFs. The system handles multi-column layouts and maintains text structure.

### 3. Model Selection
When initiating Q&A or Knowledge Graph generation, users are presented with dialog boxes to select:
- LLM model for processing (mistral:7b, qwen2.5:7b, llama3:latest, gemma3:12b)
- Graph visualization type (Full Graph with Datasets or Knowledge Graph Only)
- Confirm or Cancel actions before processing begins

### 4. Processing Options

#### Option A: Knowledge Graph Generation

**Keyword Extraction:**
- If a "Keywords" section exists in the PDF, directly extract those keywords
- Otherwise, fallback to automatic extraction using TF-IDF, YAKE, and KeyBERT
- For multiple PDFs, automatically extract roughly k/n keywords per PDF (where n = number of PDFs)

**Dataset Information Extraction (GPT-4o-mini):**
- Document split into 3000-character chunks with 500-character overlap for comprehensive coverage
- Each chunk processed independently by GPT-4o-mini API
- Automatic classification of every dataset mention as PRIMARY or CITED:
  - PRIMARY: Datasets the authors of the paper created, collected, or generated ("We deployed", "Our model ran")
  - CITED: Datasets from other sources that are referenced or used ("Forced by ERA5", "According to NASA")
- Extracted metadata for each dataset:
  - Source name and identifier
  - Measured variables and parameters
  - Time period (YYYY-YYYY format or "Not specified")
  - Geographic location
  - Usage description (how authors used the dataset)
  - Citation information (for CITED datasets)
  - Confidence score (0.0 to 1.0)
- Deduplication across chunks using fuzzy matching (70% similarity threshold)
- Cost tracking: Input/output tokens calculated, costs displayed per document and in total
- Creates specialized Dataset nodes in Neo4j with dual labels:
  - All datasets: `:Dataset` label
  - PRIMARY datasets: `:Dataset:PrimaryDataset` labels
  - CITED datasets: `:Dataset:CitedDataset` labels
- Marks dataset variables as dual-labeled nodes (`:Keyword:Variable`)
- Establishes relationships:
  - `HAS_VARIABLE`: Links datasets to their measured variables
  - `EXTRACTED_FROM`: Links datasets to extracted keywords

**Relation Extraction:**
- Keyword pairs passed to selected Ollama model to infer semantic relations
- Uses structured prompts to extract causal, correlational, and other semantic relationships
- Relations normalized to valid Neo4j relationship types (uppercase, underscores)

**Graph Construction and Storage:**
- Stores all nodes and relationships in Neo4j with complete dataset context
- Dual-label system allows efficient querying by dataset type
- Metadata stored as node properties for rich tooltips

#### Option B: Q&A System

**Document Processing:**
- Splits text into overlapping 800-word chunks for better context retrieval
- Generates vector embeddings using SentenceTransformer (all-MiniLM-L6-v2)
- Maintains document structure and source information

**RAG Implementation:**
- Stores document chunks with their embeddings in memory
- Uses cosine similarity for semantic search (threshold: 0.15)
- Retrieves top-k relevant chunks for each query
- Combines multiple sources for comprehensive answers

**Answer Generation:**
- Combines relevant chunks as context
- Uses selected Ollama model to generate contextual answers
- Includes source citations from retrieved documents
- Maintains conversation history for follow-up questions

### 5. Visualization & Interaction

**Knowledge Graph Visualization:**
Interactive PyVis network with two distinct modes based on user selection during generation.

**Q&A Interface:**
Chat-based interface with conversation history, context-aware responses, and clear source attribution.

### 6. Export Options
Users can download the extracted relations as CSV or JSON files directly from the interface.

---

## Graph Visualization Modes

The system offers two distinct graph visualization modes selected via dialog during Knowledge Graph generation:

### Full Graph (with Datasets)

**Hub-Based Collapsible Visualization:**
- Initial View: Clean graph showing only keyword nodes, relations, and a single purple "Datasets" hub node
- Hub Node Display:
  - Label: "Datasets" with icon
  - Color: Purple (distinct from all other node types)
  - Tooltip shows: Number of PRIMARY datasets, number of CITED datasets, and double-click instruction
  - Size: Larger than regular nodes (35 vs 25) for visibility
  - Connected to a central keyword node with dashed purple "CONTAINS" relationship

**Interactive Expansion:**
- Double-click the hub node to expand and view all individual datasets
- Expansion creates:
  - GREEN boxes for PRIMARY datasets (datasets created by the paper authors)
  - BLUE boxes for CITED datasets (datasets referenced from other sources)
  - Dashed connections from hub to each dataset node
  - Detailed tooltips for each dataset including:
    - Dataset type (PRIMARY or CITED)
    - Time period
    - Geographic location
    - Usage description
    - Confidence score
- Double-click hub again to collapse back to clean view
- JavaScript-powered interaction embedded in the visualization HTML

![Hub Expanded View](Knowledge_graph/images/hub_expanded_view.png)
*Interactive hub expansion showing purple hub node with CITED datasets (blue boxes) radiating outward, detailed tooltip displaying dataset metadata*

**Benefits:**
- Keeps initial graph clean and focused on keyword relationships
- Allows users to explore datasets on-demand without cluttering the visualization
- Clear visual distinction between author-created and referenced datasets
- Scales well with papers containing many dataset mentions (10-30+ datasets)

### Knowledge Graph Only (without Datasets)

**Clean Keyword-Focused Visualization:**
- Shows only keyword nodes and their semantic relationships
- No dataset hub, no dataset nodes at all
- Variable nodes still displayed in yellow for context
- Ideal for understanding conceptual relationships without data provenance
- Lighter weight visualization for papers where dataset information is less critical

**Use Cases:**
- Comparing conceptual frameworks across papers
- Understanding theoretical relationships
- Quick overview of paper topics and themes
- Teaching and presentation contexts where datasets are not the focus

---

## Model Selection

The system provides flexible model selection through dialog-based interfaces:

### Q&A Model Selection
When clicking "Send to Q&A":
1. Dialog appears with model dropdown showing:
   - mistral:7b (lightweight, fast)
   - qwen2.5:7b (balanced performance)
   - llama3:latest (high quality responses)
   - gemma3:12b (largest model, most accurate)
2. User selects preferred model
3. Confirm button initiates Q&A document processing with selected model
4. Cancel button closes dialog without processing

![Q&A Configuration Dialog](Knowledge_graph/images/qa_dialog.png)
*Q&A Configuration dialog with model selection dropdown and Confirm/Cancel buttons*

### Knowledge Graph Model Selection
When clicking "Generate Knowledge Graph":
1. Dialog appears with two selections:
   - LLM Model dropdown (same options as Q&A)
   - Graph Visualization Type dropdown:
     - "Full Graph (with Datasets)" - Hub-based collapsible view
     - "Knowledge Graph Only (without Datasets)" - Keywords and relations only
2. User configures both options
3. Confirm button initiates processing with selected configuration
4. Cancel button closes dialog without processing

![Model Selection Dialogs](Knowledge_graph/images/model_selection_dialogs.png)
*Both Q&A and Knowledge Graph configuration dialogs showing all available Ollama models (mistral:7b, qwen2.5:7b, llama3:latest, gemma3:12b)*

![Graph Type Selection](Knowledge_graph/images/graph_type_selection.png)
*Knowledge Graph Configuration with Graph Visualization Type dropdown expanded, showing "Full Graph (with Datasets)" and "Knowledge Graph Only (without Datasets)" options*

### Session Persistence
- Selected models stored in Streamlit session state
- Graph type stored with each processed PDF
- Allows different configurations for different papers in the same session
- Model selection persists until user changes it or refreshes the session

---

## Key Components

### dataset_extraction_gpt4.py - GPT-4o-mini Dataset Extractor

**GPT4DatasetExtractor Class:**
Main class for extracting ALL datasets from research papers with PRIMARY/CITED classification.

Key methods:
- `__init__()`: Initializes OpenAI client with API key from environment
- `_create_extraction_prompt()`: Creates detailed system prompt explaining PRIMARY vs CITED distinction
- `_split_into_chunks()`: Splits document into 3000-character chunks with 500-character overlap
- `_extract_from_chunk()`: Processes single chunk, returns datasets and token usage
- `_deduplicate_datasets()`: Fuzzy matching across chunks (70% similarity threshold)
- `extract_from_full_text()`: Main method that orchestrates extraction:
  - Processes all chunks in sequence
  - Accumulates raw dataset mentions
  - Deduplicates across chunks
  - Calculates total cost (input: $0.150/1M tokens, output: $0.600/1M tokens)
  - Returns DatasetMetadata objects with stats

**DatasetMetadata dataclass:**
- source: Dataset name/identifier
- variables: List of measured parameters
- time_period: Temporal coverage
- location: Geographic coverage
- context: Brief description
- chunk_indices: Which chunks mentioned this dataset
- confidence_score: Extraction confidence (0.0-1.0)
- dataset_type: "primary" or "cited"
- usage_description: How authors used the dataset
- citation_info: Reference information (for CITED datasets)

### keywords_extraction.py - Enhanced Keyword and Relation Extraction

**process() function:**
Enhanced to integrate dataset extraction:
- Accepts llm_model parameter for relation extraction
- Accepts use_gpt4_datasets flag to enable/disable GPT-4 dataset extraction
- Returns tuple: (keywords, relations, datasets, keywords_metadata)
- Extracts keywords using hybrid approach (section-based + model-based)
- Uses selected Ollama model for relation extraction
- Conditionally calls GPT4DatasetExtractor if OpenAI API key is available
- Returns comprehensive extraction statistics including GPT-4 costs

### neo4j_storage.py - Graph Storage with Hub-Based Visualization

**Neo4jConnector class:**

**store_keywords_and_relations():**
Enhanced method that handles datasets:
- Clears existing graph data
- Creates Dataset nodes with dual labels (:Dataset:PrimaryDataset or :Dataset:CitedDataset)
- Stores all dataset properties (time_period, location, dataset_type, usage_description, citation_info, confidence)
- Marks variables with :Variable label for special styling
- Creates HAS_VARIABLE relationships (dataset to variable)
- Creates EXTRACTED_FROM relationships (dataset to keyword)
- Stores keywords and semantic relationships

**generate_graph(relations, graph_type='with_datasets'):**
Core visualization method with mode support:

For 'with_datasets' mode:
- Queries all datasets from Neo4j with full metadata
- Counts PRIMARY vs CITED datasets
- Creates purple hub node with summary tooltip
- Skips individual dataset nodes in relations loop (hidden initially)
- Adds variable nodes in yellow
- Adds regular keyword nodes with default styling
- Connects hub to central keyword with dashed purple "CONTAINS" edge
- Calls `_generate_expansion_javascript()` to create interactive expansion code
- Returns (network, expansion_js) tuple

For 'without_datasets' mode:
- Skips dataset query entirely
- Skips any dataset nodes found in relations
- Shows only keywords and relations
- Returns (network, "") tuple (empty expansion_js)

**_generate_expansion_javascript(dataset_info):**
Generates JavaScript code for interactive hub expansion:
- Prepares PRIMARY and CITED dataset arrays with metadata
- Creates double-click event handler for hub node
- On first double-click (expand):
  - Creates individual nodes for each PRIMARY dataset (green, positioned above hub)
  - Creates individual nodes for each CITED dataset (blue, positioned below hub)
  - Adds dashed edges from hub to each dataset
  - Builds rich tooltips with all metadata
- On second double-click (collapse):
  - Removes all dataset nodes
  - Clears expansion state
- Returns complete JavaScript code as string for HTML injection

**get_datasets_by_type(dataset_type='all'):**
Utility method for querying datasets:
- 'primary': Returns only PRIMARY datasets (queries :PrimaryDataset label)
- 'cited': Returns only CITED datasets (queries :CitedDataset label)
- 'all': Returns all datasets (queries :Dataset label)
- Returns list of dictionaries with all dataset properties

### qa_module.py - RAG-Based Q&A System

**QASystem class:**
Implements Retrieval-Augmented Generation for document Q&A:
- `__init__()`: Initializes with default Ollama model, sentence transformer embeddings
- `set_model(model_name)`: Changes Ollama model dynamically based on user selection
- `add_document()`: Processes PDF documents:
  - Splits into 800-word chunks with overlap
  - Generates embeddings using all-MiniLM-L6-v2
  - Stores chunks with metadata (filename, chunk index)
- `find_relevant_chunks()`: Semantic search:
  - Embeds query
  - Computes cosine similarity with all chunks
  - Filters by threshold (0.15)
  - Returns top-k most relevant chunks with scores
- `generate_answer()`: Context-aware answer generation:
  - Constructs prompt with relevant context
  - Calls Ollama API with selected model
  - Streams response back
- `answer_question()`: Main Q&A interface:
  - Finds relevant chunks
  - Generates answer
  - Returns answer with source citations

### frontend_light.py - Streamlit Interface with Dialog System

**Session State Management:**
- `processed_pdfs`: Dictionary storing results for each processed PDF (nodes, relations, datasets, graph_type)
- `qa_documents`: List of documents loaded into Q&A system
- `show_qa_dialog`: Boolean flag for Q&A dialog visibility
- `show_kg_dialog`: Boolean flag for Knowledge Graph dialog visibility
- `qa_model_selected`: Stores user's Q&A model choice
- `kg_model_selected`: Stores user's KG model choice
- `kg_graph_type_selected`: Stores user's graph type choice

**Dialog-Based Workflow:**

Q&A Dialog (lines 521-559):
- Triggered by "Send to Q&A" button
- Shows model selection dropdown
- Confirm button:
  - Calls `qa_system.set_model(selected_model)`
  - Processes uploaded PDFs
  - Adds documents to Q&A system
  - Closes dialog
- Cancel button: Closes dialog without processing

Knowledge Graph Dialog (lines 570-600):
- Triggered by "Generate Knowledge Graph" button
- Shows two dropdowns:
  - Model selection for relation extraction
  - Graph type selection (with/without datasets)
- Confirm button:
  - Stores selections in session state
  - Triggers rerun to start processing
  - Closes dialog
- Cancel button: Closes dialog without processing

**Processing Logic:**
- Checks for selected model and graph type in session state
- Maps UI strings to internal parameters ('with_datasets' or 'without_datasets')
- Calls `process()` with selected model
- If GPT-4 extraction enabled, displays cost information
- Stores graph_type with processed PDF metadata
- Passes graph_type to `neo4j_storage.generate_graph()`

**Graph Rendering:**
- Retrieves graph_type from first processed PDF (all PDFs in session use same type)
- Calls `neo.generate_graph(rels, graph_type=graph_type_to_use)`
- Saves graph HTML
- Injects expansion JavaScript: `html_content.replace("</body>", expansion_js + "</body>")`
- Renders with Streamlit HTML component

---

## Example Workflow

Upload PDFs → Select Model → Extract Keywords → Extract Datasets (GPT-4o-mini) → Find Relations (Ollama) → Choose Visualization Mode → View Interactive Graph

OR

Upload PDFs → Select Model → Process for Q&A → Ask Questions → Get Contextual Answers

---

## Future Enhancements

- OCR support for scanned PDFs using Tesseract
- Interactive graph editing (merging/splitting nodes, manual relation addition)
- Fine-tune Ollama models for specific scientific domains
- Automatic summarization of graphs with key insights
- Cross-document relationship discovery in Q&A (linking information across papers)
- Export Q&A conversations and insights to PDF/Word
- Advanced dataset linking: Identify when multiple papers use the same dataset
- Temporal analysis: Track dataset usage trends over time across paper collections
- Export graph in additional formats (GraphML, GEXF, JSON-LD)
- Batch processing mode for processing large paper collections
- Custom extraction rules for domain-specific dataset formats
- Integration with dataset repositories (Zenodo, Figshare, etc.)
- Full-fledged web application with user authentication and multi-user support

---

## Example Flow

- Connect to the server (in my case UNT Server) using ssh command.
- Create venv and install required libraries and go the directory where all .py files are stored.
- Then run ollama serve to pull llama 3.2 from ollama.
- Now open another terminal and go to the same directory where code is present and run frontend_light.py
- Go to new terminal window and then run the following command to connect server to localhost using ssh tunneling.
- Open the localhost link and upload the files.

<img width="1470" height="831" alt="Screenshot 2025-08-25 at 10 12 57 PM" src="https://github.com/user-attachments/assets/6d273d21-c76d-42a4-87a0-b71604094e5d" />

- You can select any of the following options:
    - Send to Q&A
    - Generate Knowledge Graph.

 <img width="1470" height="773" alt="Screenshot 2025-08-25 at 10 16 23 PM" src="https://github.com/user-attachments/assets/9c0aa04d-1fed-4305-806d-62c7c1272df3" />

 - Querying Q&A looks like this:

<img width="1470" height="832" alt="Screenshot 2025-08-25 at 10 13 40 PM" src="https://github.com/user-attachments/assets/8e6e5b9d-20ce-4fb8-b2d8-c2ba149f1862" />

- The below are the results:

<img width="1470" height="771" alt="Screenshot 2025-08-25 at 10 15 16 PM" src="https://github.com/user-attachments/assets/92008b26-bd69-4e01-8792-08ac7ab330e9" />

<img width="1470" height="776" alt="Screenshot 2025-08-25 at 10 15 48 PM" src="https://github.com/user-attachments/assets/2439ea19-b587-459a-80f0-dc4b4f2dcc1c" />

<img width="1470" height="831" alt="Screenshot 2025-08-25 at 10 16 03 PM" src="https://github.com/user-attachments/assets/8ef7bd25-ea12-4ec7-b7d9-7a19097315b2" />

<img width="2940" height="1912" alt="image" src="https://github.com/user-attachments/assets/98bfe6b0-0e85-43f4-857d-9565b0f646dc" />

  ![image](https://github.com/user-attachments/assets/ea05dcd9-00a3-4ec5-8474-9cfa5aac2960)

- Neo4j credentials driver info:

  ![image](https://github.com/user-attachments/assets/528c40ec-cf20-49b4-924e-ae5cfb3003de)
  ![image](https://github.com/user-attachments/assets/641c7ec7-812c-4ee6-ade9-2532905c4a02)

---

## Author

**Ajith Kumar Dugyala**
Email: ajithdugyala@gmail.com
Location: Denton, Texas, USA

---

## Final Notes

This project combines local processing for privacy-sensitive operations (keyword extraction, relation extraction) with optional cloud-based enhancement (GPT-4o-mini for dataset extraction) to achieve the best balance of accuracy and privacy.

The hub-based visualization approach ensures clean, scalable graph displays even for papers with numerous dataset references. The dual-mode system (with/without datasets) provides flexibility for different use cases and audiences.

All LLM processing can run entirely locally using Ollama models, with the GPT-4 dataset extraction being optional. This makes the system suitable for sensitive research documents while still offering enhanced capabilities when cloud access is available.

---
