"""
Iteration 1 — PDF Dataset Reference Extractor

Extracts dataset references from research PDFs using two passes:
  1. Regex: explicit URLs, DOIs, accession numbers
  2. LLM (GPT-4o-mini): implicit dataset mentions without a direct link

Output is a list of DatasetRef objects ready for deduplication (Iteration 2).
"""

import re
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional
import pdfplumber
import requests

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class DatasetRef:
    name: str                          # Human-readable dataset name
    url: Optional[str] = None          # Direct URL if found
    doi: Optional[str] = None          # Data DOI (not paper DOI)
    accession: Optional[str] = None    # Repository accession number
    repository_hint: Optional[str] = None  # e.g. "pangaea", "zenodo", "nsidc"
    raw_citation: str = ""             # Original text snippet that mentioned it
    source: str = ""                   # "regex" | "llm"

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Regex patterns — arctic/env research common patterns
# ---------------------------------------------------------------------------

# Standard HTTP/HTTPS URLs (not purely paper/journal URLs)
_URL_RE = re.compile(
    r'https?://[^\s\)\],\'"<>]{10,}',
    re.IGNORECASE
)

# Data DOIs — 10.XXXX/... format, skipping common journal publishers
_DOI_RE = re.compile(
    r'\b(10\.\d{4,9}/[^\s\)\],\'"<>]+)',
    re.IGNORECASE
)

# PANGAEA accession  e.g. PANGAEA.123456 or doi:10.1594/PANGAEA.123456
_PANGAEA_RE = re.compile(r'PANGAEA[.\s]*(\d{5,7})', re.IGNORECASE)

# Zenodo record  e.g. zenodo.org/record/1234567 or zenodo.1234567
_ZENODO_RE = re.compile(r'zenodo\.org/(?:record|records)/(\d+)', re.IGNORECASE)

# NSIDC accession  e.g. NSIDC-0001  or  nsidc.org/data/NSIDC-0001
_NSIDC_RE = re.compile(r'NSIDC[-\s]*(\d{4})', re.IGNORECASE)

# Arctic Data Center  https://arcticdata.io/catalog/view/doi:...
_ADC_RE = re.compile(r'arcticdata\.io[^\s\)\],\'"<>]*', re.IGNORECASE)

# Copernicus / CDS
_CDS_RE = re.compile(r'cds\.climate\.copernicus\.eu[^\s\)\],\'"<>]*', re.IGNORECASE)

# Known dataset names that appear without URLs in arctic literature
_KNOWN_DATASETS = [
    "ERA5", "ERA-Interim", "ERA-40",
    "MODIS", "VIIRS", "Landsat",
    "Sentinel-1", "Sentinel-2", "Sentinel-3", "Sentinel-5P",
    "AMSR-E", "AMSR2", "SSMIS", "SSM/I",
    "ICESat", "ICESat-2", "CryoSat-2",
    "GRACE", "GRACE-FO",
    "PIOMAS", "TOPAZ",
    "NCEP", "NCEP/NCAR", "CFSR", "CFSv2",
    "JRA-55", "MERRA-2",
    "AVHRR", "GOES",
    "NSIDC Sea Ice Index",
    "HadGHCND", "HadSST", "HadCRUT",
    "GISTEMP", "Berkeley Earth",
    "ETOPO", "GEBCO",
    "WOA", "World Ocean Atlas",
    "ARGO", "Argo",
    "MOSAiC",
    "SHEBA",
    "IABP",
    "AWI", "IMB",
]

_KNOWN_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(d) for d in _KNOWN_DATASETS) + r')\b'
)

# DOIs that belong to journal publishers — skip these (not datasets)
_JOURNAL_DOI_PREFIXES = {
    "10.1016", "10.1038", "10.1126", "10.1175", "10.1029",
    "10.1007", "10.3390", "10.1002", "10.1080", "10.1017",
    "10.5194", "10.1073", "10.3189", "10.1098", "10.1007",
    "10.1177", "10.1093", "10.1111", "10.2307", "10.1146",
    "10.1214", "10.1137", "10.1257", "10.1353", "10.2307",
    "10.1515", "10.1515", "10.1017", "10.1017",
}

# URLs from sites that are never data repositories
_JOURNAL_URL_DOMAINS = {
    "journals.ametsoc.org", "pnas.org", "nature.com", "science.org",
    "sciencedirect.com", "springer.com", "wiley.com", "tandfonline.com",
    "cambridge.org", "agu.org", "essoar.org", "arxiv.org",
    "researchgate.net", "semanticscholar.org", "carbonbrief.org",
    "newengineer.com", "gsas.harvard.edu", "un.org", "usembassy.gov",
    "wwf.org", "wwf.org.uk", "environment.nsw.gov.au",
    "greatwhitecon.info",
}


def _is_data_doi(doi: str) -> bool:
    prefix = doi.split("/")[0].lower()
    return prefix not in _JOURNAL_DOI_PREFIXES


def _is_journal_url(url: str) -> bool:
    try:
        # Extract domain from URL
        domain = url.split("//", 1)[1].split("/")[0].lower()
        domain = domain.lstrip("www.")
        return domain in _JOURNAL_URL_DOMAINS
    except Exception:
        return False


def _is_truncated(s: str) -> bool:
    """True if a URL/DOI was cut off mid-word by a line break."""
    return s.endswith(("-", "/", ".", "_", "="))


def _repo_hint_from_url(url: str) -> Optional[str]:
    url_lower = url.lower()
    if "pangaea" in url_lower:
        return "pangaea"
    if "zenodo" in url_lower:
        return "zenodo"
    if "nsidc" in url_lower:
        return "nsidc"
    if "arcticdata.io" in url_lower:
        return "arctic_data_center"
    if "copernicus" in url_lower or "cds.climate" in url_lower:
        return "copernicus_cds"
    if "earthdata.nasa.gov" in url_lower or "nsidc.org" in url_lower:
        return "nasa_earthdata"
    if "noaa.gov" in url_lower:
        return "noaa"
    if "ncei.noaa" in url_lower:
        return "noaa_ncei"
    return None


# ---------------------------------------------------------------------------
# Pass 1: Regex extraction
# ---------------------------------------------------------------------------

def extract_regex(text: str) -> list[DatasetRef]:
    refs: list[DatasetRef] = []
    seen_identifiers: set[str] = set()

    def _add(ref: DatasetRef, key: str):
        if key not in seen_identifiers:
            seen_identifiers.add(key)
            refs.append(ref)

    # URLs — only data repository URLs
    for m in _URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;:")
        if _is_truncated(url):
            continue
        if _is_journal_url(url):
            continue
        hint = _repo_hint_from_url(url)
        # Only keep URLs that point to a known data repository
        if hint is None:
            continue
        ctx = text[max(0, m.start()-80):m.end()+80].replace("\n", " ")
        _add(DatasetRef(name=url, url=url, repository_hint=hint,
                        raw_citation=ctx, source="regex"), url)

    # DOIs — only data DOIs, strip doi.org prefix first
    for m in _DOI_RE.finditer(text):
        raw_doi = m.group(1).rstrip(".,;:")
        # Normalise: strip https://doi.org/ prefix if captured inside the DOI group
        doi = re.sub(r'^https?://doi\.org/', '', raw_doi, flags=re.IGNORECASE)
        if _is_truncated(doi):
            continue
        if not _is_data_doi(doi):
            continue
        ctx = text[max(0, m.start()-80):m.end()+80].replace("\n", " ")
        hint = None
        if "1594/PANGAEA" in doi.upper():
            hint = "pangaea"
        elif "5281/zenodo" in doi.lower():
            hint = "zenodo"
        _add(DatasetRef(name=doi, doi=doi, repository_hint=hint,
                        raw_citation=ctx, source="regex"), doi.lower())

    # PANGAEA accessions
    for m in _PANGAEA_RE.finditer(text):
        acc = f"PANGAEA.{m.group(1)}"
        ctx = text[max(0, m.start()-80):m.end()+80].replace("\n", " ")
        _add(DatasetRef(name=acc, accession=acc, repository_hint="pangaea",
                        raw_citation=ctx, source="regex"), acc)

    # Zenodo records
    for m in _ZENODO_RE.finditer(text):
        acc = f"zenodo.{m.group(1)}"
        ctx = text[max(0, m.start()-80):m.end()+80].replace("\n", " ")
        _add(DatasetRef(name=acc, accession=acc,
                        url=f"https://zenodo.org/record/{m.group(1)}",
                        repository_hint="zenodo",
                        raw_citation=ctx, source="regex"), acc)

    # NSIDC accessions
    for m in _NSIDC_RE.finditer(text):
        acc = f"NSIDC-{m.group(1).zfill(4)}"
        ctx = text[max(0, m.start()-80):m.end()+80].replace("\n", " ")
        _add(DatasetRef(name=acc, accession=acc, repository_hint="nsidc",
                        raw_citation=ctx, source="regex"), acc)

    # Known named datasets
    for m in _KNOWN_PATTERN.finditer(text):
        name = m.group(0)
        ctx = text[max(0, m.start()-100):m.end()+100].replace("\n", " ")
        _add(DatasetRef(name=name, repository_hint=_hint_for_known(name),
                        raw_citation=ctx, source="regex"), name.lower())

    return refs


def _hint_for_known(name: str) -> Optional[str]:
    n = name.upper()
    if n.startswith("ERA"):
        return "copernicus_cds"
    if n in {"MODIS", "VIIRS", "LANDSAT", "ICESAT", "ICESAT-2", "GRACE", "GRACE-FO", "MERRA-2"}:
        return "nasa_earthdata"
    if n in {"AMSR-E", "AMSR2", "SSMIS", "SSM/I", "NSIDC SEA ICE INDEX", "IABP"}:
        return "nsidc"
    if n in {"NCEP", "NCEP/NCAR", "CFSR", "CFSV2", "NOAA"}:
        return "noaa"
    return None


# ---------------------------------------------------------------------------
# Pass 2: LLM extraction — tries Ollama first, falls back to OpenAI
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a scientific data archivist specialising in arctic and environmental research.

Your task: given a chunk of text from a research paper, extract EVERY dataset that is mentioned —
including datasets that have no explicit URL or DOI but are referred to by name or description.

For EACH dataset return a JSON object with these fields (omit fields you cannot determine):
  - name        : string  — canonical dataset name
  - url         : string  — direct download or landing page URL, if present
  - doi         : string  — data DOI (10.XXXX/...), if present
  - accession   : string  — repository accession number, if present
  - repository_hint : string — one of: pangaea, zenodo, nsidc, copernicus_cds, nasa_earthdata,
                               noaa, arctic_data_center, dryad, figshare, other
  - raw_citation : string — the sentence(s) in the text that mention this dataset (verbatim, max 200 chars)

Rules:
- Include reanalysis products (ERA5, MERRA-2, JRA-55, NCEP), remote sensing products (MODIS, VIIRS,
  Sentinel, Landsat, ICESat-2, CryoSat-2, AMSR2), in-situ datasets, model outputs, and campaign data.
- Do NOT include journal papers, books, or software packages — only datasets.
- Do NOT duplicate: if the same dataset is mentioned twice, return it once.
- Return ONLY a JSON array. No prose, no markdown fences.
- If there are no datasets, return [].
"""

_CHUNK_SIZE = 3000
_OVERLAP = 400
_OLLAMA_URL = "http://localhost:11434/api/chat"
_OLLAMA_MODELS = ["mistral:latest", "mistral:7b", "llama3:latest", "qwen2.5:7b", "gemma3:12b"]


def _chunk_text(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + _CHUNK_SIZE, len(text))
        chunks.append(text[start:end])
        start += _CHUNK_SIZE - _OVERLAP
    return chunks


def _detect_ollama_model() -> Optional[str]:
    """Return the first available Ollama model, or None if Ollama is not running."""
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=3)
        if resp.status_code != 200:
            return None
        available = {m["name"] for m in resp.json().get("models", [])}
        for m in _OLLAMA_MODELS:
            if m in available:
                return m
        # If any model is present use the first one
        if available:
            return next(iter(available))
    except Exception:
        pass
    return None


def _call_ollama(model: str, chunk: str) -> list[dict]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": chunk},
        ],
        "stream": False,
        "options": {"temperature": 0},
    }
    resp = requests.post(_OLLAMA_URL, json=payload, timeout=120)
    resp.raise_for_status()
    content = resp.json()["message"]["content"].strip()
    # Strip possible markdown code fences
    content = re.sub(r'^```(?:json)?\s*', '', content)
    content = re.sub(r'\s*```$', '', content)
    return json.loads(content)


def _call_azure_openai(chunk: str) -> list[dict]:
    from openai import AzureOpenAI
    client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
    )
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini")
    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": chunk},
        ],
        temperature=0,
        max_tokens=2048,
    )
    content = response.choices[0].message.content.strip()
    content = re.sub(r'^```(?:json)?\s*', '', content)
    content = re.sub(r'\s*```$', '', content)
    return json.loads(content)


def _call_openai(chunk: str, api_key: str) -> list[dict]:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": chunk},
        ],
        temperature=0,
        max_tokens=2048,
    )
    content = response.choices[0].message.content.strip()
    content = re.sub(r'^```(?:json)?\s*', '', content)
    content = re.sub(r'\s*```$', '', content)
    return json.loads(content)


def extract_llm(text: str, api_key: Optional[str] = None) -> list[DatasetRef]:
    # Priority: Azure OpenAI → regular OpenAI → Ollama (local fallback)
    azure_ready = bool(os.getenv("AZURE_OPENAI_KEY") and os.getenv("AZURE_OPENAI_ENDPOINT"))
    openai_key = api_key or os.getenv("OPENAI_API_KEY")

    if azure_ready:
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini")
        print(f"[extractor] LLM backend: Azure OpenAI ({deployment})")
        call_fn = _call_azure_openai
    elif openai_key:
        print("[extractor] LLM backend: OpenAI gpt-4o-mini")
        call_fn = lambda chunk: _call_openai(chunk, openai_key)
    else:
        ollama_model = _detect_ollama_model()
        if ollama_model:
            print(f"[extractor] LLM backend: Ollama ({ollama_model}) [fallback]")
            call_fn = lambda chunk: _call_ollama(ollama_model, chunk)
        else:
            print("[extractor] No LLM backend available — skipping LLM pass")
            return []

    refs: list[DatasetRef] = []
    seen_names: set[str] = set()

    for i, chunk in enumerate(_chunk_text(text)):
        try:
            items = call_fn(chunk)
            for item in items:
                name = item.get("name", "").strip()
                if not name:
                    continue
                key_str = name.lower()
                if key_str in seen_names:
                    continue
                seen_names.add(key_str)
                refs.append(DatasetRef(
                    name=name,
                    url=item.get("url"),
                    doi=item.get("doi"),
                    accession=item.get("accession"),
                    repository_hint=item.get("repository_hint"),
                    raw_citation=item.get("raw_citation", "")[:300],
                    source="llm",
                ))
        except json.JSONDecodeError:
            print(f"[extractor] LLM chunk {i}: JSON parse error — skipping")
        except Exception as e:
            print(f"[extractor] LLM chunk {i}: {e}")

    return refs


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def extract_from_pdf(pdf_path: str, use_llm: bool = True,
                     api_key: Optional[str] = None) -> list[DatasetRef]:
    """
    Extract all dataset references from a PDF file.
    Returns raw (pre-dedup) list of DatasetRef objects.
    """
    text = _read_pdf(pdf_path)
    if not text:
        print(f"[extractor] Could not read text from {pdf_path}")
        return []

    print(f"[extractor] Extracted {len(text):,} characters from PDF")

    regex_refs = extract_regex(text)
    print(f"[extractor] Regex pass: {len(regex_refs)} references found")

    llm_refs = []
    if use_llm:
        llm_refs = extract_llm(text, api_key=api_key)
        print(f"[extractor] LLM pass:   {len(llm_refs)} references found")

    return regex_refs + llm_refs


def extract_from_pdfs(pdf_paths: list[str], use_llm: bool = True,
                      api_key: Optional[str] = None) -> dict[str, list[DatasetRef]]:
    """Extract from multiple PDFs. Returns {filename: [DatasetRef]}."""
    results = {}
    for path in pdf_paths:
        fname = os.path.basename(path)
        print(f"\n[extractor] Processing: {fname}")
        results[fname] = extract_from_pdf(path, use_llm=use_llm, api_key=api_key)
    return results


def _read_pdf(path: str) -> str:
    try:
        with pdfplumber.open(path) as pdf:
            pages = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages.append(t)
            return "\n".join(pages)
    except Exception as e:
        print(f"[extractor] PDF read error: {e}")
        return ""
