"""Keyword-rule based transaction categorization."""
import json
import os

import pandas as pd

DEFAULT_RULES_PATH = os.path.join(os.path.dirname(__file__), "rules.json")
UNCATEGORIZED = "Uncategorized"


def load_rules(path: str = DEFAULT_RULES_PATH) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_rules(rules: list[dict], path: str = DEFAULT_RULES_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rules, f, indent=2)


def category_names(rules: list[dict]) -> list[str]:
    return [r["category"] for r in rules] + [UNCATEGORIZED]


def categorize_description(description: str, rules: list[dict]) -> str:
    text = (description or "").lower()
    for rule in rules:
        for keyword in rule.get("keywords", []):
            keyword = keyword.strip().lower()
            if keyword and keyword in text:
                return rule["category"]
    return UNCATEGORIZED


def apply_categories(df: pd.DataFrame, rules: list[dict]) -> pd.DataFrame:
    df = df.copy()
    df["Category"] = df["Description"].apply(lambda d: categorize_description(d, rules))
    return df
