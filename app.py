import io
from datetime import date

import pandas as pd
import streamlit as st

from categorizer import (
    UNCATEGORIZED,
    apply_categories,
    category_names,
    load_rules,
    save_rules,
)
from excel_export import build_workbook
from parser import parse_statement_pdf

st.set_page_config(page_title="Puget Heating - Statement Categorizer", layout="wide")

if "rules" not in st.session_state:
    st.session_state.rules = load_rules()
if "transactions" not in st.session_state:
    st.session_state.transactions = pd.DataFrame(columns=[
        "Date", "CheckNumber", "Description", "Amount", "Type",
        "EndingDailyBalance", "SourceFile", "Category",
    ])
if "processed_files" not in st.session_state:
    st.session_state.processed_files = set()


def rules_to_editor_df(rules):
    return pd.DataFrame([
        {"Category": r["category"], "Keywords (comma-separated)": ", ".join(r.get("keywords", []))}
        for r in rules
    ])


def editor_df_to_rules(edited_df):
    rules = []
    for _, row in edited_df.iterrows():
        category = str(row["Category"]).strip()
        if not category:
            continue
        keywords_raw = str(row.get("Keywords (comma-separated)", "") or "")
        keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
        rules.append({"category": category, "keywords": keywords})
    return rules


st.title("Bank Statement Categorizer")
st.caption("Upload a Wells Fargo business checking statement PDF, review the auto-categorized "
           "line items, fix anything that's wrong, then export to Excel with category subtotals.")

with st.sidebar:
    st.header("Categories & Keyword Rules")
    st.caption("First matching rule wins. Anything that matches nothing is left Uncategorized "
               "for you to assign by hand.")
    edited_rules_df = st.data_editor(
        rules_to_editor_df(st.session_state.rules),
        num_rows="dynamic",
        use_container_width=True,
        key="rules_editor",
    )
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Save rules", use_container_width=True):
            st.session_state.rules = editor_df_to_rules(edited_rules_df)
            save_rules(st.session_state.rules)
            st.success("Rules saved.")
    with col_b:
        if st.button("Re-apply to Uncategorized", use_container_width=True):
            df = st.session_state.transactions
            if not df.empty:
                mask = df["Category"] == UNCATEGORIZED
                recat = apply_categories(df.loc[mask], st.session_state.rules)
                df.loc[mask, "Category"] = recat["Category"].values
                st.session_state.transactions = df
            st.success("Uncategorized rows re-checked against current rules.")

uploaded_files = st.file_uploader(
    "Upload bank statement PDF(s)", type=["pdf"], accept_multiple_files=True,
)

if uploaded_files:
    already_done = all(
        f"{f.name}:{f.size}" in st.session_state.processed_files for f in uploaded_files
    )
    run_clicked = st.button(
        "Categorize Transactions",
        type="primary",
        use_container_width=True,
        disabled=already_done,
    )
    if already_done:
        st.caption("These file(s) are already processed below. Upload a different file to enable this button again.")

    if run_clicked:
        new_rows = []
        with st.spinner("Parsing and categorizing..."):
            for f in uploaded_files:
                file_id = f"{f.name}:{f.size}"
                if file_id in st.session_state.processed_files:
                    continue
                try:
                    df = parse_statement_pdf(io.BytesIO(f.getvalue()))
                except Exception as e:
                    st.error(f"Failed to parse {f.name}: {e}")
                    continue
                if df.empty:
                    st.warning(f"No transactions found in {f.name}. Is this a Wells Fargo "
                               f"business checking statement?")
                    continue
                df["SourceFile"] = f.name
                df = apply_categories(df, st.session_state.rules)
                new_rows.append(df)
                st.session_state.processed_files.add(file_id)

        if new_rows:
            st.session_state.transactions = pd.concat(
                [st.session_state.transactions] + new_rows, ignore_index=True,
            )
            added = sum(len(d) for d in new_rows)
            st.success(f"Categorized {added} transaction(s) from {len(new_rows)} file(s).")
        else:
            st.warning("Nothing was added — check the errors/warnings above.")

transactions = st.session_state.transactions

if transactions.empty:
    st.info("Upload a statement PDF to get started.")
else:
    total_deposits = transactions.loc[transactions.Amount > 0, "Amount"].sum()
    total_withdrawals = transactions.loc[transactions.Amount < 0, "Amount"].sum()
    uncategorized_count = (transactions["Category"] == UNCATEGORIZED).sum()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Transactions", len(transactions))
    m2.metric("Total Deposits", f"${total_deposits:,.2f}")
    m3.metric("Total Withdrawals", f"${-total_withdrawals:,.2f}")
    m4.metric("Uncategorized", int(uncategorized_count))

    st.subheader("Review & edit line items")
    st.caption("Click any Category cell to change it. Edits are kept even if you upload another statement.")

    options = category_names(st.session_state.rules)
    edited = st.data_editor(
        transactions,
        use_container_width=True,
        height=500,
        num_rows="dynamic",
        key="transactions_editor",
        column_config={
            "Date": st.column_config.DateColumn("Date", format="MM/DD/YYYY"),
            "CheckNumber": st.column_config.TextColumn("Check #"),
            "Description": st.column_config.TextColumn("Description", width="large"),
            "Amount": st.column_config.NumberColumn("Amount", format="$%.2f"),
            "Type": st.column_config.TextColumn("Type"),
            "EndingDailyBalance": st.column_config.NumberColumn("Ending Daily Balance", format="$%.2f"),
            "SourceFile": st.column_config.TextColumn("Source File"),
            "Category": st.column_config.SelectboxColumn("Category", options=options, required=True),
        },
        column_order=[
            "Date", "CheckNumber", "Description", "Category", "Type", "Amount",
            "EndingDailyBalance", "SourceFile",
        ],
    )
    st.session_state.transactions = edited
    transactions = edited

    st.subheader("Category subtotals")
    summary = (
        transactions.groupby("Category", as_index=False)["Amount"]
        .agg(Total="sum", Count="count")
        .sort_values("Total")
    )
    st.dataframe(
        summary,
        use_container_width=True,
        column_config={
            "Total": st.column_config.NumberColumn("Total", format="$%.2f"),
        },
        hide_index=True,
    )

    st.subheader("Export")
    workbook_bytes = build_workbook(transactions)
    st.download_button(
        "Download Excel (.xlsx)",
        data=workbook_bytes,
        file_name=f"categorized_transactions_{date.today().isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    if st.button("Clear all data"):
        st.session_state.transactions = pd.DataFrame(columns=transactions.columns)
        st.session_state.processed_files = set()
        st.rerun()
