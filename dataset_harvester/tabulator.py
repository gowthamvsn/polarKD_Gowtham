"""
Panoply/NASA-style variable tabulation from paper PDFs.
Extracts: location, time range, and measured variables with units.
"""

from __future__ import annotations
import re
import json
import os
import time
from pathlib import Path

import pdfplumber


# ── Column-aware PDF extraction (mirrors extractor.py iter 9.5) ──────────────

def _words_to_text(words: list) -> str:
    if not words:
        return ""
    sorted_w = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines, cur_top, cur_line = [], None, []
    for w in sorted_w:
        if cur_top is None or (w["top"] - cur_top) > 5:
            if cur_line:
                lines.append(" ".join(x["text"] for x in cur_line))
            cur_line = [w]
            cur_top = w["top"]
        else:
            cur_line.append(w)
    if cur_line:
        lines.append(" ".join(x["text"] for x in cur_line))
    return "\n".join(lines)


def _extract_page_text(page) -> str:
    words = page.extract_words(x_tolerance=3, y_tolerance=3, keep_blank_chars=False)
    if not words:
        return page.extract_text() or ""
    mid = page.width / 2
    left = [w for w in words if w["x1"] < mid - 10]
    right = [w for w in words if w["x0"] > mid + 10]
    span = [w for w in words if not (w["x1"] < mid - 10 or w["x0"] > mid + 10)]
    two_col = (len(left) >= 5 and len(right) >= 5
               and (len(left) + len(right)) >= len(words) * 0.6)
    if two_col:
        parts = [_words_to_text(span), _words_to_text(left), _words_to_text(right)]
        return "\n".join(p for p in parts if p)
    return _words_to_text(words)


def _read_pdf(path) -> str:
    try:
        with pdfplumber.open(str(path)) as pdf:
            pages = [_extract_page_text(p) for p in pdf.pages]
            return "\n".join(p for p in pages if p)
    except Exception:
        return ""


# ── Physical unit whitelist ───────────────────────────────────────────────────
# Only patterns that represent real measured quantities pass through.

_UNIT_PATTERNS = [
    # Temperature (no standalone K — too many false positives with 'k' as count/constant)
    r"°[CF]",
    # Salinity / conductivity
    r"PSU", r"psu", r"PSS", r"g\s*/\s*kg",
    r"µS\s*/\s*cm", r"mS\s*/\s*cm",
    # Molar concentration (allow optional / separator: µmol/L or µmol L)
    r"µmol\s*/?\s*(?:L|kg|m[²2³3])?(?:\s*[⁻\-]1)?",
    r"mmol\s*/?\s*(?:L|kg|m[²2³3])?(?:\s*[⁻\-]1)?",
    r"nmol\s*/?\s*(?:L|kg|m[²2³3])?(?:\s*[⁻\-]1)?",
    r"pmol\s*/?\s*(?:L|kg)?(?:\s*[⁻\-]1)?",
    # Mass concentration
    r"mg\s*/?\s*(?:L|kg|g|m[23²³])?(?:\s*[⁻\-]1)?",
    r"µg\s*/?\s*(?:L|kg|m[23²³])?(?:\s*[⁻\-]1)?",
    r"ng\s*/?\s*(?:L|kg)?(?:\s*[⁻\-]1)?",
    # Dimensionless ratios
    r"ppm", r"ppb",
    r"%", r"‰",
    # Carbon mass
    r"PgC", r"TgC", r"GtC", r"Pg\s*C", r"Tg\s*C", r"Gt\s*C",
    r"mol\s*C\s*/?\s*m[23²³]",
    # Mass / volume (ice, water budget)
    r"Gt", r"Pg", r"Tg",
    r"km[³3]", r"km[²2]",
    # Pressure
    r"hPa", r"kPa", r"dbar", r"bar", r"mbar", r"µatm", r"matm", r"atm",
    # Length / depth / sea level
    r"km", r"m", r"cm", r"mm",
    r"mm\s*(?:SLE|w\.?e\.?)",   # sea level equivalent, water equivalent
    r"m\s*(?:SLE|w\.?e\.?)",
    r"cm\s*(?:SLE|w\.?e\.?)",
    # Velocity / rate — require explicit / separator or ⁻¹ notation
    r"m\s*/\s*s(?:\s*[⁻\-]1)?", r"m\s+s\s*[⁻\-]1",
    r"cm\s*/\s*s(?:\s*[⁻\-]1)?", r"cm\s+s\s*[⁻\-]1",
    r"m\s*/\s*yr(?:\s*[⁻\-]1)?", r"m\s+yr\s*[⁻\-]1",
    r"cm\s*/\s*yr(?:\s*[⁻\-]1)?", r"cm\s+yr\s*[⁻\-]1",
    r"mm\s*/\s*yr(?:\s*[⁻\-]1)?", r"mm\s+yr\s*[⁻\-]1",
    # Energy / heat flux
    r"W\s*/\s*m[2²]", r"MJ\s*/\s*m[2²]",
    r"ZJ",
    # Ocean transport (uppercase only — avoid PW/TW ambiguity with acronyms)
    r"Sv",
    # Flux rates
    r"mol\s*/?\s*m[2²]\s*/?\s*(?:yr|d|s)(?:\s*[⁻\-]1)?",
    r"µmol\s*/?\s*m[2²]\s*/?\s*(?:yr|d|s)(?:\s*[⁻\-]1)?",
    r"mmol\s*/?\s*m[2²]\s*/?\s*(?:yr|d|s)(?:\s*[⁻\-]1)?",
    r"g\s*/?\s*m[2²]\s*/?\s*(?:yr|d)?",
    r"µg\s*/?\s*m[2²]\s*/?\s*(?:yr|d)?",
    r"mg\s*/?\s*m[2²]\s*/?\s*(?:yr|d)?",
    r"kg\s*/?\s*m[2²]\s*/?\s*(?:yr|d)?",
    # Time rates
    r"yr[⁻\-]?1", r"/\s*yr", r"d[⁻\-]?1", r"/\s*d",
    # Water quality
    r"NTU", r"FTU",
    # Radioactivity
    r"Bq\s*/?\s*(?:m[23³]|kg|L)",
    # Isotope notation
    r"‰\s*VSMOW", r"‰\s*VPDB",
]

_UNIT_RE = re.compile(
    r"^(?:" + "|".join(f"(?:{p})" for p in _UNIT_PATTERNS) + r")$",
    re.UNICODE,  # NO IGNORECASE — scientific units are case-sensitive (Tg ≠ TG)
)


def _valid_unit(s: str) -> bool:
    return bool(_UNIT_RE.match(s.strip()))


# ── Patterns ──────────────────────────────────────────────────────────────────

# "Variable Name (unit)" or "acronym [unit]"
# - names: lowercase allowed, min 3 chars, [ -] only (no newlines in name)
# - unit content: max 30 chars, no newlines
_VAR_RE = re.compile(
    r"([A-Za-z][A-Za-z₀-₉₂₃₄]{2,}(?:[ \-][A-Za-z₀-₉₂₃₄]+){0,5})"
    r"\s*[\(\[]"
    r"([^\)\]\n]{1,30})"
    r"[\)\]]",
    re.MULTILINE,
)

# Words that are never variable names
_STOP_NAMES = frozenset({
    # Articles / prepositions / common quantifiers / adverbs
    "the", "and", "for", "but", "not", "are", "was", "were", "has", "had",
    "see", "note", "all", "each", "both", "from", "than", "with",
    "this", "that", "they", "their", "which", "when", "where", "here",
    "enough", "about", "within", "between", "around", "roughly", "approximately",
    "almost", "over", "under", "above", "below", "more", "less", "much",
    "just", "only", "even", "still", "yet", "already", "often", "sometimes",
    "many", "most", "some", "any", "few", "other", "another", "same",
    # Verb forms that describe a measurement action, not a variable
    "thus", "also", "shown", "used", "using", "based", "given", "defined",
    "expressed", "denoted", "calculated", "measured", "estimated", "derived",
    "plotted", "listed", "described", "indicated", "referred", "compared",
    "obtained", "computed", "observed", "modelled", "modeled", "simulated",
    # Adjectives describing size/magnitude (never variable names alone)
    "thin", "thick", "short", "long", "narrow", "wide", "shallow", "deep",
    "small", "large", "high", "low", "fast", "slow", "dense", "sparse",
    "upper", "lower", "inner", "outer", "central", "lateral",
    # Figure / table formatting words
    "fig", "figure", "table", "panel", "code", "label", "axis", "bars",
    "box", "cross", "cover", "line", "circle", "colour", "color",
    # Generic nouns / adjectives that appear near units but aren't variables
    "loss", "gain", "change", "error", "response", "carrier", "river",
    "maximum", "minimum", "million", "inches", "massive", "fissile",
    "suggests", "extension", "identifier",
    # Too generic measurement-adjacent words
    "content", "contents", "tests", "threshold", "species", "interval",
    "value", "values", "range", "ranges", "region", "regions",
    "explanatory", "freshened", "depths", "standard", "bottom", "top",
    # Statistical / methodological terms
    "variation", "variance", "percentage", "fraction", "proportion",
    "difference", "differences", "anomaly", "anomalies", "average",
    "typical", "relative", "decline", "reduction", "increase",
    # Adjective compounds / descriptive phrases masquerading as variables
    "low-salinity", "number", "samples", "clasts", "assemblage",
    "surface", "waters", "explanatory",
    # Geographic / topographic nouns (location descriptors, not measurement variables)
    "glacier", "basin", "fjord", "coast", "shelf", "peninsula", "island",
    "ice", "sheet", "outlet", "tributary", "channel", "bay",
    "summit", "mount", "mountain", "ridge", "peak", "nunatak", "range",
    "slope", "plateau", "valley", "divide",
    # Adjectives that start descriptive phrases
    "although", "despite", "relative", "freshening", "warming",
    "tropical", "compiled", "typical",
})

_COORD_BBOX_RE = re.compile(
    r"(\d{1,3}(?:\.\d+)?)\s*°\s*([NS])"
    r"[,\s–\-to]+"
    r"(\d{1,3}(?:\.\d+)?)\s*°\s*([NS])"
    r"[,\s;and–\-]*"
    r"(\d{1,3}(?:\.\d+)?)\s*°\s*([EW])"
    r"[,\s–\-to]+"
    r"(\d{1,3}(?:\.\d+)?)\s*°\s*([EW])",
    re.IGNORECASE,
)

_YEAR_RANGE_RE = re.compile(
    r"\b(1[89]\d{2}|20[0-3]\d)\s*[–\-to]+\s*(1[89]\d{2}|20[0-3]\d)\b"
)

_SINGLE_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20[0-3]\d)\b")

_SECTION_RE = re.compile(
    r"^\s*(?:\d+\.?\s*)?"
    r"(abstract|introduction|study\s+(?:area|site|region)|"
    r"data(?:\s+and\s+methods?)?|methods?(?:\s+and\s+materials?)?|"
    r"materials?\s+and\s+methods?|measurements?|observations?|"
    r"datasets?|variables?|parameters?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

_REF_RE = re.compile(
    r"^\s*(?:References?|Bibliography|Works\s+Cited)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _target_sections(text: str) -> tuple[str, bool]:
    """Returns (section_text, used_fallback).
    used_fallback is True when no data/methods section headers were found
    and we fell back to text[:10000] (abstract/intro region).
    """
    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        return text[:10000], True
    target_words = {"study", "data", "method", "material", "measurement",
                    "observation", "variable", "parameter", "abstract"}
    spans = []
    for i, m in enumerate(matches):
        if any(t in m.group(1).lower() for t in target_words):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else min(start + 8000, len(text))
            spans.append(text[start:end])
    if spans:
        return "\n".join(spans)[:10000], False
    return text[:10000], True


def _trim_refs(text: str) -> str:
    m = _REF_RE.search(text)
    return text[:m.start()] if m else text


# ── Polar keyword location search (faster + more reliable than NER alone) ────
# IMPORTANT: longer/more-specific patterns MUST appear before shorter ones within
# each group so re.finditer always matches the longest form (e.g. "Greenland Sea"
# before bare "Greenland", "Antarctica" before "Antarctic").
_POLAR_PLACE_RE = re.compile(
    r"\b("
    # Compound ice sheets / shelves first (before bare continent names)
    r"Greenland\s+Ice\s+Sheet|Antarctic\s+Ice\s+Sheet|"
    r"West\s+Antarctica|East\s+Antarctica|"
    r"Antarctic\s+Peninsula|"
    r"Thwaites\s+Glacier|Pine\s+Island\s+Glacier|"
    r"Lambert\s+Glacier|Totten\s+Glacier|"
    r"Filchner.Ronne|Filchner\s+Ice\s+Shelf|Ronne\s+Ice\s+Shelf|"
    r"Shackleton\s+Range|Transantarctic\s+Mountains|"
    r"Ellsworth\s+Mountains|Heritage\s+Range|"
    # Antarctic ocean sectors (before bare "Antarctica")
    r"Weddell\s+Sea|Ross\s+Sea|Amundsen\s+Sea|Bellingshausen\s+Sea|"
    r"Prydz\s+Bay|Queen\s+Maud\s+Land|Marie\s+Byrd\s+Land|Victoria\s+Land|"
    # Continent names (after compounds)
    r"Antarctica|"          # noun form — matches "Antarctica" but not "Antarctic"
    r"Antarctic(?!a)|"      # adjective form — only if "Antarctica" didn't match
    # Arctic Ocean subdivisions (before bare "Arctic")
    r"Greenland\s+Sea|Barents\s+Sea|Kara\s+Sea|Laptev\s+Sea|"
    r"East\s+Siberian\s+Sea|Chukchi\s+Sea|Beaufort\s+Sea|Lincoln\s+Sea|"
    r"Norwegian\s+Sea|Bering\s+Sea|Hudson\s+Bay|Baffin\s+Bay|"
    r"Davis\s+Strait|Fram\s+Strait|Denmark\s+Strait|"
    r"Canadian\s+Arctic|Northwest\s+Passage|Canada|"
    r"Russia|"
    # Arctic continent/region (after ocean subdivisions)
    r"Arctic|"
    # Greenland specifics (after "Greenland Sea" and "Greenland Ice Sheet")
    r"Greenland|"
    # Svalbard / Norway
    r"Svalbard|Spitsbergen|Hornsund|Isfjorden|Kongsfjorden|"
    r"Ny-?[ÅA]lesund|Longyearbyen|Nordaustlandet|Edgeøya|"
    # Canada / Alaska
    r"Alaska|Baffin\s+Island|Ellesmere\s+Island|Banks\s+Island|"
    r"Victoria\s+Island|"
    # Siberia / Russia
    r"Siberia|Novaya\s+Zemlya|Franz\s+Josef\s+Land|Severnaya\s+Zemlya|"
    # Greenland coasts / fjords
    r"Ilulissat|Jakobshavn|Kangerdlugssuaq|Helheim|Sermeq|"
    r"Disko\s+(?:Bay|Island)|"
    # Antarctic stations
    r"McMurdo|Concordia|Halley|Dome\s+(?:C|Fuji|A)|"
    # Sub-polar / mountain glaciers
    r"Himalayas|Hindu\s+Kush|Karakoram|Tibetan\s+Plateau|Patagonia|"
    r"Andes|Alps|Caucasus"
    r")\b",
    re.IGNORECASE,
)


def _places_keywords(text: str) -> list[str]:
    """Fast keyword-based polar location extraction — more reliable than NER for place names."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _POLAR_PLACE_RE.finditer(_trim_refs(text)[:80000]):
        val = m.group(1).strip()
        key = re.sub(r"\s+", " ", val).strip()
        # Normalise "Antarctic" → "Antarctica" when both might appear
        canonical = {"Antarctic": "Antarctica"}.get(key, key)
        if canonical.lower() not in seen:
            seen.add(canonical.lower())
            out.append(canonical)
        if len(out) >= 8:
            break
    return out


# ── LLM variable extraction (pass 3 fallback) ────────────────────────────────

_VARS_SYSTEM_PROMPT = """\
You are a scientific data extraction assistant for polar/cryosphere research papers.
Extract every physical or environmental variable that is measured, modelled, or reported.

Return a JSON array ONLY — no prose before or after.
Each object: {"name": "<plain English quantity name>", "unit": "<unit symbol as in paper>"}

INCLUDE: temperature, ice thickness, wave height, salinity, concentration, velocity, flux, \
extent, volume, pressure, snow depth, melt rate, discharge, albedo, reflectance, transmittance, \
radiation, irradiance, wind speed, sea level, mass balance — anything quantified.
Include BOTH directly measured quantities AND derived quantities (e.g. albedo derived from \
upwelling/downwelling irradiance is a valid variable; include both "surface albedo" AND "irradiance").
For dimensionless quantities (albedo, reflectance, fraction, index), use "-" as the unit.
EXCLUDE: model names (WRF, ROMS, CESM, CFSv2), instrument names (pyranometer, radiometer), \
station names, author names, equation numbers, figure panel labels, dataset names (CMIP6, ERA5).
Use acronyms as the name when they are well-known (e.g. FSD, SIC, Hs, SST, SLP, SZA).
If no clear physical variables are found, return [].
Output: JSON array only.\
"""


def _vars_llm(text: str) -> list[dict]:
    """LLM pass: extract variables from prose text. Returns [{name, unit}]."""
    # Load .env if keys not already in environment
    if not os.getenv("AZURE_OPENAI_KEY"):
        try:
            from dotenv import load_dotenv
            from pathlib import Path as _P
            _env = _P(__file__).parent.parent / "Knowledge_graph" / ".env"
            load_dotenv(_env)
        except Exception:
            pass

    text_trimmed = _trim_refs(text)[:6000]
    if len(text_trimmed) < 150:
        return []
    try:
        from openai import AzureOpenAI
        client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview"),
        )
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini")
        resp = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": _VARS_SYSTEM_PROMPT},
                {"role": "user",   "content": text_trimmed},
            ],
            temperature=0,
            max_tokens=800,
        )
        raw = resp.choices[0].message.content or ""
    except Exception as e:
        print(f"[tabulator]   LLM error : {e}")
        return []

    # Parse — tolerate markdown fences and extra prose
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r'\[.*?\]', raw, re.DOTALL)
        if not m:
            return []
        try:
            items = json.loads(m.group(0))
        except Exception:
            return []

    # Standalone coordinate/methodological terms that aren't environmental variables
    _LLM_META_NAMES = frozenset({
        "latitude", "longitude", "elevation", "altitude",
        "sample volume", "sample size", "sample weight",
        "spatial resolution", "temporal resolution", "pixel size",
        # Aircraft/platform navigation variables — not environmental measurements
        "flight altitude", "aircraft altitude", "aircraft pitch angle", "aircraft roll angle",
        "pitch angle", "roll angle", "heading",
        # Solar geometry — inputs, not outputs
        "solar zenith angle", "solar azimuth angle", "zenith angle",
        # Universal physical constants — never a study variable
        "gravitational acceleration", "gravity", "gas constant",
    })

    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        unit = (item.get("unit") or "").strip()
        # Allow "-" / "dimensionless" as valid units for albedo, reflectance, fraction, etc.
        if not unit:
            unit = "-"
        if not name or len(name) < 2 or len(name) > 65 or len(unit) > 30:
            continue
        name_lower = name.lower()
        first_word = name_lower.split()[0]
        if first_word in _STOP_NAMES or name_lower in _STOP_NAMES:
            continue
        if name_lower in _LLM_META_NAMES:
            continue
        out.append({"name": name, "unit": unit})
    return out


# ── spaCy NER (optional) ──────────────────────────────────────────────────────

_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
        except Exception:
            _nlp = False
    return _nlp if _nlp else None


def _places_ner(text: str) -> list[str]:
    nlp = _get_nlp()
    if not nlp:
        return []
    doc = nlp(_trim_refs(text)[:50000])
    seen: set[str] = set()
    out: list[str] = []
    for ent in doc.ents:
        if ent.label_ not in ("GPE", "LOC"):
            continue
        val = ent.text.strip()
        _NER_STOP = frozenset({
            "Sect", "Figs", "Fig", "Tab", "Eq", "Ref", "Refs", "App",  # section/figure refs
            "Polygon", "Polygons", "Station", "Delta", "Source",        # geometry / generic nouns
            "Carbon", "Nitrogen", "Oxygen", "Hydrogen",                 # element names (not places)
        })
        first_tok = val.split()[0]
        if (len(val) >= 4
                and val[0].isupper()                          # must start uppercase
                and not (val.isupper() and " " not in val and len(val) <= 6)  # short acronym: HCSL, NSF
                and first_tok not in _NER_STOP               # section/figure abbreviations
                and not re.search(r"\d", val)
                and not re.search(r"^[A-Z]\.", val)
                and not re.search(r"[A-Z]\.[,\s]", val)
                and not re.search(r"\bet\s+al", val, re.IGNORECASE)  # citation "et al."
                and not (len(val) > 20 and " " not in val)   # all-concatenated
                and not (len(first_tok) > 15)                 # concatenated first word
                and "(" not in val                            # citation artifact
                and "\n" not in val
                and val not in seen
                and not (                                     # author name: "et [al.] + year"
                    re.search(r"\bet\s*(?:al\.?)?", doc.text[ent.end_char:ent.end_char + 40])
                    and re.search(r"(?:19|20)\d{2}", doc.text[ent.end_char:ent.end_char + 40])
                )
                and not re.search(                            # single-author (YYYY) pattern
                    r"\(\s*(?:19|20)\d{2}",
                    doc.text[ent.end_char:ent.end_char + 25]
                )):
            seen.add(val)
            out.append(val)
    return out[:10]


# ── Core extraction ───────────────────────────────────────────────────────────

def tabulate_paper(pdf_path: str | Path, compare_llm: bool = False) -> dict:
    """
    Return a Panoply-style dict for one PDF:
    {paper, location, coords, time_start, time_end, variables: [{name, acronym, unit}]}
    """
    pdf_path = Path(pdf_path)
    print(f"\n[tabulator] {'─' * 60}")
    print(f"[tabulator] {pdf_path.name}")

    result: dict = {
        "paper": pdf_path.name,
        "location": None,
        "coords": None,
        "time_start": None,
        "time_end": None,
        "variables": [],
    }

    full_text = _read_pdf(pdf_path)
    if len(full_text) < 300:
        result["error"] = "Too little text (likely scanned PDF)"
        print(f"[tabulator]   ERROR: too little text ({len(full_text)} chars) — likely scanned PDF")
        return result

    print(f"[tabulator]   full text : {len(full_text):,} chars")

    section_text, _section_fallback = _target_sections(full_text)
    print(f"[tabulator]   sections  : {len(section_text):,} chars  "
          f"({'targeted' if not _section_fallback else 'fallback — no section headers found'})")

    # ── Coordinates ───────────────────────────────────────────────────────────
    m = _COORD_BBOX_RE.search(section_text) or _COORD_BBOX_RE.search(full_text)
    if m:
        la1, d1, la2, d2, lo1, d3, lo2, d4 = m.groups()
        result["coords"] = f"{la1}°{d1}–{la2}°{d2}, {lo1}°{d3}–{lo2}°{d4}"
        result["location"] = result["coords"]
        print(f"[tabulator]   coords    : {result['coords']}  [regex]")
    else:
        print(f"[tabulator]   coords    : not found — falling back to keyword/NER")

    # ── Place names: keyword regex first, NER as supplement ──────────────────
    if not result["location"]:
        kw_places = _places_keywords(full_text)
        ner_places = _places_ner(section_text)
        # Supplement with NER only when keyword detection is sparse
        if len(kw_places) < 3:
            seen_lc: set[str] = {p.lower() for p in kw_places}
            for p in ner_places:
                p_lower = p.lower()
                # Skip NER entries that contain (or are contained by) a keyword result
                if any(kw.lower() in p_lower or p_lower in kw.lower()
                       for kw in kw_places):
                    continue
                if p_lower not in seen_lc:
                    kw_places.append(p)
                    seen_lc.add(p_lower)
        places = kw_places[:5]
        if places:
            source = "keyword" if kw_places else "spaCy NER"
            result["location"] = ", ".join(places)
            print(f"[tabulator]   places    : {result['location']}  [{source}+NER, {len(kw_places)} found]")
        else:
            print(f"[tabulator]   places    : none detected")

    # ── Time range ────────────────────────────────────────────────────────────
    pairs = _YEAR_RANGE_RE.findall(section_text) or _YEAR_RANGE_RE.findall(full_text)
    if pairs:
        # Cascading filter to strip historical-context references:
        #   Level 1: both years ≥ 2000 AND span ≤ 60yr   (modern observational data)
        #   Level 2: both years ≥ 1950 AND span ≤ 80yr   (satellite/instrument era)
        #   Level 3: both years ≥ 1900 AND span ≤ 100yr  (instrumental record)
        #   Fallback: all pairs (paleo / historical papers)
        int_pairs = [(int(a), int(b)) for a, b in pairs]
        filters = [
            (lambda a, b: min(a, b) >= 2000 and abs(b - a) <= 60, "pre-2000/wide pairs excluded"),
            (lambda a, b: min(a, b) >= 1950 and abs(b - a) <= 80, "pre-1950/wide pairs excluded"),
            (lambda a, b: min(a, b) >= 1900 and abs(b - a) <= 100, "pre-1900/wide pairs excluded"),
        ]
        use_pairs = int_pairs
        note = ""
        for filt, label in filters:
            filtered = [(a, b) for a, b in int_pairs if filt(a, b)]
            if filtered:
                use_pairs = filtered
                if len(filtered) < len(int_pairs):
                    note = f"  ({len(int_pairs) - len(filtered)} {label})"
                break
        years = [y for p in use_pairs for y in p]
        result["time_start"] = min(years)
        result["time_end"] = max(years)
        print(f"[tabulator]   time      : {result['time_start']}–{result['time_end']}  "
              f"({len(pairs)} year-range mention(s){note})")
    else:
        singles = sorted(set(int(y) for y in _SINGLE_YEAR_RE.findall(section_text)))
        if singles:
            span = singles[-1] - singles[0]
            if span <= 20:
                # Compact span → likely a data period, not bibliography scatter
                result["time_start"] = singles[0]
                result["time_end"] = singles[-1]
                print(f"[tabulator]   time      : {result['time_start']}–{result['time_end']}  "
                      f"(single years only, {len(singles)} found)")
            else:
                print(f"[tabulator]   time      : not detected from single years "
                      f"({singles[0]}–{singles[-1]}, {span}yr span too wide — likely bibliography)")
        else:
            print(f"[tabulator]   time      : not detected")

    # ── Variables ─────────────────────────────────────────────────────────────
    variables: list[dict] = []
    seen_keys: set[tuple] = set()

    # Method 1: explicit PDF tables
    table_count = 0
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages[:20]:
                for table in (page.extract_tables() or []):
                    for row in table:
                        if row and len(row) >= 2:
                            name_cell = (row[0] or "").strip()
                            unit_cell = (row[1] or "").strip()
                            if name_cell and unit_cell and _valid_unit(unit_cell):
                                key = (name_cell.lower()[:25], unit_cell)
                                if key not in seen_keys:
                                    seen_keys.add(key)
                                    variables.append({"name": name_cell, "acronym": "", "unit": unit_cell, "source": "table"})
                                    table_count += 1
    except Exception:
        pass
    print(f"[tabulator]   pass 1    : PDF tables  → {table_count} variable(s)")

    # Method 2 helper — shared logic for both passes
    def _sweep(text: str, label: str) -> tuple[int, int]:
        candidates = accepted = 0
        cid_skipped = stop_skipped = 0
        for m in _VAR_RE.finditer(text):
            name_raw = re.sub(r'\s+', ' ', m.group(1)).strip()   # normalise whitespace
            inner    = m.group(2).strip()
            candidates += 1
            # Skip PDF font-encoding artifacts like (cid:19)
            if re.match(r"cid:\d+", inner):
                cid_skipped += 1
                continue
            # Skip single-letter figure refs like (a), (j)
            if len(inner) == 1 and inner.isalpha():
                stop_skipped += 1
                continue
            # Skip if whole name, first word, or last word is a stop word
            words = name_raw.split()
            first_word = words[0].lower()
            last_word  = words[-1].lower()
            name_lower = name_raw.lower()
            # Single generic measurement-adjacent words (fine as last word in a phrase but
            # not as standalone variable names)
            _SOLO_STOPS = frozenset({"coverage", "extent", "concentration", "area",
                                     "thickness", "depth", "flux", "discharge"})
            if (name_lower in _STOP_NAMES
                    or name_lower in _SOLO_STOPS
                    or first_word in _STOP_NAMES
                    or last_word in _STOP_NAMES
                    or (len(last_word) == 1 and last_word.isalpha())):
                stop_skipped += 1
                continue
            # Skip repeated word — column-join duplicated: "airtemperature airtemperature"
            if len(words) > 1 and any(
                words[i].lower() == words[i + 1].lower() for i in range(len(words) - 1)
            ):
                stop_skipped += 1
                continue
            # Skip concatenated names — PDF column-join or camelCase artifacts
            if " " not in name_raw and len(name_raw) > 11:
                stop_skipped += 1
                continue
            # SICsub-range style: uppercase run immediately followed by lowercase body
            if re.search(r'[A-Z]{2,}[a-z]', name_raw) and " " not in name_raw:
                stop_skipped += 1
                continue
            # conjunction embedded without spaces: "gainedorlost", "andsalinity"
            if " " not in name_raw and re.search(
                r'(^|[a-z])(or|and|to|of|in)[a-z]', name_raw.lower()
            ):
                stop_skipped += 1
                continue
            # Skip sentence fragments (too long to be a variable name)
            if len(name_raw) > 55:
                stop_skipped += 1
                continue
            # Skip names that contain sentence-fragment phrases
            name_lower = name_raw.lower()
            if re.search(
                r'\b(in its|in the|are a|is a|was a|with a|bars are|that is'
                r'|as it flows|slightly as|contain a|characterised by|since\b'
                r'|flows into|low\b.{0,10}[%]|over the|although\b'
                r'|integrated over|substantially|increases\b|decreases\b)\b',
                name_lower
            ):
                stop_skipped += 1
                continue
            if _valid_unit(inner):
                # No expansion context in direct-unit match — store empty acronym
                key = (name_raw.lower()[:25], inner)
                if key not in seen_keys:
                    seen_keys.add(key)
                    variables.append({"name": name_raw, "acronym": "", "unit": inner, "source": label})
                    accepted += 1
            else:
                parts = re.split(r"[,;\s]+", inner)
                if parts and _valid_unit(parts[-1]):
                    # first part is an acronym if uppercase 2-8 chars AND differs from name
                    acr = (parts[0] if re.match(r"^[A-Z]{2,8}$", parts[0])
                                       and parts[0].lower() != name_raw.lower() else "")
                    key = (acr or name_raw.lower()[:25], parts[-1])
                    if key not in seen_keys:
                        seen_keys.add(key)
                        variables.append({"name": name_raw, "acronym": acr, "unit": parts[-1], "source": label})
                        accepted += 1
        rejected = candidates - accepted - cid_skipped - stop_skipped
        parts = []
        if cid_skipped:  parts.append(f"{cid_skipped} cid-artifacts")
        if stop_skipped: parts.append(f"{stop_skipped} filtered")
        note = f"  ({', '.join(parts)} skipped)" if parts else ""
        print(f"[tabulator]   {label:<10}: bracket regex  → {candidates} candidates, "
              f"{accepted} passed unit whitelist, {rejected} rejected{note}")
        if cid_skipped > 0 and candidates > 0 and cid_skipped / candidates > 0.25:
            print(f"[tabulator]   WARNING   : {cid_skipped}/{candidates} bracket matches are PDF "
                  f"font-encoding artifacts (cid:N) — unit symbols like °C, µmol/L may not be "
                  f"decodeable from this PDF's embedded fonts")
        return candidates, accepted

    # Pass 2a — targeted sections only
    _sweep(section_text, "pass 2a")

    # Pass 2b — full text sweep to catch appendix tables, figure captions, etc.
    before = len(variables)
    _sweep(full_text, "pass 2b")
    extra = len(variables) - before
    if extra:
        print(f"[tabulator]             {extra} additional variable(s) found in full text")

    heuristic_total = len(variables)
    print(f"[tabulator]   total     : {heuristic_total} variable(s) from heuristics")
    for v in variables:
        acr = f" ({v['acronym']})" if v["acronym"] else ""
        print(f"[tabulator]     {v['name']}{acr}  [{v['unit']}]  via {v['source']}")

    # Pass 3 — LLM fallback (always runs in compare mode; otherwise only when heuristics silent)
    if not os.getenv("AZURE_OPENAI_KEY"):
        try:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).parent.parent / "Knowledge_graph" / ".env")
        except Exception:
            pass
    azure_ready = bool(os.getenv("AZURE_OPENAI_KEY") and os.getenv("AZURE_OPENAI_ENDPOINT"))
    run_llm = azure_ready and (compare_llm or heuristic_total == 0)
    if run_llm:
        mode = "compare" if compare_llm and heuristic_total > 0 else "fallback"
        print(f"[tabulator]   pass 3    : LLM variable extraction ({mode})")
        t0 = time.time()
        # When section detection fell back to abstract/intro (no section headers found),
        # send the post-intro window instead — methods sections for most academic papers
        # start around char 8000-18000, well past the abstract/intro region.
        if _section_fallback and len(full_text) > 25000:
            llm_input = full_text[8000:18000]
            print(f"[tabulator]   pass 3    : section fallback — using post-intro window [8000:18000]")
        else:
            llm_input = section_text or full_text[:6000]
        llm_vars = _vars_llm(llm_input)
        elapsed = time.time() - t0

        new_from_llm = 0
        llm_accepted = []
        # Prefix-based dedup: "basal melting" vs "basal melting rate" → keep first
        llm_seen_names: list[str] = [v["name"].lower() for v in variables]
        for item in llm_vars:
            name, unit = item["name"], item["unit"]
            name_lower = name.lower()
            key = (name_lower[:25], unit)
            if key in seen_keys:
                continue
            # Skip if this name is a prefix-extension of an already-accepted name, or vice versa
            if any(
                name_lower.startswith(p + " ") or p.startswith(name_lower + " ")
                for p in llm_seen_names
            ):
                continue
            seen_keys.add(key)
            llm_seen_names.append(name_lower)
            entry = {"name": name, "acronym": "", "unit": unit, "source": "llm"}
            variables.append(entry)
            llm_accepted.append(entry)
            new_from_llm += 1

        if compare_llm and heuristic_total > 0:
            # Side-by-side comparison output
            print(f"[tabulator]   pass 3    : LLM found {len(llm_vars)} candidate(s)  ({elapsed:.1f}s)")
            if llm_vars:
                print(f"[tabulator]   LLM vars  :")
                for item in llm_vars:
                    overlap = any(v["name"].lower()[:20] == item["name"].lower()[:20]
                                  for v in variables if v["source"] != "llm")
                    marker = "=" if overlap else "+"
                    print(f"[tabulator]     [{marker}] {item['name']}  [{item['unit']}]")
                print(f"[tabulator]   [=] = matches heuristic  [+] = new from LLM  "
                      f"({new_from_llm} new added)")
        else:
            print(f"[tabulator]   pass 3    : LLM → {len(llm_vars)} candidate(s), "
                  f"{new_from_llm} accepted  ({elapsed:.1f}s)")
            for v in llm_accepted:
                print(f"[tabulator]     {v['name']}  [{v['unit']}]  via llm")

    total = len(variables)
    print(f"[tabulator]   FINAL     : {total} variable(s)")
    result["variables"] = variables
    return result


def tabulate_papers(pdf_paths: list, compare_llm: bool = False) -> list[dict]:
    print(f"\n[tabulator] ={'=' * 60}")
    print(f"[tabulator] Starting variable tabulation for {len(pdf_paths)} paper(s)")
    print(f"[tabulator] ={'=' * 60}")
    results = [tabulate_paper(p, compare_llm=compare_llm) for p in pdf_paths]
    total_vars = sum(len(r.get("variables", [])) for r in results)
    print(f"\n[tabulator] ={'=' * 60}")
    print(f"[tabulator] Done — {len(pdf_paths)} paper(s), {total_vars} variable(s) total")
    print(f"[tabulator] ={'=' * 60}\n")
    return results
