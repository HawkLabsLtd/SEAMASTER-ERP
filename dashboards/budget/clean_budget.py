import os
import pandas as pd
import numpy as np
import re
from pathlib import Path

# Input/output live in <data dir>/budget (SEAMASTER_DATA_DIR, default data/)
SCRIPT_DIR = Path(os.getenv('SEAMASTER_DATA_DIR') or Path(__file__).resolve().parents[2] / 'data') / 'budget'
INPUT_FILE = SCRIPT_DIR / "budget_report_1399-1400.csv"
INPUT_FILE_EN = SCRIPT_DIR / "budget_report_1399-1400-EN.csv"
OUTPUT_WIDE = SCRIPT_DIR / "cleaned_budget_wide.csv"
OUTPUT_LONG = SCRIPT_DIR / "cleaned_budget_long.csv"

ENCODINGS = ["utf-8-sig", "utf-8", "cp1256", "windows-1256", "latin1"]

MEASURES_ORDER = ["budget", "actual", "variance"]

MEASURE_LABEL_MAP = {
    "approved budget": "approved",
    "approved": "approved",
    "expenses incurred": "expenses",
    "expenses": "expenses",
    "budget deduction": "deduction",
    "deduction": "deduction",
}

def read_csv_any_encoding(path: Path) -> pd.DataFrame:
    last_err = None
    for enc in ENCODINGS:
        try:
            return pd.read_csv(path, header=None, encoding=enc)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Failed to read CSV with known encodings: {last_err}")


def extract_year(value) -> str:
    s = str(value)
    m = re.search(r"(13|14)\d{2}", s)
    return m.group(0) if m else None


def clean_numeric_cell(x):
    if pd.isna(x):
        return np.nan
    s = str(x)
    s = s.replace('"', '').strip()
    # Common placeholders for missing values like '-' or ' -    '
    if s == '' or s == '-' or s.replace(' ', '') == '-':
        return np.nan
    neg = False
    # Some cells have a trailing '-' to indicate negative values
    if s.endswith('-'):
        neg = True
        s = s[:-1]
    # Remove thousands separators and odd punctuation
    s = s.replace(',', '')
    s = s.replace('٬', '')  # Arabic thousands separator
    s = s.replace('،', '')  # Arabic comma
    # Remove left-to-right/right-to-left marks
    s = s.replace('\u200f', '').replace('\u202a', '').replace('\u202c', '')
    # Keep only digits and dot
    s = re.sub(r"[^0-9.]", "", s)
    if s == "":
        return np.nan
    # Prefer integers; fall back to float
    try:
        if '.' in s:
            val = float(s)
        else:
            val = int(s)
    except Exception:
        return np.nan
    return -val if neg else val


def build_columns(df: pd.DataFrame, measures_order: list) -> list:
    # First row holds years; second row holds measure labels (in Persian/English, order assumed as triples)
    years_row = df.iloc[0].astype(str).tolist()
    measures_row = df.iloc[1].astype(str).tolist()

    columns = ["category"]
    # Starting from col 1, group in triples
    i = 1
    group_idx = 0
    while i < df.shape[1]:
        year_raw = years_row[i] if i < len(years_row) else ''
        year = extract_year(year_raw) or f"unknown_{group_idx}"
        for j, m in enumerate(measures_order):
            col_idx = i + j
            if col_idx >= df.shape[1]:
                break
            columns.append(f"{year}_{m}")
        i += 3
        group_idx += 1
    return columns


def build_columns_en(df: pd.DataFrame) -> list:
    years_row = df.iloc[0].astype(str).tolist()
    measures_row = df.iloc[1].astype(str).tolist()
    columns = ["category"]
    current_year = None
    for i in range(1, df.shape[1]):
        yr = extract_year(years_row[i])
        if yr:
            current_year = yr
        meas_raw = measures_row[i].strip().lower()
        meas = MEASURE_LABEL_MAP.get(meas_raw)
        if current_year and meas:
            columns.append(f"{current_year}_{meas}")
        else:
            columns.append(f"unknown_{i}")
    return columns

def cleanse_and_normalize():
    # Prefer English CSV if available
    src_file = INPUT_FILE_EN if INPUT_FILE_EN.exists() else INPUT_FILE
    df = read_csv_any_encoding(src_file)

    # Build normalized columns
    if src_file == INPUT_FILE_EN:
        columns = build_columns_en(df)
    else:
        columns = build_columns(df, MEASURES_ORDER)
    # Assign and drop header rows
    df.columns = columns
    df = df.iloc[2:].reset_index(drop=True)

    # Tidy up category names
    df["category"] = df["category"].astype(str).str.strip()
    df["category"] = df["category"].replace({"": np.nan}).fillna("Unlabeled")

    # Clean numeric columns
    num_cols = [c for c in df.columns if c != "category"]
    for c in num_cols:
        df[c] = df[c].apply(clean_numeric_cell)

    # Save wide format
    df.to_csv(OUTPUT_WIDE, index=False)

    # Build long format: category, year, measure, value
    long = []
    for c in num_cols:
        m = re.match(r"(\d{4})_(\w+)", c)
        if not m:
            # Skip unknown columns
            continue
        year, measure = m.group(1), m.group(2)
        part = df[["category", c]].copy()
        part.columns = ["category", "value"]
        part["year"] = int(year)
        part["measure"] = measure
        long.append(part)
    if long:
        long_df = pd.concat(long, axis=0, ignore_index=True)
    else:
        long_df = pd.DataFrame(columns=["category", "value", "year", "measure"])

    long_df.to_csv(OUTPUT_LONG, index=False)
    return OUTPUT_WIDE, OUTPUT_LONG


if __name__ == "__main__":
    w, l = cleanse_and_normalize()
    print(f"Cleaned datasets written to:\n- {w}\n- {l}")