"""Plotly chart builders. Palet minimal: navy sebagai warna utama, satu aksen."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from metrics import summarize
from utils import fmt_int, fmt_pct, fmt_rp, metric_fmt, scale_metric

PRIMARY = "#1F3A5F"
ACCENT = "#C8553D"
MUTED = "#9AA7B4"
SEG_COLORS = {
    "New Car": "#1F3A5F", "Used Car": "#4F7CAC", "New MCY": "#C8553D", "Used MCY": "#E0A458",
    "MPL": "#5B8C85", "Other / Unclassified": "#B8B8B8",
    "NC1": "#1F3A5F", "NC2": "#4F7CAC", "NC3": "#8FB3D9", "Honda": "#C8553D", "Yamaha": "#1F3A5F", "SMB": "#7A8B99",
    "MPL 2W": "#5B8C85", "MPL 4W": "#E0A458",
}
CAT_COLORS = ["#1F3A5F", "#C8553D", "#5B8C85", "#E0A458", "#7A8B99", "#4F7CAC", "#8E6C8A"]


def _base(fig, height=380, title=None, legend=True):
    fig.update_layout(
        template="plotly_white", height=height, title=dict(text=title, x=0, font=dict(size=14)) if title else None,
        margin=dict(l=10, r=20, t=44 if title else 12, b=10),
        font=dict(family="Segoe UI, Arial, sans-serif", size=12, color="#243447"),
        showlegend=legend, legend=dict(orientation="h", y=-0.18, x=0),
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
    )
    fig.update_xaxes(gridcolor="#EEF1F5", zeroline=False)
    fig.update_yaxes(gridcolor="#EEF1F5", zeroline=False)
    return fig


def _hover(s):
    return np.stack([s["PPD"].map(fmt_int), s["OTR"].map(fmt_rp), s["Avg Ticket"].map(fmt_rp),
                     s["PPD %"].map(fmt_pct)], axis=-1)


HOVER = ("<b>%{y}</b><br>PPD: %{customdata[0]}<br>OTR: %{customdata[1]}<br>"
         "Avg Ticket: %{customdata[2]}<br>Kontribusi PPD: %{customdata[3]}<extra></extra>")


def rank_bar(s, cat, metric, title=None, color=PRIMARY):
    """Bar horizontal; s sudah berisi Top-N."""
    s = s.copy()
    v, ax = scale_metric(s[metric], metric)
    s["_v"] = v
    s = s.sort_values("_v", ascending=True)
    fig = go.Figure(go.Bar(
        x=s["_v"], y=s[cat].astype(str), orientation="h", marker_color=color,
        text=s[metric].map(metric_fmt(metric)), textposition="outside", cliponaxis=False,
        customdata=_hover(s), hovertemplate=HOVER))
    fig.update_xaxes(title=ax)
    fig.update_yaxes(automargin=True)
    return _base(fig, height=max(260, 30 * len(s) + 90), title=title, legend=False)


def col_bar(s, cat, metric, title=None, color=PRIMARY, colors=None):
    s = s.copy()
    v, ax = scale_metric(s[metric], metric)
    mc = [colors.get(c, color) for c in s[cat]] if colors else color
    fig = go.Figure(go.Bar(
        x=s[cat].astype(str), y=v, marker_color=mc, text=s[metric].map(metric_fmt(metric)),
        textposition="outside", cliponaxis=False,
        customdata=_hover(s), hovertemplate=HOVER.replace("%{y}", "%{x}")))
    fig.update_yaxes(title=ax)
    return _base(fig, height=360, title=title, legend=False)


def grouped_bar(p, x, color, metric, title=None, x_order=None):
    """Grouped bar: x = kategori utama, color = sub-dimensi."""
    s = summarize(p, [x, color])
    fig = go.Figure()
    cats = x_order or list(s[x].unique())
    for i, c in enumerate(sorted(s[color].unique())):
        t = s[s[color] == c].set_index(x).reindex(cats)
        v, ax = scale_metric(t[metric], metric)
        fig.add_trace(go.Bar(
            name=str(c), x=cats, y=v, marker_color=CAT_COLORS[i % len(CAT_COLORS)],
            text=t[metric].map(lambda z: "" if pd.isna(z) else metric_fmt(metric)(z)), textposition="outside",
            cliponaxis=False))
    fig.update_layout(barmode="group")
    fig.update_yaxes(title=ax if len(s) else metric)
    return _base(fig, height=380, title=title)


def volume_value_bars(seg, metric, title):
    seg = seg.copy()
    return col_bar(seg, "portfolio", metric, title=title, colors=SEG_COLORS)


def scatter_matrix(seg):
    """Volume (PPD) vs Value (OTR), ukuran = Avg Ticket, warna = segmen."""
    fig = go.Figure()
    if seg.empty:
        return _base(fig)
    mx = seg["Avg Ticket"].max()
    for _, r in seg.iterrows():
        fig.add_trace(go.Scatter(
            x=[r["PPD"]], y=[r["OTR"] / 1e9], mode="markers+text", name=r["portfolio"],
            text=[r["portfolio"]], textposition="top center",
            marker=dict(size=[max(14, 70 * r["Avg Ticket"] / mx)], color=SEG_COLORS.get(r["portfolio"], MUTED),
                        opacity=0.85, line=dict(width=1, color="#FFFFFF")),
            customdata=[[r["portfolio"], fmt_int(r["PPD"]), fmt_rp(r["OTR"]), fmt_rp(r["Avg Ticket"]),
                         fmt_pct(r["PPD %"]), fmt_pct(r["OTR %"])]],
            hovertemplate=("<b>%{customdata[0]}</b><br>PPD: %{customdata[1]}<br>OTR: %{customdata[2]}<br>"
                           "Avg Ticket: %{customdata[3]}<br>Kontribusi PPD: %{customdata[4]}<br>"
                           "Kontribusi OTR: %{customdata[5]}<extra></extra>")))
    fig.add_vline(x=seg["PPD"].mean(), line_dash="dash", line_color=MUTED, annotation_text="rata-rata PPD",
                  annotation_position="top")
    fig.add_hline(y=seg["OTR"].mean() / 1e9, line_dash="dash", line_color=MUTED, annotation_text="rata-rata OTR",
                  annotation_position="right")
    fig.update_xaxes(title="PPD (kontrak) - volume", rangemode="tozero")
    fig.update_yaxes(title="OTR (Rp miliar) - value", rangemode="tozero")
    return _base(fig, height=470, legend=False)


def daily_line(d, metric, window=7, title=None):
    v, ax = scale_metric(d[metric], metric)
    ma = v.rolling(window, min_periods=1).mean()
    fig = go.Figure()
    fig.add_trace(go.Bar(x=d["Tanggal"], y=v, name="Harian", marker_color="#C9D3DE"))
    fig.add_trace(go.Scatter(x=d["Tanggal"], y=ma, name=f"Moving average {window} hari",
                             line=dict(color=PRIMARY, width=2.5)))
    if v.sum() > 0:
        ip = v.idxmax()
        fig.add_trace(go.Scatter(x=[d.loc[ip, "Tanggal"]], y=[v[ip]], mode="markers+text", name="Puncak",
                                 text=["Puncak"], textposition="top center",
                                 marker=dict(color=ACCENT, size=11)))
        pos = v[v > 0]
        il = pos.idxmin()
        fig.add_trace(go.Scatter(x=[d.loc[il, "Tanggal"]], y=[v[il]], mode="markers+text", name="Terendah (hari produksi)",
                                 text=["Terendah"], textposition="bottom center",
                                 marker=dict(color="#E0A458", size=11)))
    fig.update_yaxes(title=ax)
    fig.update_xaxes(title="Tanggal PPD")
    return _base(fig, height=360, title=title)


def stacked_daily(dseg, metric="PPD", col="portfolio", title=None):
    v, ax = scale_metric(dseg[metric], metric)
    fig = go.Figure()
    for i, c in enumerate([x for x in SEG_COLORS if x in set(dseg[col])] + [x for x in dseg[col].unique() if x not in SEG_COLORS]):
        t = dseg[dseg[col] == c]
        fig.add_trace(go.Bar(x=t["ppd_date"], y=scale_metric(t[metric], metric)[0], name=c,
                             marker_color=SEG_COLORS.get(c, CAT_COLORS[i % len(CAT_COLORS)])))
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title=ax)
    fig.update_xaxes(title="Tanggal PPD")
    return _base(fig, height=400, title=title)


def stacked_bar(df, x, color, value, title=None, order=None):
    """df long-format: x, color, value (PPD atau OTR)."""
    fig = go.Figure()
    cats = order or list(df[x].unique())
    for i, c in enumerate(df[color].unique()):
        t = df[df[color] == c].set_index(x).reindex(cats).fillna(0)
        v, ax = scale_metric(t[value], value)
        fig.add_trace(go.Bar(name=str(c), x=cats, y=v, marker_color=CAT_COLORS[i % len(CAT_COLORS)]))
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title=ax if len(df) else value)
    return _base(fig, height=400, title=title)


def source_contrib(src, order=None):
    """Kontribusi PPD% dan OTR% per sumber (horizontal grouped)."""
    s = src.copy()
    if order:
        s["_o"] = s["business_source"].map({k: i for i, k in enumerate(order)})
        s = s.sort_values("_o", ascending=False)
    fig = go.Figure()
    fig.add_trace(go.Bar(y=s["business_source"], x=s["PPD %"] * 100, orientation="h", name="Kontribusi PPD (%)",
                         marker_color=PRIMARY, text=s["PPD %"].map(fmt_pct), textposition="outside"))
    fig.add_trace(go.Bar(y=s["business_source"], x=s["OTR %"] * 100, orientation="h", name="Kontribusi OTR (%)",
                         marker_color=ACCENT, text=s["OTR %"].map(fmt_pct), textposition="outside"))
    fig.update_layout(barmode="group")
    fig.update_xaxes(title="% dari total", range=[0, max(s["PPD %"].max(), s["OTR %"].max()) * 100 * 1.2 + 1])
    return _base(fig, height=max(320, 70 * len(s) + 90))


def tat_hist(tat: pd.Series, title=None):
    t = tat.dropna()
    fig = go.Figure(go.Histogram(x=t, xbins=dict(start=-0.5, size=1), marker_color=PRIMARY, opacity=0.9))
    if len(t):
        fig.add_vline(x=t.mean(), line_dash="dash", line_color=ACCENT, annotation_text=f"Rata-rata {t.mean():.1f}".replace(".", ","),
                      annotation_position="top right")
        fig.add_vline(x=t.median(), line_dash="dot", line_color="#5B8C85", annotation_text=f"Median {t.median():.1f}".replace(".", ","),
                      annotation_position="top left")
    fig.update_xaxes(title="TAT (hari: Tgl PPD - Tgl Order)")
    fig.update_yaxes(title="Jumlah kontrak")
    return _base(fig, height=360, title=title, legend=False)


def tat_bar(s, cat, title=None):
    s = s.sort_values("Avg TAT", ascending=True)
    fig = go.Figure()
    fig.add_trace(go.Bar(y=s[cat].astype(str), x=s["Avg TAT"], orientation="h", name="Rata-rata TAT", marker_color=PRIMARY,
                         text=s["Avg TAT"].map(lambda z: f"{z:.1f}".replace(".", ",")), textposition="outside"))
    fig.add_trace(go.Bar(y=s[cat].astype(str), x=s["Median TAT"], orientation="h", name="Median TAT", marker_color=MUTED,
                         text=s["Median TAT"].map(lambda z: f"{z:.1f}".replace(".", ",")), textposition="outside"))
    fig.update_layout(barmode="group")
    fig.update_xaxes(title="Hari")
    fig.update_yaxes(automargin=True)
    return _base(fig, height=max(300, 60 * len(s) + 100), title=title)
