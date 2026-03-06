"""
Shared loader: takes zip bytes (or direct file bytes), runs Arelle, returns a DataFrame of facts.
Also provides extract_text_sections() for narrative text extraction from the same iXBRL source.
skipDTS=True avoids network calls to ESMA taxonomy servers.
"""
import os
import re
import tempfile
import zipfile
import pandas as pd
import streamlit as st

# ─── Statement classification ──────────────────────────────────────────────────

STATEMENT_MAP = {
    "Revenue": "Income Statement", "GrossProfit": "Income Statement",
    "OperatingIncomeLoss": "Income Statement", "ProfitLoss": "Income Statement",
    "ProfitLossFromOperatingActivities": "Income Statement", "ProfitLossBeforeTax": "Income Statement",
    "IncomeTaxExpenseContinuingOperations": "Income Statement", "ProfitLossFromContinuingOperations": "Income Statement",
    "ProfitLossAttributableToOwnersOfParent": "Income Statement", "BasicEarningsLossPerShare": "Income Statement",
    "DilutedEarningsLossPerShare": "Income Statement", "FinanceCosts": "Income Statement",
    "FinanceIncome": "Income Statement", "DistributionCosts": "Income Statement",
    "AdministrativeExpense": "Income Statement", "CostOfSales": "Income Statement",
    "Assets": "Balance Sheet", "NoncurrentAssets": "Balance Sheet", "CurrentAssets": "Balance Sheet",
    "Liabilities": "Balance Sheet", "NoncurrentLiabilities": "Balance Sheet", "CurrentLiabilities": "Balance Sheet",
    "Equity": "Balance Sheet", "EquityAttributableToOwnersOfParent": "Balance Sheet",
    "CashAndCashEquivalents": "Balance Sheet", "TradeAndOtherCurrentReceivables": "Balance Sheet",
    "Inventories": "Balance Sheet", "PropertyPlantAndEquipment": "Balance Sheet",
    "IntangibleAssetsOtherThanGoodwill": "Balance Sheet", "Goodwill": "Balance Sheet",
    "TradeAndOtherCurrentPayables": "Balance Sheet", "IssuedCapital": "Balance Sheet",
    "RetainedEarnings": "Balance Sheet",
    "CashFlowsFromUsedInOperatingActivities": "Cash Flow", "CashFlowsFromUsedInInvestingActivities": "Cash Flow",
    "CashFlowsFromUsedInFinancingActivities": "Cash Flow", "IncreaseDecreaseInCashAndCashEquivalents": "Cash Flow",
    "AdjustmentsForDepreciationAndAmortisationExpense": "Cash Flow",
    "OtherComprehensiveIncome": "Other Comprehensive Income", "ComprehensiveIncome": "Other Comprehensive Income",
}

def classify_statement(name):
    if name in STATEMENT_MAP:
        return STATEMENT_MAP[name]
    n = name.lower()
    if any(k in n for k in ["revenue","profit","loss","income","expense","earnings","ebit","sales","cost"]):
        return "Income Statement"
    if any(k in n for k in ["asset","liabilit","equity","cash","inventor","payable","receivable","goodwill","capital","reserve","borrowing"]):
        return "Balance Sheet"
    if any(k in n for k in ["cashflow","cash flow","operating activit","investing activit","financing activit"]):
        return "Cash Flow"
    return "Other / Extension"


# ─── Annual report section classification ─────────────────────────────────────

SECTION_PATTERNS = [
    ("Strategic Report",             r"strategic\s+report"),
    ("Chair's Statement",            r"chair(?:man|woman|person)?'?s?\s+statement|letter\s+from\s+the\s+chair"),
    ("CEO Statement",                r"chief\s+executi\w+['\u2019]?s?\s+(?:statement|review|letter)|ceo\s+(?:statement|review)"),
    ("CFO Review",                   r"chief\s+financial\s+officer|cfo\s+(?:statement|review)|finance\s+(?:director|review)"),
    ("Business Overview",            r"business\s+(?:overview|model|description|at\s+a\s+glance)"),
    ("Market Review",                r"market\s+(?:review|overview|context|environment)"),
    ("Strategy",                     r"(?:our\s+)?strateg(?:y|ic\s+priorities|ic\s+objectives)"),
    ("Key Performance Indicators",   r"key\s+performance\s+indicators|kpis?"),
    ("Principal Risks",              r"principal\s+risks?|risk\s+management|risks?\s+and\s+uncertainties"),
    ("Viability Statement",          r"viability\s+statement"),
    ("Sustainability / ESG",         r"sustainabilit|esg|environmental|social\s+and\s+governance|climate|net\s+zero|carbon"),
    ("Section 172",                  r"section\s+172|stakeholder\s+engagement"),
    ("Directors' Report",            r"directors['\u2019]?\s+report"),
    ("Corporate Governance",         r"corporate\s+governance"),
    ("Board of Directors",           r"board\s+of\s+directors|our\s+board"),
    ("Audit Committee",              r"audit\s+committee"),
    ("Remuneration Report",          r"remuneration\s+(?:report|committee|policy)|directors['\u2019]?\s+remuneration"),
    ("Nomination Committee",         r"nomination\s+(?:committee|report)"),
    ("Independent Auditor's Report", r"independent\s+auditor|auditor['\u2019]?s\s+report"),
    ("Income Statement",             r"(?:consolidated\s+)?(?:income\s+statement|profit\s+(?:and|&)\s+loss|statement\s+of\s+(?:comprehensive\s+)?income)"),
    ("Balance Sheet",                r"(?:consolidated\s+)?(?:balance\s+sheet|statement\s+of\s+financial\s+position)"),
    ("Cash Flow Statement",          r"(?:consolidated\s+)?(?:cash\s+flow|statement\s+of\s+cash\s+flows)"),
    ("Statement of Changes in Equity", r"(?:consolidated\s+)?statement\s+of\s+(?:changes\s+in\s+)?equity"),
    ("Accounting Policies",          r"accounting\s+policies|basis\s+of\s+(?:preparation|consolidation)"),
    ("Notes to Accounts",            r"notes?\s+to\s+(?:the\s+)?(?:financial\s+)?(?:statements?|accounts?)"),
    ("Five Year Summary",            r"five\s+year|financial\s+(?:summary|highlights)|historical\s+(?:data|summary)"),
    ("Shareholder Information",      r"shareholder\s+information|investor\s+(?:relations|information)"),
    ("Glossary",                     r"glossar"),
    ("Other",                        r".*"),
]

_COMPILED = [(name, re.compile(pat, re.IGNORECASE)) for name, pat in SECTION_PATTERNS]


def _classify_heading(text: str) -> str:
    for name, pat in _COMPILED:
        if pat.search(text):
            return name
    return "Other"


def _clean(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


# ─── Text section extraction ───────────────────────────────────────────────────

def extract_text_sections(html_bytes: bytes) -> pd.DataFrame:
    """
    Given raw iXBRL/HTML bytes, strip XBRL tags and extract narrative text
    classified into annual report sections.

    Returns a DataFrame with columns:
        section, heading, seq, char_count, text
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        import subprocess, sys
        subprocess.run([sys.executable, "-m", "pip", "install", "beautifulsoup4",
                        "--break-system-packages", "-q"], check=False)
        from bs4 import BeautifulSoup

    html_str = html_bytes.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html_str, "html.parser")

    # Remove non-content tags
    for tag in soup(["script", "style", "nav", "noscript", "iframe"]):
        tag.decompose()

    # Unwrap iXBRL inline tags (ix:nonfraction, ix:nonnumeric, etc.)
    # so their text content remains but the wrapper tags disappear
    for ix_tag in soup.find_all(re.compile(r'^ix:', re.I)):
        ix_tag.unwrap()
    # Also handle namespace-prefixed variants without colon (some parsers flatten them)
    for ix_tag in soup.find_all(re.compile(r'^ix')):
        try:
            ix_tag.unwrap()
        except Exception:
            pass

    heading_tags = {"h1", "h2", "h3", "h4"}
    rows = []
    current_heading = None
    current_section = "Other"
    current_chunks = []
    seq = 0

    def flush():
        nonlocal seq
        text = _clean(" ".join(current_chunks))
        if len(text) > 40:   # skip tiny fragments
            rows.append({
                "section":    current_section,
                "heading":    current_heading or "",
                "seq":        seq,
                "char_count": len(text),
                "text":       text,
            })
            seq += 1

    body = soup.body if soup.body else soup
    for element in body.descendants:
        if not hasattr(element, 'name') or element.name is None:
            continue
        if element.name in heading_tags:
            heading_text = _clean(element.get_text())
            if heading_text:
                flush()
                current_chunks = []
                current_heading = heading_text
                current_section = _classify_heading(heading_text)
        elif element.name in {"p", "li", "td", "th"}:
            # Only grab leaf-ish nodes to avoid double-counting
            if not any(c.name in heading_tags | {"p", "li"} for c in element.children
                       if hasattr(c, 'name') and c.name):
                t = _clean(element.get_text())
                if len(t) > 20:
                    current_chunks.append(t)

    flush()

    if not rows:
        return pd.DataFrame(columns=["section", "heading", "seq", "char_count", "text"])

    return pd.DataFrame(rows, columns=["section", "heading", "seq", "char_count", "text"])


# ─── ESEF zip utilities ────────────────────────────────────────────────────────

def find_entry_point(extract_dir):
    for root, dirs, files in os.walk(extract_dir):
        for f in files:
            if f.endswith(('.xhtml','.htm','.html')) and 'report' in root.lower():
                return os.path.join(root, f)
    for root, dirs, files in os.walk(extract_dir):
        for f in files:
            if f.endswith(('.xhtml','.htm','.html')):
                return os.path.join(root, f)
    for root, dirs, files in os.walk(extract_dir):
        for f in files:
            if f.endswith('.xml') and not f.startswith('.'):
                return os.path.join(root, f)
    return None


def _parse_arelle(entry_path: str, logs: list, meta: dict) -> pd.DataFrame:
    """Shared Arelle parsing logic given a resolved file path."""
    from arelle import Cntlr, ModelManager

    cntlr = Cntlr.Cntlr(logFileName="logToStdErr")
    model_manager = ModelManager.initialize(cntlr)
    model_manager.skipDTS = True
    model_xbrl = model_manager.load(entry_path)

    if model_xbrl is None:
        raise RuntimeError("Arelle failed to load the report.")

    rows = []
    for fact in model_xbrl.facts:
        try:
            concept = fact.concept
            if concept is not None:
                local_name = concept.qname.localName
                ns = concept.qname.namespaceURI or ""
                try:
                    label = concept.label(lang="en") or local_name
                except Exception:
                    label = local_name
            else:
                local_name = fact.qname.localName
                ns = fact.qname.namespaceURI or ""
                label = local_name
        except Exception:
            try:
                local_name = fact.qname.localName
                ns = ""
                label = local_name
            except Exception:
                continue

        try:
            ctx = fact.context
            if ctx is None:
                period_type = period_start = period_end = ""
            elif ctx.isInstantPeriod:
                period_type = "instant"
                period_start = ""
                period_end = str(ctx.instantDatetime.date()) if ctx.instantDatetime else ""
            elif ctx.isStartEndPeriod:
                period_type = "duration"
                period_start = str(ctx.startDatetime.date()) if ctx.startDatetime else ""
                period_end = str(ctx.endDatetime.date()) if ctx.endDatetime else ""
            else:
                period_type = "forever"
                period_start = period_end = ""
        except Exception:
            ctx = None
            period_type = period_start = period_end = ""

        unit_str = ""
        try:
            unit = fact.unit
            if unit is not None:
                unit_str = str(unit.value)
        except Exception:
            pass

        dims = {}
        try:
            if ctx is not None:
                for dq, dv in ctx.qnameDims.items():
                    try:
                        dims[dq.localName] = dv.memberQname.localName if dv.isExplicit else str(dv.typedMember)
                    except Exception:
                        dims[dq.localName] = str(dv)
        except Exception:
            pass

        value = ""
        try:
            value = fact.value
        except Exception:
            try:
                value = fact.text or ""
            except Exception:
                pass

        entity = ""
        try:
            if ctx and ctx.entityIdentifier:
                entity = ctx.entityIdentifier[1]
        except Exception:
            pass

        rows.append({
            "Concept": local_name, "Label": label, "Namespace": ns,
            "Statement": classify_statement(local_name),
            "Period Type": period_type, "Period Start": period_start, "Period End": period_end,
            "Value": value, "Unit": unit_str,
            "Decimals": getattr(fact, "decimals", "") or "",
            "Entity": entity,
            "Dimensions": "; ".join(f"{k}={v}" for k, v in dims.items()) if dims else "",
        })

    try:
        for ctx in model_xbrl.contexts.values():
            if ctx.entityIdentifier:
                meta["entity_id"] = ctx.entityIdentifier[1]
                break
    except Exception:
        pass

    logs.append(f"Facts found: {len(rows)}")
    model_manager.close()

    COLUMNS = ["Concept","Label","Namespace","Statement","Period Type",
               "Period Start","Period End","Value","Unit","Decimals","Entity","Dimensions"]

    if not rows:
        df = pd.DataFrame(columns=COLUMNS)
        df["_numeric"] = pd.Series(dtype=float)
        logs.append("Warning: no facts could be extracted.")
        return df

    df = pd.DataFrame(rows, columns=COLUMNS)
    df["Value"] = pd.to_numeric(df["Value"], errors="ignore")
    df["_numeric"] = pd.to_numeric(df["Value"], errors="coerce")
    return df


# ─── Public API ────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_facts(zip_bytes: bytes):
    """Load XBRL facts from a ZIP package. Returns (df, logs, meta)."""
    logs = []
    meta = {}

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "report.zip")
        with open(zip_path, "wb") as f:
            f.write(zip_bytes)
        extract_dir = os.path.join(tmpdir, "extracted")
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_dir)

        entry = find_entry_point(extract_dir)
        if not entry:
            raise FileNotFoundError("Could not find an XBRL/iXBRL entry point in the zip.")
        logs.append(f"Entry point: {os.path.relpath(entry, extract_dir)}")

        df = _parse_arelle(entry, logs, meta)

    return df, logs, meta


@st.cache_data(show_spinner=False)
def load_facts_from_file(file_bytes: bytes, file_ext: str, filename: str):
    """
    Handles zip packages and direct xhtml/html/xml files.
    Returns (df, logs, meta).
    """
    if file_ext == "zip":
        return load_facts(file_bytes)

    logs = [f"Direct file load: {filename}"]
    meta = {}

    with tempfile.TemporaryDirectory() as tmpdir:
        entry = os.path.join(tmpdir, filename)
        with open(entry, "wb") as f:
            f.write(file_bytes)
        df = _parse_arelle(entry, logs, meta)

    return df, logs, meta


@st.cache_data(show_spinner=False)
def load_text_sections(file_bytes: bytes, file_ext: str, filename: str) -> pd.DataFrame:
    """
    Extract narrative text sections from an iXBRL/HTML file or ZIP package.
    Returns a DataFrame with columns: section, heading, seq, char_count, text.
    """
    if file_ext == "zip":
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "report.zip")
            with open(zip_path, "wb") as f:
                f.write(file_bytes)
            extract_dir = os.path.join(tmpdir, "extracted")
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(extract_dir)
            entry = find_entry_point(extract_dir)
            if not entry:
                raise FileNotFoundError("Could not find an HTML/iXBRL entry point in the zip.")
            with open(entry, "rb") as f:
                html_bytes = f.read()
    else:
        html_bytes = file_bytes

    return extract_text_sections(html_bytes)
