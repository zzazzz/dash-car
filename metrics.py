"""Perhitungan metrik. Semua fungsi menerima dataframe yang sudah difilter."""
import numpy as np
import pandas as pd
import streamlit as st

from business_mapping import CAR_PORTFOLIOS as CORE_PORTFOLIOS, P_OTHER, S_OTHER, UNCL_LABEL


def totals(p: pd.DataFrame) -> dict:
    n = len(p)
    otr = p["OTR"].sum()
    otr_n = p["OTR"].count()
    tat = p["tat_days"].dropna()
    return {
        "ppd": n,
        "otr": otr,
        "pokok": p["Pokok Hutang"].sum(),
        "bunga": p["Bunga"].sum(),
        # ticket size = total Pokok Hutang / jumlah PPD
        "avg_ticket": p["Pokok Hutang"].sum() / n if n else np.nan,
        "median_ticket": p["Pokok Hutang"].median() if p["Pokok Hutang"].count() else np.nan,
        "avg_tat": tat.mean() if len(tat) else np.nan,
        "median_tat": tat.median() if len(tat) else np.nan,
        "same_day": int((tat == 0).sum()),
        "same_day_pct": (tat == 0).mean() if len(tat) else np.nan,
        "tat_le1_pct": (tat <= 1).mean() if len(tat) else np.nan,
        "tat_le3_pct": (tat <= 3).mean() if len(tat) else np.nan,
        "tat_max": tat.max() if len(tat) else np.nan,
        "tat_n": len(tat),
    }


@st.cache_data(show_spinner=False)
def summarize(p: pd.DataFrame, by, total_ppd=None, total_otr=None) -> pd.DataFrame:
    """Ringkasan PPD, OTR, Pokok Hutang, Avg Ticket, TAT dan kontribusi per dimensi."""
    by = [by] if isinstance(by, str) else list(by)
    if p.empty:
        return pd.DataFrame(columns=by + ["PPD", "OTR", "Pokok Hutang", "Avg Ticket", "Avg TAT", "PPD %", "OTR %"])
    g = p.groupby(by, dropna=False).agg(
        PPD=("OTR", "size"), OTR=("OTR", "sum"), OTR_n=("OTR", "count"),
        **{"Pokok Hutang": ("Pokok Hutang", "sum")}, **{"Avg TAT": ("tat_days", "mean")},
        **{"Median TAT": ("tat_days", "median")},
    ).reset_index()
    g["Avg Ticket"] = g["Pokok Hutang"] / g["PPD"].replace(0, np.nan)   # total Pokok Hutang / jumlah PPD
    tp = total_ppd if total_ppd else g["PPD"].sum()
    to = total_otr if total_otr else g["OTR"].sum()
    g["PPD %"] = g["PPD"] / tp if tp else np.nan
    g["OTR %"] = g["OTR"] / to if to else np.nan
    g = g.drop(columns="OTR_n").sort_values("PPD", ascending=False).reset_index(drop=True)
    return g[by + ["PPD", "PPD %", "OTR", "OTR %", "Avg Ticket", "Pokok Hutang", "Avg TAT", "Median TAT"]]


def rank_for_metric(s: pd.DataFrame, metric: str, top_n: int, min_n: int = 2) -> pd.DataFrame:
    """Top-N menurut metrik. Untuk Avg Ticket, abaikan grup < min_n kontrak bila grup cukup banyak."""
    t = s
    if metric == "Avg Ticket":
        big = s[s["PPD"] >= min_n]
        if len(big) >= 3:
            t = big
    return t.sort_values(metric, ascending=False).head(top_n)


def daily_series(p: pd.DataFrame, start, end) -> pd.DataFrame:
    idx = pd.date_range(start, end, freq="D")
    d = p.dropna(subset=["ppd_date"]).groupby("ppd_date").agg(PPD=("OTR", "size"), OTR=("OTR", "sum"))
    return d.reindex(idx, fill_value=0).rename_axis("Tanggal").reset_index()


def daily_by_segment(p: pd.DataFrame, col: str = "portfolio") -> pd.DataFrame:
    return (p.dropna(subset=["ppd_date"]).groupby(["ppd_date", col])
            .agg(PPD=("OTR", "size"), OTR=("OTR", "sum")).reset_index())


PERIOD_DAYS = {"1-7": 7, "8-14": 7, "15-21": 7, "22-akhir": 9}


def period_summary(p: pd.DataFrame) -> pd.DataFrame:
    s = summarize(p, "period_bucket")
    order = list(PERIOD_DAYS) + ["Tanggal tidak valid"]
    s["_o"] = s["period_bucket"].map({k: i for i, k in enumerate(order)})
    s = s.sort_values("_o").drop(columns="_o").reset_index(drop=True)
    s["Hari"] = s["period_bucket"].map(PERIOD_DAYS)
    s["PPD / hari"] = s["PPD"] / s["Hari"]
    s["OTR / hari"] = s["OTR"] / s["Hari"]
    return s


def classification_check(p: pd.DataFrame) -> dict:
    """Coverage klasifikasi portfolio (parent), sub-portfolio (child) dan source."""
    total = len(p)
    unc_p = int((p["portfolio"] == P_OTHER).sum())
    unc_s = int(p["sub_unclassified"].sum())
    unc_src = int((p["business_source"] == S_OTHER).sum())
    cov = lambda u: (total - u) / total if total else np.nan  # noqa: E731
    return {"total": total, "unclassified_portfolio": unc_p, "unclassified_sub": unc_s, "unclassified_source": unc_src,
            "cov_portfolio": cov(unc_p), "cov_sub": cov(unc_s), "cov_source": cov(unc_src),
            "core5": int(p["portfolio"].isin(CORE_PORTFOLIOS).sum())}


def calculate_metrics(p: pd.DataFrame) -> dict:
    return totals(p)


def _pair(df, mask_parent, mask_child):
    a, b = df[mask_parent], df[mask_child]
    return len(a), len(b), a["OTR"].sum(), b["OTR"].sum()


def validate_hierarchy(df: pd.DataFrame) -> pd.DataFrame:
    """Validasi parent = sum(child). Parent dihitung dari field Object (independen dari klasifikasi child).
    Residual TIDAK dipaksa balance dan diberi label 'Detail belum tersedia'."""
    o = df["Object"].astype(str).str.upper()
    pt = df["portfolio"]
    bp = df["business_portfolio"]
    specs = [
        ("4W", "Object MOBIL BARU/BEKAS", "New Car + Used Car", o.isin(["MOBIL BARU", "MOBIL BEKAS"]), pt.isin(["New Car", "Used Car"])),
        ("NCAR", "Object MOBIL BARU", "NC1 + NC2 + NC3", o.eq("MOBIL BARU"), bp.isin(["NC1", "NC2", "NC3"])),
    ]
    rows = []
    for name, basis, child, mp, mc in specs:
        pp, cp, po, co = _pair(df, mp, mc)
        res = pp - cp
        rows.append({"Parent": name, "Basis parent": basis, "Child": child, "Parent PPD": pp, "Child PPD": cp,
                     "Residual PPD": res, "Parent OTR": po, "Child OTR": co, "Residual OTR": po - co,
                     "Coverage %": cp / pp if pp else np.nan,
                     "Status": "Lengkap" if res == 0 else f"Parsial - {UNCL_LABEL}"})
    return pd.DataFrame(rows)


def quadrant(seg: pd.DataFrame) -> pd.DataFrame:
    """Label kuadran Volume vs Value terhadap rata-rata antar segmen."""
    s = seg.copy()
    if s.empty:
        s["Kuadran"] = []
        return s
    mv, mo = s["PPD"].mean(), s["OTR"].mean()
    hv, ho = s["PPD"] >= mv, s["OTR"] >= mo
    s["Kuadran"] = np.select(
        [(hv & ho).to_numpy(dtype=bool), (hv & ~ho).to_numpy(dtype=bool), (~hv & ho).to_numpy(dtype=bool)],
        ["High volume / High value", "High volume / Low value", "Low volume / High value"],
        default="Low volume / Low value")
    return s
