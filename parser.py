"""Parses Wells Fargo business checking statement PDFs into a transaction table."""
import re
from datetime import date

import pandas as pd
import pdfplumber

DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}$")
AMOUNT_RE = re.compile(r"^-?\$?[\d,]+\.\d{2}$")
CHECK_NUM_RE = re.compile(r"^\d{3,7}$")
STATEMENT_DATE_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+\d{4}"
)

HEADER_STOPWORDS = {
    "check", "number", "description", "date", "deposits/", "withdrawals/",
    "ending", "daily", "credits", "debits", "balance", "transaction",
    "history", "(continued)", "page",
}

# Approximate right-edge (x1) boundaries for the three amount columns,
# derived from the Wells Fargo statement header positions.
COL_DEPOSITS_MAX_X1 = 440
COL_WITHDRAWALS_MAX_X1 = 512
COL_BALANCE_MAX_X1 = 600

CHECK_NUM_MIN_X0, CHECK_NUM_MAX_X0 = 110, 148
DESCRIPTION_MIN_X0 = 149

# Every page repeats a banner ("January 31, 2026 [ Page 5 of 17") near the very
# top; skip anything up there so it never gets merged into a description when a
# transaction happens to straddle a page break.
PAGE_BANNER_MAX_TOP = 40
DATE_MAX_X0 = 90


def _line_groups(words, y_tolerance=2.5):
    """Group words on a page into visual lines by their vertical position."""
    lines = []
    current = []
    current_top = None
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if current_top is None or abs(w["top"] - current_top) <= y_tolerance:
            current.append(w)
            current_top = w["top"] if current_top is None else current_top
        else:
            lines.append(current)
            current = [w]
            current_top = w["top"]
    if current:
        lines.append(current)
    return lines


def _classify_amount(word):
    x1 = word["x1"]
    if x1 <= COL_DEPOSITS_MAX_X1:
        return "deposit"
    if x1 <= COL_WITHDRAWALS_MAX_X1:
        return "withdrawal"
    if x1 <= COL_BALANCE_MAX_X1:
        return "balance"
    return None


def _is_header_noise_line(tokens_text):
    words = [t.lower().strip() for t in tokens_text if t.strip()]
    if not words:
        return True
    non_stopwords = [w for w in words if w not in HEADER_STOPWORDS and not re.match(r"^\d+$", w)]
    return len(non_stopwords) == 0


def _find_statement_year_month(first_page_text):
    m = STATEMENT_DATE_RE.search(first_page_text)
    if not m:
        return date.today().year, date.today().month
    parts = m.group(0).replace(",", "").split()
    month_name, _, year = parts
    month = [
        "january", "february", "march", "april", "may", "june", "july",
        "august", "september", "october", "november", "december",
    ].index(month_name.lower()) + 1
    return int(year), month


def _resolve_date(m_d, stmt_year, stmt_month):
    month, day = (int(p) for p in m_d.split("/"))
    year = stmt_year
    if month > stmt_month:
        year -= 1
    return date(year, month, day)


def parse_statement_pdf(file) -> pd.DataFrame:
    """
    Parse a Wells Fargo business checking statement PDF (file path or
    file-like object) into a DataFrame with columns:
    Date, CheckNumber, Description, Amount, Type, EndingDailyBalance, SourceFile
    Amount is signed: positive for deposits/credits, negative for withdrawals/debits.
    """
    transactions = []
    parsing_active = False
    stopped = False
    stmt_year = stmt_month = None
    current = None

    def flush():
        if current is not None:
            transactions.append(current)

    with pdfplumber.open(file) as pdf:
        first_page_text = pdf.pages[0].extract_text() or ""
        stmt_year, stmt_month = _find_statement_year_month(first_page_text)

        for page in pdf.pages:
            if stopped:
                break
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            if not words:
                continue

            for line in _line_groups(words):
                if stopped:
                    break
                line = sorted(line, key=lambda w: w["x0"])
                texts = [w["text"] for w in line]

                if line[0]["top"] < PAGE_BANNER_MAX_TOP:
                    continue

                # Global stop: the "Totals" row ends the transaction table for good.
                if texts and texts[0].strip().lower() == "totals":
                    stopped = True
                    break

                if not parsing_active:
                    # Look for the column header row to know the table has started.
                    lower_texts = [t.lower() for t in texts]
                    if "date" in lower_texts and "description" in lower_texts:
                        parsing_active = True
                    continue

                if _is_header_noise_line(texts):
                    continue

                first_word = line[0]
                is_new_txn = (
                    first_word["x0"] < DATE_MAX_X0 and DATE_RE.match(first_word["text"])
                )

                if is_new_txn:
                    flush()
                    current = {
                        "Date": _resolve_date(first_word["text"], stmt_year, stmt_month),
                        "CheckNumber": None,
                        "Description": [],
                        "Amount": None,
                        "Type": None,
                        "EndingDailyBalance": None,
                    }
                    remaining = line[1:]
                else:
                    if current is None:
                        # Stray line before any transaction started; ignore.
                        continue
                    remaining = line

                for w in remaining:
                    text = w["text"]
                    if AMOUNT_RE.match(text):
                        col = _classify_amount(w)
                        if col == "deposit":
                            current["Amount"] = float(text.replace(",", ""))
                            current["Type"] = "Credit"
                        elif col == "withdrawal":
                            current["Amount"] = -float(text.replace(",", ""))
                            current["Type"] = "Debit"
                        elif col == "balance":
                            current["EndingDailyBalance"] = float(text.replace(",", ""))
                        continue
                    if (
                        current["CheckNumber"] is None
                        and CHECK_NUM_MIN_X0 <= w["x0"] <= CHECK_NUM_MAX_X0
                        and CHECK_NUM_RE.match(text)
                    ):
                        current["CheckNumber"] = text
                        continue
                    if w["x0"] >= DESCRIPTION_MIN_X0 - 5:
                        current["Description"].append(text)

    flush()

    rows = []
    for t in transactions:
        if t["Amount"] is None:
            continue
        rows.append({
            "Date": t["Date"],
            "CheckNumber": t["CheckNumber"],
            "Description": " ".join(t["Description"]).strip(),
            "Amount": t["Amount"],
            "Type": t["Type"],
            "EndingDailyBalance": t["EndingDailyBalance"],
        })

    df = pd.DataFrame(rows, columns=[
        "Date", "CheckNumber", "Description", "Amount", "Type", "EndingDailyBalance",
    ])
    return df
