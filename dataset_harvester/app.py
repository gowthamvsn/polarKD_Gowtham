import streamlit as st
import tempfile
import os
import re
import sys
import requests

sys.path.insert(0, os.path.dirname(__file__))

from extractor import extract_from_pdfs
from deduplicator import deduplicate
from resolver import resolve, ResolvedDataset

st.set_page_config(page_title="Dataset Harvester", page_icon="🧊", layout="wide")
st.title("🧊 Arctic Dataset Harvester")
st.caption("Upload a research PDF → extract dataset references → check which ones are downloadable")

# --------------------------------------------------------------------------
# Downloadability checker
# --------------------------------------------------------------------------

_AUTH_REQUIRED = {
    "nsidc", "nasa_earthdata", "copernicus_cds", "copernicus_marine",
    "ecmwf", "esa", "jma", "ncar_rda",
}
_LANDING_PAGE_ONLY = {
    "uw_apl", "met_norway", "noaa", "noaa_ncei", "noaa_psl",
    "usgs", "argo", "gebco", "other",
}
_CSV_EXTS = {".csv", ".txt", ".tsv", ".tab"}


def _pangaea_id(r: ResolvedDataset):
    for s in [r.resolved_url or "", r.doi or "", r.accession or ""]:
        m = re.search(r'PANGAEA\.(\d+)', s, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _zenodo_id(r: ResolvedDataset):
    for s in [r.resolved_url or "", r.doi or ""]:
        m = re.search(r'zenodo\.org/(?:record[s]?/)?(\d+)|zenodo\.(\d+)', s, re.IGNORECASE)
        if m:
            return m.group(1) or m.group(2)
    return None


def check_downloadable(r: ResolvedDataset):
    """Returns (status, label, detail)"""
    if not r.resolved_url:
        return "none", "No URL", "Dataset not resolved"

    repo = (r.repository or "").lower()

    if repo in _AUTH_REQUIRED:
        return "auth", "🔐 Login required", f"Requires account on {repo}"

    if repo in _LANDING_PAGE_ONLY:
        return "page", "🌐 Homepage only", "No direct file — manual download"

    if repo == "pangaea" or "pangaea" in (r.resolved_url or "").lower():
        pid = _pangaea_id(r)
        if pid:
            try:
                resp = requests.head(
                    f"https://doi.pangaea.de/10.1594/PANGAEA.{pid}?format=textfile",
                    timeout=8, allow_redirects=True
                )
                if resp.status_code == 200:
                    return "yes", "✅ Downloadable", "PANGAEA tab-separated file"
                else:
                    return "collection", "📦 Collection", "Parent record — contains multiple datasets"
            except Exception:
                return "unknown", "❓ Unknown", "Could not reach PANGAEA"

    if repo == "zenodo" or "zenodo" in (r.resolved_url or "").lower():
        zid = _zenodo_id(r)
        if zid:
            try:
                resp = requests.get(f"https://zenodo.org/api/records/{zid}", timeout=8)
                if resp.status_code == 200:
                    files = resp.json().get("files", [])
                    csv_files = [
                        f for f in files
                        if os.path.splitext(f.get("key", "").lower())[1] in _CSV_EXTS
                    ]
                    if csv_files:
                        return "yes", "✅ Downloadable", f"Zenodo: {len(csv_files)} CSV/text file(s)"
                    return "no_csv", "❌ No CSV files", "Zenodo record has no CSV/text files"
            except Exception:
                return "unknown", "❓ Unknown", "Could not reach Zenodo"

    return "page", "🌐 Homepage only", "Landing page — no direct file"


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------

uploaded = st.file_uploader("Upload a research PDF", type=["pdf"])

if uploaded:
    st.divider()

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, uploaded.name)
        with open(pdf_path, "wb") as f:
            f.write(uploaded.getbuffer())

        # Step 1 — Extract
        with st.status("🔍 Step 1 — Extracting dataset references from PDF...", expanded=True) as step1:
            refs_by_source = extract_from_pdfs([pdf_path], use_llm=True)
            raw_count = sum(len(v) for v in refs_by_source.values())
            step1.update(label=f"✅ Step 1 — Found {raw_count} raw references", state="complete", expanded=False)

        # Step 2 — Deduplicate
        with st.status("🔗 Step 2 — Deduplicating...", expanded=True) as step2:
            datasets = deduplicate(refs_by_source)
            step2.update(label=f"✅ Step 2 — {raw_count} raw → {len(datasets)} unique datasets", state="complete", expanded=False)

        # Step 3 — Resolve URLs
        with st.status("🌐 Step 3 — Resolving URLs...", expanded=True) as step3:
            resolved = resolve(datasets)
            resolved_count = sum(1 for r in resolved if r.resolved_url)
            step3.update(label=f"✅ Step 3 — {resolved_count} of {len(resolved)} datasets resolved", state="complete", expanded=False)

        # Step 4 — Check downloadability
        with st.status("⬇️ Step 4 — Checking downloadability...", expanded=True) as step4:
            rows = []
            for r in resolved:
                status_key, label, detail = check_downloadable(r)
                rows.append({
                    "Dataset Name": r.canonical_name,
                    "URL": r.resolved_url or "",
                    "Repository": r.repository or "unknown",
                    "Status": label,
                    "Detail": detail,
                    "_status_key": status_key,
                })
            downloadable_count = sum(1 for row in rows if row["_status_key"] == "yes")
            step4.update(label=f"✅ Step 4 — {downloadable_count} datasets ready to download", state="complete", expanded=False)

    # Metrics
    st.subheader(f"Results — {len(rows)} datasets found in {uploaded.name}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total found", len(rows))
    c2.metric("URLs resolved", resolved_count)
    c3.metric("Ready to download", downloadable_count)
    c4.metric("Need login / manual", len(rows) - downloadable_count)

    st.divider()

    # Tabs — downloadable first, then all
    tab1, tab2 = st.tabs([f"✅ Downloadable ({downloadable_count})", f"📋 All datasets ({len(rows)})"])

    def render_table(data):
        display = [
            {
                "Dataset": row["Dataset Name"][:90] + ("…" if len(row["Dataset Name"]) > 90 else ""),
                "URL": row["URL"],
                "Repository": row["Repository"],
                "Status": row["Status"],
                "Detail": row["Detail"],
            }
            for row in data
        ]
        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "URL": st.column_config.LinkColumn("URL", display_text="🔗 Open"),
                "Status": st.column_config.TextColumn("Status", width="medium"),
                "Detail": st.column_config.TextColumn("Detail", width="large"),
            },
        )

    with tab1:
        downloadable_rows = [r for r in rows if r["_status_key"] == "yes"]
        if downloadable_rows:
            render_table(downloadable_rows)
        else:
            st.info("No directly downloadable datasets found in this paper.")

    with tab2:
        render_table(rows)
