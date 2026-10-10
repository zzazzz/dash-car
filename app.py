"""Car (4W) Business Performance.

Jalankan:  streamlit run app.py
Cakupan: hanya 4W = New Car (NC1/NC2/NC3) dan Used Car. MCY dan MPL dikeluarkan dari data.
"""
import os

import numpy as np
import pandas as pd
import streamlit as st

import charts as ch
import insights as ins
from business_mapping import (CAR_PORTFOLIOS, NC1_BRANDS, NC2_BRANDS, NC3_BRANDS, NC_MP_CODE_REF, NC_ORDER,
                              P_NC, P_UC, S_DEALER, SOURCE_ORDER, SOURCE_RULES, UNCL_LABEL)
from data_loader import load_data, restrict_to_car
from metrics import (calculate_metrics, classification_check, daily_by_segment, daily_series, period_summary,
                     quadrant, rank_for_metric, summarize, validate_hierarchy)
from utils import (CSS, METRICS, display_table, fmt_days, fmt_int, fmt_pct, fmt_rp, insight_box, kpi_cards, warn_box)

st.set_page_config(page_title="Car (4W) Performance", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "ppd september(1).xls")
PAGES = ["Executive Summary", "Portfolio Overview", "New Car", "Used Car", "Dealer & Channel", "Sales Force",
         "Production Trend", "Operational / TAT", "Data Quality", "Data Detail"]
BASIS = {"Net PPD (tanpa kontrak yang di-cancel)": "counted_net",
         "Gross PPD (Status = PPD)": "counted_gross",
         "Semua record (termasuk CANCEL PPD)": "all"}

# ------------------------------------------------------------------ data
with st.sidebar.expander("Sumber data", expanded=False):
    up = st.file_uploader("Ganti file PPD (.xls / .xlsx)", type=["xls", "xlsx"])
if up is not None:
    source = up.getvalue()
elif os.path.exists(DATA_PATH):
    source = DATA_PATH
else:
    st.error("File data tidak ditemukan di folder data/. Letakkan 'ppd september(1).xls' di sana atau unggah lewat sidebar.")
    st.stop()
try:
    df_all, dq = load_data(source)
    df_all, dq = restrict_to_car(df_all, dq)
except Exception as e:  # noqa: BLE001
    st.error(f"Gagal membaca data: {e}")
    st.stop()
if df_all.empty:
    st.error("Tidak ada kontrak New Car / Used Car (Object MOBIL BARU / MOBIL BEKAS) pada file ini.")
    st.stop()

# ------------------------------------------------------------------ sidebar
st.sidebar.title("Car (4W)")
page = st.sidebar.radio("Navigasi", PAGES, label_visibility="collapsed")
st.sidebar.markdown("---")
basis_label = st.sidebar.radio("Basis perhitungan", list(BASIS), index=0,
                               help="Net: kontrak yang punya pasangan CANCEL PPD dikeluarkan dari produksi.")

FILTERS = {  # key -> (label, kolom)
    "f_port": ("Business Portfolio", "portfolio"), "f_sub": ("Sub-Portfolio (NC1/NC2/NC3, Used Car)", "business_portfolio"),
    "f_src": ("Business Source", "business_source"),
    "f_prod": ("Product", "product"), "f_obj": ("Object", "Object"), "f_brand": ("Brand", "brand"),
    "f_model": ("Model", "model_family"), "f_dlc": ("Dealer / DLC", "DLC"), "f_st": ("Sales Through", "Sales Through"),
    "f_fin": ("Financing Type", "Financing Type"), "f_isf": ("Internal Sales Force", "Internal Sales Force"),
    "f_cfo": ("CFO", "CFO"), "f_ini": ("Inisiator", "inisiator_name"),
}


def reset_filters():
    for k in list(FILTERS) + ["f_date"]:
        st.session_state.pop(k, None)


st.sidebar.markdown("### Filter")
st.sidebar.button("Reset Filter", on_click=reset_filters, width="stretch")
dmin, dmax = df_all["Tgl PPD"].min().date(), df_all["Tgl PPD"].max().date()
date_rng = st.sidebar.date_input("Tanggal PPD", value=(dmin, dmax), min_value=dmin, max_value=dmax, key="f_date")


def _opts(col):
    vals = df_all[col].dropna().unique().tolist()
    if col == "portfolio":
        return [s for s in CAR_PORTFOLIOS if s in vals]
    if col == "business_source":
        return [s for s in SOURCE_ORDER if s in vals]
    if col == "business_portfolio":
        order = ["NC1", "NC2", "NC3", "Used Car"]
        return [s for s in order if s in vals] + sorted(s for s in vals if s not in order)
    return sorted(vals, key=str)


def _ms(key):
    label, col = FILTERS[key]
    return st.multiselect(label, _opts(col), key=key, placeholder="Semua")


with st.sidebar.expander("Portfolio", expanded=True):
    _ms("f_port"); _ms("f_sub")  # noqa: E702
with st.sidebar.expander("Source"):
    _ms("f_src")
with st.sidebar.expander("Lainnya"):
    for k in ("f_prod", "f_obj", "f_brand", "f_model", "f_dlc", "f_st", "f_fin"):
        _ms(k)
with st.sidebar.expander("Organization"):
    for k in ("f_isf", "f_cfo", "f_ini"):
        _ms(k)

f = df_all
if isinstance(date_rng, (tuple, list)) and len(date_rng) == 2:
    a, b = pd.Timestamp(date_rng[0]), pd.Timestamp(date_rng[1])
    f = f[(f["Tgl PPD"] >= a) & (f["Tgl PPD"] < b + pd.Timedelta(days=1))]
for k, (label, col) in FILTERS.items():
    sel = st.session_state.get(k)
    if sel:
        f = f[f[col].isin(sel)]
mode = BASIS[basis_label]
p = f if mode == "all" else f[f[mode]]
n_cancel = int(f["is_cancel"].sum())
cancel_otr = f.loc[f["is_cancel"], "OTR"].sum()
TOT_PPD, TOT_OTR = len(p), p["OTR"].sum()
TOT_POKOK = p["Pokok Hutang"].sum()
PERIOD = dq["period"]
RANGE = (pd.Timestamp(date_rng[0]), pd.Timestamp(date_rng[1])) if isinstance(date_rng, (tuple, list)) and len(date_rng) == 2 else (PERIOD[0], PERIOD[1])


def PF(name):
    return p[p["portfolio"] == name]


# ------------------------------------------------------------------ helper UI
def head(title, question):
    st.title(title)
    st.caption(question)
    st.caption(f"Periode {PERIOD[0]:%d %b %Y} - {PERIOD[1]:%d %b %Y} | Basis: {basis_label} | {fmt_int(TOT_PPD)} kontrak dalam filter aktif")


def sub(title, note=None):
    st.markdown(f"#### {title}")
    if note:
        st.caption(note)


def no_data(df, msg="Tidak ada data untuk filter yang dipilih."):
    if df is None or len(df) == 0:
        st.info(msg)
        return True
    return False


def with_total(s, col, df, label="Total"):
    """Tambah baris Total di bawah tabel ringkasan (s = hasil summarize, df = data sumbernya)."""
    if s.empty:
        return s
    ppd, pokok = s["PPD"].sum(), s["Pokok Hutang"].sum()
    tot = {col: label, "PPD": ppd, "PPD %": s["PPD %"].sum(), "OTR": s["OTR"].sum(), "OTR %": s["OTR %"].sum(),
           "Avg Ticket": pokok / ppd if ppd else np.nan, "Pokok Hutang": pokok,
           "Avg TAT": df["tat_days"].mean(), "Median TAT": df["tat_days"].median()}
    return pd.concat([s.astype({col: "object"}), pd.DataFrame([tot])], ignore_index=True)


def panel(df, col, title, key, default_top=10, metrics=METRICS, table=True, note=None, total_ppd=None, total_otr=None):
    """Ranking horizontal dengan selector metrik dan Top-N."""
    sub(title, note)
    s = summarize(df, col, total_ppd or len(df), total_otr or df["OTR"].sum())
    if s.empty:
        st.info("Tidak ada data.")
        return
    c1, c2 = st.columns(2)
    m = c1.selectbox("Metrik", metrics, key=f"{key}_m")
    n = c2.selectbox("Tampilkan", [5, 10, 20], index=[5, 10, 20].index(default_top), key=f"{key}_n")
    t = rank_for_metric(s, m, n)
    st.plotly_chart(ch.rank_bar(t, col, m), width="stretch", key=f"{key}_c")
    if m == "Avg Ticket":
        st.caption("Ranking Avg Ticket mengabaikan grup dengan < 2 kontrak bila grup lain cukup banyak.")
    if table:
        with st.expander("Tabel detail"):
            st.dataframe(display_table(with_total(s, col, df).drop(columns=["Median TAT"])), hide_index=True, width="stretch")


def kpis(df, label, parent=None, parent_name="total"):
    t = calculate_metrics(df)
    pt = calculate_metrics(parent) if parent is not None else {"ppd": TOT_PPD, "otr": TOT_OTR, "pokok": TOT_POKOK}
    kpi_cards([(f"{label} PPD", fmt_int(t["ppd"]), f"{fmt_pct(t['ppd'] / pt['ppd']) if pt['ppd'] else '-'} dari {parent_name}"),
               (f"{label} OTR", fmt_rp(t["otr"]), f"{fmt_pct(t['otr'] / pt['otr']) if pt['otr'] else '-'} dari {parent_name}"),
               (f"{label} Pokok Hutang", fmt_rp(t["pokok"]), f"{fmt_pct(t['pokok'] / pt['pokok']) if pt['pokok'] else '-'} dari {parent_name}"),
               (f"{label} Bunga", fmt_rp(t["bunga"]), f"{fmt_pct(t['bunga'] / t['pokok']) if t['pokok'] else '-'} dari Pokok Hutang"),
               ("Average Ticket", fmt_rp(t["avg_ticket"]), f"Median {fmt_rp(t['median_ticket'])}"),
               ("Rata-rata TAT", fmt_days(t["avg_tat"]), f"Same-day {fmt_pct(t['same_day_pct'])}")])


def compare_panel(a, b, name_a, name_b, key, colors=None):
    rows = []
    for nm, d in ((name_a, a), (name_b, b)):
        t = calculate_metrics(d)
        rows.append({"Kelompok": nm, "PPD": t["ppd"], "OTR": t["otr"], "Avg Ticket": t["avg_ticket"],
                     "PPD %": t["ppd"] / TOT_PPD if TOT_PPD else np.nan, "OTR %": t["otr"] / TOT_OTR if TOT_OTR else np.nan})
    s = pd.DataFrame(rows)
    m = st.selectbox("Metrik perbandingan", METRICS, key=f"{key}_cm")
    c1, c2 = st.columns(2)
    c1.plotly_chart(ch.col_bar(s, "Kelompok", m, colors=colors or {name_a: ch.PRIMARY, name_b: ch.ACCENT}), width="stretch", key=f"{key}_cc")
    c2.dataframe(display_table(s), hide_index=True, width="stretch")
    insight_box(ins.compare_two(a, b, name_a, name_b))


def child_compare(df, cat, order, key, title, colors=None):
    """Perbandingan child (mis. NC1 vs NC2 vs NC3) dengan selector metrik + tabel."""
    s = summarize(df, cat, TOT_PPD, TOT_OTR)
    s[cat] = s[cat].astype(str)
    s["_o"] = s[cat].map({k: i for i, k in enumerate(order)}).fillna(99)
    s = s.sort_values("_o").drop(columns="_o")
    m = st.selectbox("Metrik", METRICS, key=f"{key}_m")
    st.plotly_chart(ch.col_bar(s, cat, m, title=title, colors=colors or ch.SEG_COLORS), width="stretch", key=f"{key}_c")
    show = display_table(with_total(s, cat, df).drop(columns=["Median TAT"]))
    st.dataframe(show.replace({cat: {k: UNCL_LABEL for k in s[cat] if str(k).startswith("Unclassified")}}),
                 hide_index=True, width="stretch")
    return s


def breakdown(df, key, items, cols=2):
    """items: list of (kolom, judul, default_top). Ditata dalam grid."""
    for i in range(0, len(items), cols):
        cs = st.columns(cols)
        for c, (col, title, top) in zip(cs, items[i:i + cols]):
            with c:
                panel(df, col, title, f"{key}_{col}", default_top=top)


# ================================================================== PAGES
def page_exec():
    head("Executive Summary", "Apa portfolio mobil terbesar Cabang Solo (New Car vs Used Car), dan mana volume driver vs value driver?")
    if no_data(p):
        return
    t = calculate_metrics(p)
    kpi_cards([("Total PPD", fmt_int(t["ppd"]), "kontrak"), ("Total OTR", fmt_rp(t["otr"]), ""),
               ("Total Pokok Hutang", fmt_rp(t["pokok"]), f"{fmt_pct(t['pokok'] / t['otr']) if t['otr'] else '-'} dari OTR"),
               ("Total Bunga", fmt_rp(t["bunga"]), f"{fmt_pct(t['bunga'] / t['pokok']) if t['pokok'] else '-'} dari Pokok Hutang"),
               ("Average Ticket", fmt_rp(t["avg_ticket"]), "Pokok Hutang / PPD")])
    st.write("")
    kpi_cards([("Median Ticket", fmt_rp(t["median_ticket"]), "Pokok Hutang per kontrak"),
               ("Average TAT", fmt_days(t["avg_tat"]), f"Median {fmt_days(t['median_tat'])}"),
               ("Same-Day PPD", fmt_int(t["same_day"]), f"{fmt_pct(t['same_day_pct'])} dari kontrak"),
               ("Cancel PPD", fmt_int(n_cancel), f"OTR {fmt_rp(cancel_otr)} (tidak dihitung pada basis Net/Gross)")])
    insight_box(ins.executive(p))
    sub("Portfolio Contribution", "Cakupan 4W: New Car dan Used Car.")
    seg = summarize(p, "portfolio", TOT_PPD, TOT_OTR)
    seg["_o"] = seg["portfolio"].map({s: i for i, s in enumerate(CAR_PORTFOLIOS)})
    seg = seg.sort_values("_o").drop(columns="_o")
    tbl = seg[["portfolio", "PPD", "PPD %", "OTR", "OTR %", "Avg Ticket"]].copy()
    tbl = tbl.rename(columns={"portfolio": "Portfolio"})
    tot = pd.DataFrame([{"Portfolio": "Total", "PPD": seg["PPD"].sum(), "PPD %": seg["PPD %"].sum(), "OTR": seg["OTR"].sum(),
                         "OTR %": seg["OTR %"].sum(), "Avg Ticket": t["avg_ticket"]}])
    st.dataframe(display_table(pd.concat([tbl, tot], ignore_index=True)), hide_index=True, width="stretch")


def page_portfolio():
    head("Portfolio Overview", "Bisnis mobil Solo ditopang New Car atau Used Car? Mana volume driver dan value driver?")
    if no_data(p):
        return
    seg = summarize(p, "portfolio", TOT_PPD, TOT_OTR)
    seg["_o"] = seg["portfolio"].map({s: i for i, s in enumerate(CAR_PORTFOLIOS)})
    seg = seg.sort_values("_o").drop(columns="_o")
    core = seg[seg["portfolio"].isin(CAR_PORTFOLIOS)]
    insight_box(ins.portfolio_overview(p))
    c1, c2 = st.columns(2)
    c1.plotly_chart(ch.volume_value_bars(core, "PPD", "Portfolio by PPD"), width="stretch", key="po_v")
    c2.plotly_chart(ch.volume_value_bars(core, "OTR", "Portfolio by OTR"), width="stretch", key="po_o")
    sub("Volume vs Value Matrix", "X = PPD, Y = OTR, ukuran bubble = Average Ticket. Garis putus = rata-rata antar portfolio.")
    st.plotly_chart(ch.scatter_matrix(core), width="stretch", key="po_sc")
    q = quadrant(core)[["portfolio", "PPD", "OTR", "Avg Ticket", "Kuadran"]].rename(columns={"portfolio": "Portfolio"})
    st.dataframe(display_table(q), hide_index=True, width="stretch")

    sub("Hierarki bisnis", "Parent dan child ditampilkan berjenjang; angka child tidak dijumlahkan lagi dengan parent.")
    nb = " "
    rows = [("4W (Car)", p)]
    for pf in CAR_PORTFOLIOS:
        dpf = p[p["portfolio"] == pf]
        if dpf.empty:
            continue
        rows.append((nb * 4 + "- " + pf, dpf))
        for bp in sorted(dpf["business_portfolio"].unique(), key=str):
            if bp == pf:
                continue
            lab = UNCL_LABEL + f" ({pf})" if str(bp).startswith("Unclassified") else bp
            rows.append((nb * 8 + "- " + lab, dpf[dpf["business_portfolio"] == bp]))
    tr = []
    for lab, d in rows:
        tt = calculate_metrics(d)
        tr.append({"Level": lab, "PPD": tt["ppd"], "PPD %": tt["ppd"] / TOT_PPD if TOT_PPD else np.nan,
                   "OTR": tt["otr"], "OTR %": tt["otr"] / TOT_OTR if TOT_OTR else np.nan, "Avg Ticket": tt["avg_ticket"]})
    st.dataframe(display_table(pd.DataFrame(tr)), hide_index=True, width="stretch")

    sub("Validasi hierarki", "Parent dihitung dari field Object; child dari klasifikasi. Selisih tidak dipaksa balance.")
    hv = validate_hierarchy(p)
    show_hierarchy(hv)


def show_hierarchy(hv):
    t = hv.copy()
    for c in ("Parent PPD", "Child PPD", "Residual PPD"):
        t[c] = t[c].map(fmt_int)
    for c in ("Parent OTR", "Child OTR", "Residual OTR"):
        t[c] = t[c].map(fmt_rp)
    t["Coverage %"] = hv["Coverage %"].map(fmt_pct)
    t = t.rename(columns={"Residual PPD": f"Residual PPD ({UNCL_LABEL})", "Residual OTR": f"Residual OTR ({UNCL_LABEL})"})
    st.dataframe(t, hide_index=True, width="stretch")
    bad = hv[hv["Residual PPD"] != 0]
    if len(bad):
        warn_box("Parent tidak sama dengan jumlah child pada: " + ", ".join(bad["Parent"]) + f". Residual diberi label '{UNCL_LABEL}' dan tidak dijadikan kategori bisnis baru.")


def page_new_car():
    head("New Car (NCAR)", "")
    nc = PF(P_NC)
    if no_data(nc, "Tidak ada kontrak New Car pada filter ini."):
        return
    g = lambda n: int(s.loc[s["business_portfolio"] == n, "PPD"].sum())  # noqa: E731
    t = calculate_metrics(nc)
    kpi_cards([("Total New Car PPD", fmt_int(t["ppd"]), f"{fmt_pct(t['ppd'] / TOT_PPD)} dari total"),
               ("Total New Car OTR", fmt_rp(t["otr"]), f"{fmt_pct(t['otr'] / TOT_OTR)} dari total"),
               ("Total New Car Pokok Hutang", fmt_rp(t["pokok"]), f"{fmt_pct(t['pokok'] / TOT_POKOK) if TOT_POKOK else '-'} dari total"),
               ("Total New Car Bunga", fmt_rp(t["bunga"]), f"{fmt_pct(t['bunga'] / t['pokok']) if t['pokok'] else '-'} dari Pokok Hutang"),
               ("Average Ticket", fmt_rp(t["avg_ticket"]), "Pokok Hutang / PPD")])
    insight_box(ins.child_group(nc[nc["business_portfolio"].isin(["NC1", "NC2", "NC3"])], "business_portfolio", "New Car",
                                [("brand", "Brand"), ("DLC", "Dealer")]))
    unc = nc[nc["sub_unclassified"]]
    if len(unc):
        warn_box(f"{len(unc)} kontrak New Car ({', '.join(sorted(unc['brand'].astype(str).unique()))}) belum masuk NC1/NC2/NC3 karena brand tidak ada dalam definisi NC. Dicatat sebagai '{UNCL_LABEL}'.")
    sub("NC1 vs NC2 vs NC3")
    child_compare(nc, "business_portfolio", NC_ORDER, "nc_cmp", None, {"NC1": ch.SEG_COLORS["NC1"], "NC2": ch.SEG_COLORS["NC2"], "NC3": ch.SEG_COLORS["NC3"]})
    c1, c2 = st.columns(2)
    with c1:
        panel(nc, "brand", "Top 10 Brand New Car", "nc_b", total_ppd=TOT_PPD, total_otr=TOT_OTR)
    with c2:
        panel(nc, "DLC", "Top 10 Dealer New Car", "nc_d", total_ppd=TOT_PPD, total_otr=TOT_OTR)
    sub("Analisis per NC")
    tabs = st.tabs(["NC1", "NC2", "NC3"])
    for tb, n in zip(tabs, ["NC1", "NC2", "NC3"]):
        with tb:
            d = nc[nc["business_portfolio"] == n]
            if no_data(d, f"Tidak ada kontrak {n} pada filter ini."):
                continue
            kpis(d, n, nc, "New Car")
            insight_box(ins.contribution(d, n, "New Car", nc))
            breakdown(d, f"nc_{n}", [("brand", "Brand", 5), ("model_family", "Model", 5), ("DLC", "Dealer", 5),
                                     ("Sales Through", "Sales Through", 5), ("Internal Sales Force", "Sales Force", 5),
                                     ("Financing Type", "Financing Type", 5)])


def page_used_car():
    head("Used Car (UCAR)", "")
    uc = PF(P_UC)
    if no_data(uc, "Tidak ada kontrak Used Car pada filter ini."):
        return
    kpis(uc, "Used Car")
    insight_box(ins.contribution(uc, "Used Car", "total Car Cabang Solo", p) + ins.child_group(uc, "brand", "Used Car", [("DLC", "Dealer")])[:3])
    c1, c2 = st.columns(2)
    with c1:
        panel(uc, "brand", "Top 10 Brand Used Car", "uc_b", total_ppd=TOT_PPD, total_otr=TOT_OTR)
    with c2:
        panel(uc, "DLC", "Top 10 Dealer Used Car", "uc_d", total_ppd=TOT_PPD, total_otr=TOT_OTR)
    breakdown(uc, "uc", [("model_family", "Model", 10), ("Sales Through", "Sales Through", 5),
                         ("Internal Sales Force", "Sales Force", 10), ("Financing Type", "Financing Type", 5)])
    sub("New Car vs Used Car")
    compare_panel(PF(P_NC), uc, "New Car", "Used Car", "uc_cmp")


def page_dealer():
    head("Dealer & Channel", "Dealer mana yang menjadi contributor terbesar, dan source mana yang menghasilkan volume dan value?")
    if no_data(p):
        return
    only = st.checkbox("Ranking dealer hanya untuk source Dealer (tanpa DLC Retention/NDS/REFFO)", value=True, key="dc_only")
    d = p[p["business_source"] == S_DEALER] if only else p
    if no_data(d, "Tidak ada dealer pada filter ini."):
        return
    insight_box(ins.dealer_insight(d))
    sub("Top 10 Dealer")
    s = summarize(d, "DLC", len(p), p["OTR"].sum())
    tabs = st.tabs(["PPD", "OTR", "Average Ticket"])
    for tb, m in zip(tabs, METRICS):
        with tb:
            st.plotly_chart(ch.rank_bar(rank_for_metric(s, m, 10), "DLC", m), width="stretch", key=f"dc_{m}")
    with st.expander("Tabel dealer"):
        st.dataframe(display_table(s.drop(columns=["Median TAT"])), hide_index=True, width="stretch")
    panel(p, "Sales Through", "Top 10 Sales Through", "dc_st", default_top=10)

    sub("Perbandingan Business Source", "Dimensi source terpisah dari portfolio. Jangan dijumlahkan dengan portfolio.")
    src = summarize(p, "business_source", TOT_PPD, TOT_OTR)
    insight_box(ins.source_insight(p))
    st.plotly_chart(ch.source_contrib(src, SOURCE_ORDER), width="stretch", key="dc_src")
    st.markdown(
        "Satu kontrak punya tepat satu portfolio dan satu source; tabel di bawah adalah irisan keduanya, bukan penjumlahan dua bisnis. "
        "NDS di sini adalah NDS Non Channel; NDS Channel ditampilkan sebagai Channeling.")
    x = summarize(p, ["portfolio", "business_source"], TOT_PPD, TOT_OTR)
    mm = st.selectbox("Metrik stacked bar", ("PPD", "OTR"), key="dc_m")
    st.plotly_chart(ch.stacked_bar(x, "portfolio", "business_source", mm, order=[s_ for s_ in CAR_PORTFOLIOS if s_ in set(x["portfolio"])]),
                    width="stretch", key="dc_stack")
    st.dataframe(display_table(x[["portfolio", "business_source", "PPD", "PPD %", "OTR", "OTR %", "Avg Ticket"]].rename(
        columns={"portfolio": "Portfolio", "business_source": "Source"})), hide_index=True, width="stretch")


def page_sales_force():
    head("Sales Force", "Sales Force mana yang menghasilkan produksi terbesar?")
    if no_data(p):
        return
    c1, c2, c3, c4 = st.columns(4)
    pf = c1.multiselect("Portfolio", [s for s in CAR_PORTFOLIOS if s in set(p["portfolio"])], placeholder="Semua", key="sf_pf")
    pr = c2.multiselect("Product", sorted(p["product"].dropna().unique()), placeholder="Semua", key="sf_pr")
    dl = c3.multiselect("Dealer", sorted(p["DLC"].dropna().unique()), placeholder="Semua", key="sf_dl")
    st_ = c4.multiselect("Sales Through", sorted(p["Sales Through"].dropna().unique()), placeholder="Semua", key="sf_st")
    d = p
    for vals, col in ((pf, "portfolio"), (pr, "product"), (dl, "DLC"), (st_, "Sales Through")):
        if vals:
            d = d[d[col].isin(vals)]
    if no_data(d, "Tidak ada data untuk kombinasi filter ini."):
        return
    m = st.selectbox("Metrik", METRICS, key="sf_m")
    n = st.selectbox("Tampilkan", [5, 10, 20], index=1, key="sf_n")
    roles = [("Internal Sales Force", "Internal Sales Force"), ("CFO", "CFO"), ("Inisiator", "inisiator_name")]
    tabs = st.tabs([r[0] for r in roles])
    for tb, (lab, col) in zip(tabs, roles):
        with tb:
            s = summarize(d, col, len(d), d["OTR"].sum())
            insight_box(ins.sales_force_insight(s, col))
            st.plotly_chart(ch.rank_bar(rank_for_metric(s, m, n), col, m), width="stretch", key=f"sf_c_{col}")
            st.dataframe(display_table(rank_for_metric(s, m, n).drop(columns=["Median TAT", "Pokok Hutang"])), hide_index=True, width="stretch")
            if m == "Avg Ticket":
                st.caption("Ranking Avg Ticket mengabaikan grup dengan < 2 kontrak bila grup lain cukup banyak.")


def page_trend():
    head("Production Trend", "Bagaimana tren PPD sepanjang periode, dan apakah ada month-end acceleration?")
    if no_data(p):
        return
    d = daily_series(p, *RANGE)
    per = period_summary(p)
    insight_box(ins.trend_insight(d, per))
    w = st.selectbox("Moving average (hari)", [3, 5, 7], index=2, key="tr_w")
    pk = d.loc[d["PPD"].idxmax()]
    pos = d[d["PPD"] > 0]
    lo = pos.loc[pos["PPD"].idxmin()] if len(pos) else None
    kpi_cards([("Peak date (PPD)", f"{pk['Tanggal']:%d %b}", f"{fmt_int(pk['PPD'])} kontrak"),
               ("Lowest date (hari produksi)", f"{lo['Tanggal']:%d %b}" if lo is not None else "-", f"{fmt_int(lo['PPD'])} kontrak" if lo is not None else ""),
               ("Hari tanpa PPD", fmt_int((d["PPD"] == 0).sum()), "akhir pekan/libur"),
               ("Rata-rata PPD / hari", fmt_int(d["PPD"].mean()), "seluruh hari kalender")])
    sub("Daily PPD")
    st.plotly_chart(ch.daily_line(d, "PPD", w), width="stretch", key="tr_ppd")
    sub("Daily OTR")
    st.plotly_chart(ch.daily_line(d, "OTR", w), width="stretch", key="tr_otr")
    sub("Daily PPD by Portfolio")
    mm = st.selectbox("Metrik", ("PPD", "OTR"), key="tr_sm")
    st.plotly_chart(ch.stacked_daily(daily_by_segment(p), mm), width="stretch", key="tr_seg")
    sub("Month-End Analysis", "Periode 1-7, 8-14, 15-21, 22-akhir bulan.")
    mt = st.selectbox("Metrik periode", ("PPD", "OTR", "Avg Ticket", "PPD / hari"), key="tr_pm")
    per_v = per[per["period_bucket"] != "Tanggal tidak valid"]
    c1, c2 = st.columns(2)
    if mt == "PPD / hari":
        c1.plotly_chart(ch.col_bar(per_v.assign(PPD=per_v["PPD / hari"]), "period_bucket", "PPD"), width="stretch", key="tr_pb")
    else:
        c1.plotly_chart(ch.col_bar(per_v, "period_bucket", mt), width="stretch", key="tr_pb")
    t = per[["period_bucket", "Hari", "PPD", "OTR", "Avg Ticket", "PPD / hari"]].rename(columns={"period_bucket": "Periode"}).copy()
    t["PPD / hari"] = t["PPD / hari"].map(lambda z: f"{z:.1f}".replace(".", ","))
    c2.dataframe(display_table(t), hide_index=True, width="stretch")


def page_tat():
    head("Operational / TAT", "Seberapa cepat Order berubah menjadi PPD?")
    if no_data(p):
        return
    t = calculate_metrics(p)
    kpi_cards([("Average TAT", fmt_days(t["avg_tat"]), ""), ("Median TAT", fmt_days(t["median_tat"]), ""),
               ("Same-Day PPD", fmt_pct(t["same_day_pct"]), f"{fmt_int(t['same_day'])} kontrak"),
               ("TAT <= 1 hari", fmt_pct(t["tat_le1_pct"]), ""), ("TAT <= 3 hari", fmt_pct(t["tat_le3_pct"]), ""),
               ("Maximum TAT", fmt_days(t["tat_max"]), "")])
    st.caption("TAT = Tgl PPD - Tgl Order (hari kalender). TAT negatif atau tanggal tidak valid dikeluarkan dari perhitungan.")
    insight_box(ins.tat_insight(p))
    sub("Order-to-PPD TAT")
    st.plotly_chart(ch.tat_hist(p["tat_days"]), width="stretch", key="tat_h")
    sub("Breakdown TAT")
    tabs = st.tabs(["Portfolio", "Sales Through"])
    for tb, col in zip(tabs, ["portfolio", "Sales Through"]):
        with tb:
            s = summarize(p, col).dropna(subset=["Avg TAT"])
            if no_data(s):
                continue
            st.plotly_chart(ch.tat_bar(s, col), width="stretch", key=f"tat_b_{col}")
            st.dataframe(display_table(s[[col, "PPD", "Avg TAT", "Median TAT"]]), hide_index=True, width="stretch")


def page_dq():
    head("Data Quality", "Seberapa bisa dipercaya data dan klasifikasinya?")
    base = df_all[df_all["counted_net"]]
    cc = classification_check(base)
    miss = df_all
    n_unknown = lambda col: int((miss[col] == "Tidak diketahui").sum())  # noqa: E731
    kpi_cards([("Total rows", fmt_int(dq["n_raw"]), f"header di baris {dq['header_row']}"),
               ("Duplicate rows", fmt_int(dq["n_dup_extra"]), f"{dq['n_cancel']} kontrak punya pasangan CANCEL PPD"),
               ("Cancel PPD", fmt_int(dq["n_cancel"]), f"+ {fmt_int(dq['n_reversed'])} baris PPD yang dibatalkan"),
               ("Net PPD", fmt_int(int(df_all["counted_net"].sum())), "basis default")])
    st.write("")
    kpi_cards([("Invalid dates", fmt_int(sum(dq["invalid_dates_after_parse"].values())), f"di luar periode: {fmt_int(dq['out_of_period'])}"),
               ("Negative TAT", fmt_int(dq["negative_tat"]), "dikeluarkan dari TAT"),
               ("Missing Product", fmt_int(n_unknown("Jenis Produk")), ""),
               ("Missing Dealer/DLC", fmt_int(n_unknown("DLC")), "")])
    st.write("")
    kpi_cards([("Missing Sales Force", fmt_int(n_unknown("Internal Sales Force")), "Internal Sales Force"),
               ("Non-Car dikeluarkan", fmt_int(dq["n_excluded_non_car"]), "MCY, MPL, lainnya"),
               ("Unclassified sub-portfolio", fmt_int(cc["unclassified_sub"]), UNCL_LABEL),
               ("Unclassified source", fmt_int(cc["unclassified_source"]), "Other")])
    sub("Classification Coverage", "Basis Net, tanpa filter, cakupan Car (4W).")
    cov = pd.DataFrame([
        {"Dimensi": "Sub-portfolio (child)", "Classified %": cc["cov_sub"], "Unclassified %": 1 - cc["cov_sub"], "Unclassified": cc["unclassified_sub"]},
        {"Dimensi": "Business source", "Classified %": cc["cov_source"], "Unclassified %": 1 - cc["cov_source"], "Unclassified": cc["unclassified_source"]}])
    cov["Classified %"] = cov["Classified %"].map(fmt_pct)
    cov["Unclassified %"] = cov["Unclassified %"].map(fmt_pct)
    st.dataframe(cov, hide_index=True, width="stretch")

    sub("Validasi hierarki parent-child (basis Net, tanpa filter)")
    show_hierarchy(validate_hierarchy(base))
    unc = base[base["sub_unclassified"]]
    if len(unc):
        with st.expander(f"Record yang belum terklasifikasi sampai sub-portfolio ({len(unc)})"):
            st.dataframe(unc[["portfolio", "business_portfolio", "Object", "product", "Model", "brand", "OTR"]], hide_index=True, width="stretch")

    sub("Penanganan masalah data")
    st.markdown(f"""
- **NaN / missing values**: kolom dimensi kosong diisi `Tidak diketahui`; OTR kosong ({dq['missing_otr']}) tidak ikut dijumlahkan. Avg Ticket = total Pokok Hutang / jumlah PPD (Pokok Hutang kosong dihitung 0). Pembagian dengan nol menghasilkan nilai kosong, bukan error.
- **Duplikat**: kontrak yang tampil dua kali dengan status PPD dan CANCEL PPD ({dq['n_cancel']} pasangan) dianggap pembatalan; basis Net mengeluarkan kedua barisnya. Duplikat murni (No Kontrak + Status sama) = {dq['n_dup_extra']}.
- **Tanggal**: gagal dibaca = {dq['invalid_dates_after_parse']}; TAT negatif = {dq['negative_tat']}; PPD di luar periode laporan = {dq['out_of_period']}. Baris itu tetap di total tetapi keluar dari TAT/tren.
- **Angka berbentuk teks**: dikonversi dengan `to_numeric(errors='coerce')`.
- **Kolom opsional hilang**: {', '.join(dq['missing_optional_cols']) or 'tidak ada'} (dibuat kosong agar halaman tetap jalan). Kolom kosong total di sumber: {', '.join(dq['empty_cols']) or '-'}.
- **Klasifikasi tidak pasti**: masuk `Unclassified`/`Other`, tidak dipaksakan.
""")
    sub("Missing values per kolom")
    mv = dq["missing"].copy()
    mv["% Kosong"] = mv["% Kosong"].map(fmt_pct)
    st.dataframe(mv, hide_index=True, width="stretch")
    sub("Kontrak ganda")
    dd = dq["dup_contract_rows"]
    if len(dd):
        st.dataframe(dd[["No Kontrak", "Tgl Order", "Tgl PPD", "Status", "Model", "OTR"]], hide_index=True, width="stretch")
    else:
        st.write("Tidak ada.")

    sub("Mapping yang digunakan")
    st.markdown("**1. Portfolio (parent) dari Object dan Jenis Produk**")
    st.caption(f"Record di luar Object MOBIL BARU / MOBIL BEKAS ({fmt_int(dq['n_excluded_non_car'])}) tidak dimuat di dashboard ini.")
    mp = df_all.groupby(["Object", "product", "portfolio"]).size().reset_index(name="Kontrak")
    st.dataframe(mp.rename(columns={"product": "Jenis Produk", "portfolio": "Portfolio"}), hide_index=True, width="stretch")
    st.caption("Aturan: MOBIL BARU = New Car, MOBIL BEKAS = Used Car.")
    st.markdown("**2. New Car: brand (dari kata kunci Model) -> NC1/NC2/NC3**")
    a = base[base["portfolio"] == P_NC].groupby(["brand", "business_portfolio", "mp_nc_code"], dropna=False).size().reset_index(name="Kontrak")
    a["Referensi kode MP"] = a["mp_nc_code"].map(NC_MP_CODE_REF)
    st.dataframe(a.rename(columns={"business_portfolio": "Hasil", "mp_nc_code": "Kode MP"}), hide_index=True, width="stretch")
    st.markdown("**3. Business Source (dievaluasi berurutan)**")
    st.dataframe(pd.DataFrame(SOURCE_RULES, columns=["Aturan", "Source"]), hide_index=True, width="stretch")
    sd = df_all.groupby(["business_source", "DLC"]).size().reset_index(name="Kontrak")
    with st.expander("DLC non-dealer dan source-nya"):
        st.dataframe(sd[sd["business_source"] != S_DEALER], hide_index=True, width="stretch")
    st.markdown("**4. Brand dan Model**")
    unk = df_all[df_all["brand"] == "Tidak teridentifikasi"]
    if len(unk):
        warn_box(f"{len(unk)} kontrak brand-nya tidak teridentifikasi. Tambahkan kata kunci di business_mapping.py.")
        st.dataframe(unk[["Object", "Model", "OTR"]], hide_index=True, width="stretch")
    else:
        st.write("Semua brand teridentifikasi.")


def page_detail():
    head("Data Detail", "Data transaksi sesuai filter aktif.")
    d = f.assign(PPD=f["counted_net"].astype(int), TAT=f["tat_days"], Dealer=f["DLC"])
    base = ["Tgl PPD", "Tgl Order", "PPD", "portfolio", "business_portfolio", "business_source", "product", "Object", "Financing Type",
            "Sales Through", "DLC", "Dealer", "brand", "Model", "OTR", "Pokok Hutang", "Total Piutang", "Internal Sales Force", "CFO",
            "inisiator_name", "TAT", "Status", "No Kontrak"]
    base = [c for c in base if c in d.columns]
    cols = st.multiselect("Kolom", list(d.columns), default=base, key="dt_cols")
    st.caption(f"{fmt_int(len(d))} baris pada filter (termasuk CANCEL PPD). Kolom PPD = 1 bila dihitung pada basis Net.")
    show = d[cols] if cols else d
    st.dataframe(show, hide_index=True, width="stretch")
    st.download_button("Unduh CSV", show.to_csv(index=False).encode("utf-8"), "ppd_solo_car_filtered.csv", "text/csv")


ROUTES = {"Executive Summary": page_exec, "Portfolio Overview": page_portfolio, "New Car": page_new_car,
          "Used Car": page_used_car, "Dealer & Channel": page_dealer,
          "Sales Force": page_sales_force, "Production Trend": page_trend, "Operational / TAT": page_tat,
          "Data Quality": page_dq, "Data Detail": page_detail}
ROUTES[page]()
