"""Formatter, konstanta metrik dan komponen UI kecil."""
import html

import numpy as np
import pandas as pd
import streamlit as st

METRICS = ("PPD", "OTR", "Avg Ticket")


def _swap(s: str) -> str:
    """Ubah format angka US (1,234.5) menjadi Indonesia (1.234,5)."""
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def _na(x) -> bool:
    return x is None or (isinstance(x, float) and np.isnan(x)) or x is pd.NA


def fmt_int(x) -> str:
    return "-" if _na(x) else _swap(f"{x:,.0f}")


def fmt_pct(x, d: int = 1) -> str:
    return "-" if _na(x) else _swap(f"{x * 100:.{d}f}") + "%"


def fmt_days(x) -> str:
    return "-" if _na(x) else _swap(f"{x:.1f}") + " hari"


def fmt_rp(x) -> str:
    """Rp43,32 M | Rp51,08 Jt | Rp12.500"""
    if _na(x):
        return "-"
    sign = "-" if x < 0 else ""
    a = abs(float(x))
    if a >= 1e12:
        v, u = a / 1e12, " T"
    elif a >= 1e9:
        v, u = a / 1e9, " M"
    elif a >= 1e6:
        v, u = a / 1e6, " Jt"
    else:
        return f"{sign}Rp{_swap(f'{a:,.0f}')}"
    return f"{sign}Rp{_swap(f'{v:,.2f}')}{u}"


def metric_fmt(metric: str):
    return fmt_int if metric == "PPD" else fmt_rp


def scale_metric(values: pd.Series, metric: str):
    """Skala nilai agar sumbu grafik mudah dibaca. Return (nilai, judul sumbu)."""
    if metric == "PPD":
        return values, "PPD (kontrak)"
    if metric == "OTR":
        return values / 1e9, "OTR (Rp miliar)"
    return values / 1e6, "Average Ticket (Rp juta)"


CSS = """
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 2rem;}
.kpi {background:#FFFFFF; border:1px solid #E1E6EC; border-radius:8px; padding:12px 14px; height:100%;}
.kpi-l {font-size:0.76rem; color:#5B6B7B; text-transform:uppercase; letter-spacing:.03em;}
.kpi-v {font-size:1.45rem; font-weight:650; color:#1F3A5F; line-height:1.25; margin-top:2px;}
.kpi-s {font-size:0.76rem; color:#7A8794; margin-top:2px;}
.insight {background:#F3F6FA; border-left:4px solid #1F3A5F; border-radius:4px; padding:10px 14px; margin:8px 0 14px 0;}
.insight-t {font-size:0.78rem; font-weight:650; color:#1F3A5F; text-transform:uppercase; letter-spacing:.04em; margin-bottom:4px;}
.insight li {margin-bottom:3px; color:#243447; font-size:0.93rem;}
.warnbox {background:#FFF7EC; border-left:4px solid #C8553D; border-radius:4px; padding:10px 14px; margin:8px 0;}
h4 {margin-top: 1.2rem !important;}
</style>
"""


def kpi_cards(items):
    """items: list of (label, value, sub)."""
    cols = st.columns(len(items))
    for col, (label, value, sub) in zip(cols, items):
        col.markdown(
            f'<div class="kpi"><div class="kpi-l">{html.escape(str(label))}</div>'
            f'<div class="kpi-v">{html.escape(str(value))}</div>'
            f'<div class="kpi-s">{html.escape(str(sub)) if sub else "&nbsp;"}</div></div>',
            unsafe_allow_html=True,
        )


def insight_box(lines):
    lines = [l for l in lines if l]
    if not lines:
        return
    li = "".join(f"<li>{html.escape(l)}</li>" for l in lines)
    st.markdown(
        f'<div class="insight"><div class="insight-t">Key Business Insight</div><ul style="margin:0;padding-left:18px">{li}</ul></div>',
        unsafe_allow_html=True,
    )


def warn_box(text: str):
    st.markdown(f'<div class="warnbox">{html.escape(text)}</div>', unsafe_allow_html=True)


def display_table(df: pd.DataFrame) -> pd.DataFrame:
    """Format tabel ringkasan (hasil metrics.summarize) untuk ditampilkan."""
    out = df.copy()
    for c in out.columns:
        if c in ("PPD",):
            out[c] = out[c].map(fmt_int)
        elif c in ("OTR", "Pokok Hutang", "Avg Ticket"):
            out[c] = out[c].map(fmt_rp)
        elif c.endswith("%"):
            out[c] = out[c].map(fmt_pct)
        elif c in ("Avg TAT", "Median TAT"):
            out[c] = out[c].map(fmt_days)
    return out


# alias nama fungsi sesuai spesifikasi
def format_currency(x) -> str:
    return fmt_rp(x)


def format_percentage(x, d: int = 1) -> str:
    return fmt_pct(x, d)
