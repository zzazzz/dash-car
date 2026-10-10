"""Load, cleaning dan validasi data PPD."""
import io
import re

import numpy as np
import pandas as pd
import streamlit as st

from business_mapping import CAR_PORTFOLIOS, P_OTHER, S_OTHER, classify

MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MEI": 5, "MAY": 5, "JUN": 6, "JUL": 7, "AGU": 8,
          "AGT": 8, "AUG": 8, "SEP": 9, "OKT": 10, "OCT": 10, "NOV": 11, "DES": 12, "DEC": 12}
NUM_COLS = ["Pokok Hutang", "OTR", "Total Piutang", "Bunga", "DP (Gross)", "TOP", "EFF RATE",
            "Angsuran", "Admin Fee", "Tahun Prod"]
DIM_COLS = ["Financing Type", "Sales Through", "DLC", "Internal Sales Force", "CFO", "Inisiator",
            "Model", "Object", "Jenis Produk", "Status", "Kode dan Nama Dealer"]
UNKNOWN = "Tidak diketahui"


def _find_header(raw: pd.DataFrame) -> int:
    for i in range(min(len(raw), 40)):
        if str(raw.iat[i, 0]).strip().upper() == "NO":
            return i
    raise ValueError("Baris header (kolom 'NO') tidak ditemukan pada 40 baris pertama.")


def _parse_period(raw: pd.DataFrame, hdr: int):
    for i in range(hdr):
        for v in raw.iloc[i].dropna().astype(str):
            m = re.search(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})\s*s/d\s*(\d{1,2})-([A-Za-z]{3})-(\d{4})", v)
            if m:
                try:
                    a = pd.Timestamp(int(m[3]), MONTHS[m[2].upper()], int(m[1]))
                    b = pd.Timestamp(int(m[6]), MONTHS[m[5].upper()], int(m[4]))
                    return a, b
                except Exception:
                    return None
    return None


@st.cache_data(show_spinner="Memuat dan memvalidasi data PPD...")
def load_and_prepare(source):
    """source: path (str) atau bytes. Return (df, dq)."""
    content = source if isinstance(source, (bytes, bytearray)) else open(source, "rb").read()
    raw = pd.read_excel(io.BytesIO(content), sheet_name=0, header=None)
    hdr = _find_header(raw)
    period = _parse_period(raw, hdr)
    df = pd.read_excel(io.BytesIO(content), sheet_name=0, header=hdr)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how="all").reset_index(drop=True)
    required = ["Tgl Order", "Tgl PPD", "OTR", "Object", "No Kontrak"]
    miss_req = [c for c in required if c not in df.columns]
    if miss_req:
        raise ValueError("Kolom wajib tidak ditemukan: " + ", ".join(miss_req))
    optional = ["Financing Type", "Sales Through", "DLC", "Internal Sales Force", "CFO", "Inisiator", "Model",
                "Jenis Produk", "Status", "Kode dan Nama Dealer", "Pokok Hutang", "Total Piutang", "Ext Sales 1",
                "Marketing Proposal", "Bunga"]
    missing_opt = [c for c in optional if c not in df.columns]
    for c in missing_opt:
        df[c] = pd.NA
    n_raw = len(df)
    dq = {"n_raw": n_raw, "header_row": hdr + 1, "missing_optional_cols": missing_opt}

    # --- tipe data ---
    for c in df.columns:
        if c in NUM_COLS:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        elif not pd.api.types.is_datetime64_any_dtype(df[c]) and not pd.api.types.is_numeric_dtype(df[c]):
            df[c] = df[c].astype("string").str.strip().replace("", pd.NA)
    n_before = {c: int(df[c].isna().sum()) for c in ("Tgl Order", "Tgl PPD")}
    for c in ("Tgl Order", "Tgl PPD"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    dq["invalid_dates_raw_null"] = n_before
    dq["invalid_dates_after_parse"] = {c: int(df[c].isna().sum()) for c in ("Tgl Order", "Tgl PPD")}

    # --- missing value kolom dimensi -> label eksplisit ---
    miss = df.isna().sum()
    dq["missing"] = (pd.DataFrame({"Kolom": miss.index, "Kosong": miss.values,
                                   "% Kosong": (miss.values / max(n_raw, 1))})
                     .query("Kosong > 0").sort_values("Kosong", ascending=False).reset_index(drop=True))
    dq["empty_cols"] = [c for c in df.columns if df[c].isna().all()]
    for c in DIM_COLS:
        if c in df.columns:
            df[c] = df[c].fillna(UNKNOWN)
    if "No Kontrak" in df.columns:
        df["No Kontrak"] = df["No Kontrak"].astype("string")

    # --- status, cancel, duplikat ---
    st_up = df["Status"].astype("string").str.upper()
    df["is_cancel"] = st_up.str.contains("CANCEL", na=False)
    cancel_contracts = set(df.loc[df["is_cancel"], "No Kontrak"])
    df["is_reversed"] = df["No Kontrak"].isin(cancel_contracts) & ~df["is_cancel"]
    df["is_dup_extra"] = df.duplicated(["No Kontrak", "Status"], keep="first")
    df["counted_net"] = ~df["is_cancel"] & ~df["is_reversed"] & ~df["is_dup_extra"]
    df["counted_gross"] = ~df["is_cancel"] & ~df["is_dup_extra"]
    dq["dup_contract_rows"] = df[df["No Kontrak"].duplicated(keep=False)].sort_values("No Kontrak")
    dq["n_cancel"] = int(df["is_cancel"].sum())
    dq["n_reversed"] = int(df["is_reversed"].sum())
    dq["n_dup_extra"] = int(df["is_dup_extra"].sum())

    # --- tanggal & TAT ---
    df["tat_days"] = (df["Tgl PPD"] - df["Tgl Order"]).dt.days
    df["ppd_date"] = df["Tgl PPD"].dt.normalize()
    dq["negative_tat"] = int((df["tat_days"] < 0).sum())
    df.loc[df["tat_days"] < 0, "tat_days"] = np.nan  # TAT negatif tidak valid
    if period is None:
        mo = df["Tgl PPD"].dropna()
        period = (mo.min().replace(day=1), mo.max()) if len(mo) else (None, None)
    dq["period"] = period
    out_p = pd.Series(False, index=df.index)
    if period[0] is not None:
        out_p = (df["Tgl PPD"] < period[0]) | (df["Tgl PPD"] > period[1] + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
    out_p &= df["Tgl PPD"].notna()
    df["ppd_out_of_period"] = out_p
    dq["out_of_period"] = int(out_p.sum())
    day = df["Tgl PPD"].dt.day
    df["period_bucket"] = np.select(
        [day.between(1, 7).fillna(False).to_numpy(dtype=bool), day.between(8, 14).fillna(False).to_numpy(dtype=bool), day.between(15, 21).fillna(False).to_numpy(dtype=bool), (day >= 22).fillna(False).to_numpy(dtype=bool)],
        ["1-7", "8-14", "15-21", "22-akhir"], default="Tanggal tidak valid")

    # --- nilai finansial ---
    dq["missing_otr"] = int(df["OTR"].isna().sum())
    dq["nonpositive_otr"] = int((df["OTR"] <= 0).sum())

    # --- produk bersih & klasifikasi ---
    df["product"] = df["Jenis Produk"].astype("string").str.replace(r"^\w+\s*-\s*", "", regex=True)
    df["Financing Type"] = df["Financing Type"].astype("string").str.title()
    df = classify(df)
    dq["unclassified"] = int((df["portfolio"] == P_OTHER).sum())
    dq["unclassified_source"] = int((df["business_source"] == S_OTHER).sum())
    return df, dq


# ---- nama fungsi sesuai spesifikasi ----
def load_data(source):
    """Baca file PPD, bersihkan, klasifikasi, validasi. Return (df, dq)."""
    return load_and_prepare(source)


def calculate_tat(df: pd.DataFrame) -> pd.Series:
    """TAT = Tgl PPD - Tgl Order (hari). TAT negatif/tanggal tidak valid -> NaN."""
    t = (df["Tgl PPD"] - df["Tgl Order"]).dt.days
    return t.where(t >= 0)


def restrict_to_car(df: pd.DataFrame, dq: dict):
    """Batasi data ke New Car + Used Car (4W) dan hitung ulang ringkasan kualitas data untuk cakupan itu."""
    keep = df["portfolio"].isin(CAR_PORTFOLIOS)
    car = df[keep].reset_index(drop=True)
    d = dict(dq)
    d["n_excluded_non_car"] = int((~keep).sum())
    d["n_raw"] = len(car)
    d["n_cancel"] = int(car["is_cancel"].sum())
    d["n_reversed"] = int(car["is_reversed"].sum())
    d["n_dup_extra"] = int(car["is_dup_extra"].sum())
    d["invalid_dates_after_parse"] = {c: int(car[c].isna().sum()) for c in ("Tgl Order", "Tgl PPD")}
    d["negative_tat"] = int(((car["Tgl PPD"] - car["Tgl Order"]).dt.days < 0).sum())
    d["out_of_period"] = int(car["ppd_out_of_period"].sum())
    d["missing_otr"] = int(car["OTR"].isna().sum())
    d["dup_contract_rows"] = car[car["No Kontrak"].duplicated(keep=False)].sort_values("No Kontrak")
    raw_cols = list(car.columns[:car.columns.get_loc("is_cancel")])
    empty = (car[raw_cols].isna() | (car[raw_cols].astype("string") == UNKNOWN)).sum()
    d["missing"] = (pd.DataFrame({"Kolom": empty.index, "Kosong": empty.values,
                                  "% Kosong": empty.values / max(len(car), 1)})
                    .query("Kosong > 0").sort_values("Kosong", ascending=False).reset_index(drop=True))
    d["empty_cols"] = [c for c in raw_cols if car[c].isna().all()]
    d["unclassified"] = 0
    d["unclassified_source"] = int((car["business_source"] == S_OTHER).sum())
    return car, d
