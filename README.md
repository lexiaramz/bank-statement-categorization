# Bank Statement Categorizer

Upload a Wells Fargo business checking statement PDF, review auto-categorized
line items, fix anything wrong, and export to Excel with per-category
subtotals.

## How it works

1. **`parser.py`** reads the PDF with `pdfplumber` and reconstructs the
   transaction table (it's tuned to the Wells Fargo "Initiate Business
   Checking" layout — date/check-number/description/deposits/withdrawals/
   balance columns, multi-line descriptions, repeated page headers).
2. **`categorizer.py`** matches each transaction's description against
   keyword rules in `rules.json` (first match wins). Anything that matches
   nothing is left `Uncategorized` for manual review — it never guesses.
3. **`app.py`** (Streamlit) lets you upload PDFs, edit categories inline in a
   table, edit the keyword rules themselves in the sidebar, and download the
   result as an `.xlsx` with a `Transactions` sheet and a `Summary` sheet
   (subtotal + count per category).

## Run locally

```bash
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\streamlit run app.py
```

Then open http://localhost:8501.

## Deploy to Railway

This repo already has a `Procfile`, `.python-version`, and
`.streamlit/config.toml` set up for Railway's Nixpacks builder — just
connect the repo/push and Railway will detect it as a Python app and run the
`web` process.

**Rules persistence caveat:** `rules.json` lives in the repo. Editing
keyword rules in the sidebar and clicking "Save rules" writes to the
container's filesystem, which is wiped on every new deploy. For rule
changes you want to keep permanently, either:

- edit `rules.json` in the repo and redeploy, or
- attach a Railway volume mounted over the project directory so runtime
  edits survive deploys.

## Editing categories/keywords

Open the sidebar in the app — it's a table of `Category` / `Keywords
(comma-separated)`. Add, remove, or rename rows, then click **Save rules**.
Existing transactions already marked with a category are left alone; use
**Re-apply to Uncategorized** to run the updated rules only against rows
still marked `Uncategorized`.

The starter rules in `rules.json` were seeded from real transactions in a
sample January 2026 statement (Gensco/Ferguson/Platt/Keller → Job Costs,
Intuit QuickBooks Payments/Podium/Verizon/Comcast/ADT → Business
Applications, Labor&Industries Permit → Build Permits, etc.). Categories
like Travel, Legal, Food, Classes and Workshops, and Div had no matching
transactions in that sample, so their keyword lists are just common-sense
placeholders — expect to refine them (or add rules) as you run real
statements through.

## Other banks / statement formats

`parser.py` is written specifically for Wells Fargo's business checking
statement layout. A statement from a different bank will very likely parse
incorrectly or return zero rows — that's expected, not a silent failure to
worry about. Bring a sample and the parser can be adapted.

---

## | web-production-a1383.up.railway.app |
