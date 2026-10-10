"""Automatic insight engine. Semua angka dihitung dari dataframe hasil filter; tidak ada hardcode."""
import numpy as np
import pandas as pd

from business_mapping import P_OTHER
from metrics import summarize, totals
from utils import fmt_days, fmt_int, fmt_pct, fmt_rp


def _empty(p):
    return p is None or len(p) == 0


def _lead(s, col):
    return s.sort_values(col, ascending=False).iloc[0]


def _num(x, d=1):
    return str(round(x, d)).replace(".", ",")


def _leaders(s, cat, name):
    """Kalimat volume leader / value leader / avg ticket leader untuk kelompok child."""
    if s is None or len(s) == 0:
        return []
    v, o, t = _lead(s, "PPD"), _lead(s, "OTR"), _lead(s, "Avg Ticket")
    out = [f"{v[cat]} adalah volume leader {name} ({fmt_int(v['PPD'])} PPD, {fmt_pct(v['PPD %'])} dari {name})."]
    if o[cat] != v[cat]:
        out.append(f"{o[cat]} adalah value leader dengan OTR terbesar ({fmt_rp(o['OTR'])}, {fmt_pct(o['OTR %'])}).")
    else:
        out.append(f"{v[cat]} juga value leader (OTR {fmt_rp(v['OTR'])}, {fmt_pct(v['OTR %'])}).")
    if len(s) > 1:
        out.append(f"{t[cat]} memiliki average ticket tertinggi ({fmt_rp(t['Avg Ticket'])}).")
    return out


def executive(p):
    if _empty(p):
        return ["Tidak ada data pada filter yang dipilih."]
    s = summarize(p[p["portfolio"] != P_OTHER], "portfolio")
    out = []
    if len(s):
        v, o, t = _lead(s, "PPD"), _lead(s, "OTR"), _lead(s, "Avg Ticket")
        txt = f"{v['portfolio']} adalah portfolio terbesar Cabang Solo berdasarkan volume ({fmt_pct(v['PPD'] / len(p))} dari total PPD, {fmt_int(v['PPD'])} kontrak)"
        if o["portfolio"] != v["portfolio"]:
            txt += f", sedangkan {o['portfolio']} menjadi value driver terbesar ({fmt_pct(o['OTR'] / p['OTR'].sum())} dari total OTR)."
        else:
            txt += f" dan sekaligus value driver ({fmt_pct(o['OTR'] / p['OTR'].sum())} dari total OTR)."
        out.append(txt)
        if t["portfolio"] != v["portfolio"]:
            out.append(f"{t['portfolio']} memiliki average ticket tertinggi ({fmt_rp(t['Avg Ticket'])}) dibanding {v['portfolio']} ({fmt_rp(v['Avg Ticket'])}).")
    oth = p[p["portfolio"] == P_OTHER]
    if len(oth):
        out.append(f"{fmt_int(len(oth))} kontrak ({fmt_pct(len(oth) / len(p))} PPD) belum masuk portfolio dalam hierarki ({UNCL})."
                   )
    return out


UNCL = "detail belum tersedia"


def portfolio_overview(p):
    if _empty(p):
        return []
    s = summarize(p[p["portfolio"] != P_OTHER], "portfolio")
    if s.empty:
        return []
    out = _leaders(s, "portfolio", "portfolio")
    w = summarize(p[p["portfolio"] != P_OTHER], "wheel")
    if len(w) > 1:
        a = _lead(w, "PPD")
        out.append(f"Berdasarkan struktur wheel, {a['wheel']} terbesar dengan {fmt_pct(a['PPD %'])} PPD dan {fmt_pct(a['OTR %'])} OTR.")
    return out


def child_group(df, cat, name, extra_dims=()):
    """Insight umum untuk kelompok child (NC1/NC2/NC3, Honda/Yamaha/SMB, MPL 2W/4W)."""
    if _empty(df):
        return [f"Tidak ada data {name} pada filter ini."]
    s = summarize(df, cat)
    out = _leaders(s, cat, name)
    for col, label in extra_dims:
        d = summarize(df, col)
        if len(d) > 1:
            a = _lead(d, "PPD")
            out.append(f"{label} contributor terbesar {name}: {a[col]} ({fmt_pct(a['PPD %'])} PPD, {fmt_pct(a['OTR %'])} OTR).")
    return out


def compare_two(a, b, name_a, name_b):
    if _empty(a) or _empty(b):
        return []
    ta, tb = totals(a), totals(b)
    out = []
    if ta["ppd"] != tb["ppd"]:
        hi, lo = (name_a, name_b) if ta["ppd"] > tb["ppd"] else (name_b, name_a)
        out.append(f"{hi} memiliki volume lebih tinggi dari {lo} ({fmt_int(max(ta['ppd'], tb['ppd']))} vs {fmt_int(min(ta['ppd'], tb['ppd']))} PPD).")
    if ta["avg_ticket"] != tb["avg_ticket"] and min(ta["avg_ticket"], tb["avg_ticket"]) > 0:
        hi, lo = (name_a, name_b) if ta["avg_ticket"] > tb["avg_ticket"] else (name_b, name_a)
        r = max(ta["avg_ticket"], tb["avg_ticket"]) / min(ta["avg_ticket"], tb["avg_ticket"])
        out.append(f"Average ticket {hi} ({fmt_rp(max(ta['avg_ticket'], tb['avg_ticket']))}) sekitar {_num(r)}x {lo} ({fmt_rp(min(ta['avg_ticket'], tb['avg_ticket']))}).")
    if ta["otr"] != tb["otr"]:
        hi = name_a if ta["otr"] > tb["otr"] else name_b
        out.append(f"Dari sisi OTR, {hi} lebih besar ({fmt_rp(max(ta['otr'], tb['otr']))} vs {fmt_rp(min(ta['otr'], tb['otr']))}).")
    return out


def contribution(df, name, parent_name, parent):
    if _empty(df):
        return [f"Tidak ada data {name} pada filter ini."]
    t, tp = totals(df), totals(parent)
    out = [f"{name} menyumbang {fmt_pct(t['ppd'] / tp['ppd']) if tp['ppd'] else '-'} dari PPD {parent_name} dan "
           f"{fmt_pct(t['otr'] / tp['otr']) if tp['otr'] else '-'} dari OTR {parent_name} ({fmt_int(t['ppd'])} kontrak, {fmt_rp(t['otr'])}, average ticket {fmt_rp(t['avg_ticket'])})."]
    return out


def channeling(ch, mpl):
    """Channeling sebagai bagian MPL (mpl = seluruh MPL pada filter)."""
    if _empty(ch):
        return ["Tidak ada kontrak Channeling pada MPL dengan filter ini."]
    out = contribution(ch, "Channeling", "MPL", mpl)
    s = summarize(ch, "business_portfolio")
    if len(s) > 1:
        a, b = s.sort_values("PPD", ascending=False).iloc[0], s.sort_values("Avg Ticket", ascending=False).iloc[0]
        if a["business_portfolio"] != b["business_portfolio"]:
            out.append(f"{a['business_portfolio']} Channeling menghasilkan volume lebih tinggi, tetapi {b['business_portfolio']} Channeling memiliki average ticket lebih tinggi ({fmt_rp(b['Avg Ticket'])}).")
        else:
            out.append(f"Channeling lebih kuat di {a['business_portfolio'].replace('MPL ', '')} dari volume ({fmt_pct(a['PPD %'])} PPD Channeling) maupun average ticket.")
    pa = summarize(ch, "partner")
    real = pa[pa["partner"] != "Tanpa Ext Sales 1"]
    if len(real):
        a = _lead(real, "PPD")
        out.append(f"Partner (Ext Sales 1) terbesar: {a['partner']} ({fmt_int(a['PPD'])} PPD, {fmt_rp(a['OTR'])} OTR).")
    nop = pa[pa["partner"] == "Tanpa Ext Sales 1"]
    if len(nop):
        out.append(f"{fmt_pct(nop.iloc[0]['PPD %'])} PPD Channeling tidak mencatat Ext Sales 1 sehingga partner tidak dapat diidentifikasi.")
    return out


def retention(re_, mpl):
    if _empty(re_):
        return ["Tidak ada kontrak Retention pada MPL dengan filter ini."]
    out = contribution(re_, "Retention", "MPL", mpl)
    s = summarize(re_, "business_portfolio")
    if len(s) > 1:
        a = s.sort_values("PPD", ascending=False).iloc[0]
        b = s.sort_values("PPD", ascending=False).iloc[1]
        out.append(f"{a['business_portfolio']} Retention lebih dominan dibanding {b['business_portfolio']} Retention ({fmt_pct(a['PPD %'])} vs {fmt_pct(b['PPD %'])} PPD Retention).")
    c = summarize(re_, "retention_category")
    if len(c):
        a = _lead(c, "PPD")
        out.append(f"Kategori Retention terbesar: {a['retention_category']} ({fmt_pct(a['PPD %'])} PPD Retention).")
    out.append("Retention bertujuan mempertahankan sekaligus meningkatkan customer value / Customer Lifetime Value, "
               "sehingga kualitas (average ticket dan kontribusi OTR) perlu dibaca bersama volume.")
    return out


def channeling_vs_retention(ch, re_, mpl):
    if _empty(mpl):
        return []
    c, r = len(ch), len(re_)
    out = []
    if c != r:
        hi, lo = ("Channeling", "Retention") if c > r else ("Retention", "Channeling")
        out.append(f"MPL Solo lebih banyak digerakkan oleh {hi} dibanding {lo} ({fmt_int(max(c, r))} vs {fmt_int(min(c, r))} PPD; "
                   f"{fmt_pct(max(c, r) / len(mpl))} dari PPD MPL).")
    elif c:
        out.append("Channeling dan Retention memiliki PPD yang sama pada MPL.")
    rows = []
    for w in ("MPL 2W", "MPL 4W"):
        rows.append((w, (ch["business_portfolio"] == w).sum(), (re_["business_portfolio"] == w).sum()))
    texts = []
    for w, a, b in rows:
        if a or b:
            texts.append(f"{w}: " + ("Channeling lebih besar" if a > b else "Retention lebih besar" if b > a else "seimbang") + f" (Channeling {fmt_int(a)} vs Retention {fmt_int(b)} PPD)")
    if texts:
        lead = [("Channeling" if a > b else "Retention" if b > a else "=") for _, a, b in rows if a or b]
        out.append("Pola per wheel - " + "; ".join(texts) + (". Pola sama di 2W dan 4W." if len(set(lead)) == 1 and len(lead) > 1 else ". Polanya berbeda antara 2W dan 4W." if len(lead) > 1 else "."))
    return out


def source_insight(p):
    if _empty(p):
        return []
    s = summarize(p, "business_source")
    a, o = _lead(s, "PPD"), _lead(s, "OTR")
    out = [f"{a['business_source']} menyumbang {fmt_pct(a['PPD %'])} PPD tetapi {fmt_pct(a['OTR %'])} OTR."]
    if o["business_source"] != a["business_source"]:
        out.append(f"Dari sisi nilai, {o['business_source']} terbesar ({fmt_pct(o['OTR %'])} OTR dengan {fmt_pct(o['PPD %'])} PPD).")
    out.append("Source adalah dimensi terpisah dari portfolio sehingga tidak dijumlahkan dengan portfolio.")
    return out


def dealer_insight(d):
    if _empty(d):
        return []
    s = summarize(d, "DLC")
    a = _lead(s, "PPD")
    o = _lead(s, "OTR")
    out = [f"{a['DLC']} adalah contributor terbesar berdasarkan PPD ({fmt_int(a['PPD'])} kontrak, {fmt_pct(a['PPD %'])})."]
    if o["DLC"] != a["DLC"]:
        out.append(f"Berdasarkan OTR, {o['DLC']} terbesar ({fmt_rp(o['OTR'])}, {fmt_pct(o['OTR %'])}).")
    out.append(f"Top 10 menyumbang {fmt_pct(s.head(10)['PPD'].sum() / s['PPD'].sum())} PPD pada kelompok ini.")
    return out


def trend_insight(d, per):
    out = []
    if d["PPD"].sum() > 0:
        pk = d.loc[d["PPD"].idxmax()]
        out.append(f"Puncak PPD terjadi pada {pk['Tanggal']:%d %b %Y} ({fmt_int(pk['PPD'])} kontrak). Ada {int((d['PPD'] == 0).sum())} hari tanpa PPD.")
    pv = per[per["period_bucket"].isin(["1-7", "8-14", "15-21", "22-akhir"]) & (per["PPD"] > 0)]
    if len(pv) >= 2 and "22-akhir" in set(pv["period_bucket"]):
        last = pv[pv["period_bucket"] == "22-akhir"].iloc[0]
        base = pv[pv["period_bucket"] != "22-akhir"]
        ratio = last["PPD / hari"] / base["PPD / hari"].mean()
        if ratio >= 1.1:
            out.append(f"Terdapat month-end acceleration: PPD/hari pada 22-akhir bulan ({_num(last['PPD / hari'])}) adalah {_num(ratio, 2)}x rata-rata tiga periode sebelumnya.")
        elif ratio <= 0.9:
            out.append(f"Tidak ada month-end acceleration: PPD/hari pada 22-akhir bulan hanya {_num(ratio, 2)}x rata-rata periode sebelumnya.")
        else:
            out.append("Laju PPD per hari relatif stabil sepanjang bulan; tidak terlihat akselerasi akhir bulan yang berarti.")
    return out


def tat_insight(p):
    t = totals(p)
    if not t["tat_n"]:
        return ["Tidak ada data TAT valid."]
    out = [f"Rata-rata TAT {fmt_days(t['avg_tat'])} dengan median {fmt_days(t['median_tat'])}; {fmt_pct(t['same_day_pct'])} kontrak di-PPD pada hari yang sama dengan order dan {fmt_pct(t['tat_le3_pct'])} selesai dalam 3 hari."]
    s = summarize(p, "portfolio").dropna(subset=["Avg TAT"])
    if len(s) > 1:
        a, b = s.sort_values("Avg TAT").iloc[0], s.sort_values("Avg TAT").iloc[-1]
        out.append(f"Order-to-PPD tercepat di {a['portfolio']} ({fmt_days(a['Avg TAT'])}) dan terlama di {b['portfolio']} ({fmt_days(b['Avg TAT'])}).")
    if t["avg_tat"] > t["median_tat"]:
        out.append(f"TAT maksimum {fmt_int(t['tat_max'])} hari; rata-rata di atas median menandakan ekor kasus lambat.")
    return out


def sales_force_insight(s, role):
    if _empty(s):
        return []
    a = _lead(s, "PPD")
    return [f"{a[role]} adalah kontributor PPD terbesar ({fmt_int(a['PPD'])} kontrak, {fmt_pct(a['PPD %'])}). Top 10 menyumbang {fmt_pct(s.head(10)['PPD'].sum() / s['PPD'].sum())} dari PPD pada peran ini."]


def generate_insight(kind, *args, **kw):
    """Dispatcher tunggal: generate_insight('executive', p) dst."""
    fn = {"executive": executive, "portfolio": portfolio_overview, "group": child_group, "compare": compare_two,
          "contribution": contribution, "channeling": channeling, "retention": retention,
          "ch_vs_re": channeling_vs_retention, "source": source_insight, "dealer": dealer_insight,
          "trend": trend_insight, "tat": tat_insight, "sales_force": sales_force_insight}[kind]
    return fn(*args, **kw)
