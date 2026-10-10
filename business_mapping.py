"""Business classification engine.

Tiga dimensi yang TIDAK boleh dicampur:
  1. Business Portfolio (parent)  : New Car, Used Car, New MCY, Used MCY, MPL
  2. Sub-portfolio (child)        : NC1/NC2/NC3, Honda/Yamaha/SMB, MPL 2W/MPL 4W
  3. Business Source / Function   : Dealer, Direct Sales, NDS, Channeling, Retention, ...
Channeling dan Retention adalah fungsi/source pada MPL, bukan portfolio sejajar.
Record yang tidak bisa dibuktikan masuk 'Unclassified' / 'Other', tidak dipaksakan.
"""
import re

import numpy as np
import pandas as pd

# ---------------- Dimension 1: Portfolio ----------------
P_NC, P_UC, P_NMCY, P_UMCY, P_MPL = "New Car", "Used Car", "New MCY", "Used MCY", "MPL"
P_OTHER = "Other / Unclassified"
CORE_PORTFOLIOS = [P_NC, P_UC, P_NMCY, P_UMCY, P_MPL]
CAR_PORTFOLIOS = [P_NC, P_UC]   # cakupan dashboard ini: 4W (New Car + Used Car)
PORTFOLIO_ORDER = CORE_PORTFOLIOS + [P_OTHER]
WHEEL_OF = {P_NC: "4W", P_UC: "4W", P_NMCY: "2W", P_UMCY: "2W", P_MPL: "MPL", P_OTHER: "Other"}

# Object -> portfolio. 'JASA' = produk dana tunai/multiguna (MPL); 2W/4W dari MOTOR/MOBIL.
OBJECT_TO_PORTFOLIO = {"MOBIL BARU": P_NC, "MOBIL BEKAS": P_UC, "MOTOR BARU": P_NMCY, "MOTOR BEKAS": P_UMCY,
                       "MOTOR JASA": P_MPL, "MOBIL JASA": P_MPL}
MPL_UNIT = {"MOTOR JASA": "MPL 2W", "MOBIL JASA": "MPL 4W"}
DFF_KEYWORD = "FLOOR FINANCING"   # Dealer Floor Financing: pembiayaan dealer, bukan MPL, tidak ada di hierarki -> Other

# Definisi NC
NC1_BRANDS = {"Toyota", "Daihatsu", "Isuzu"}                      # Astra Group
NC2_BRANDS = {"Suzuki", "Mitsubishi", "Honda", "Hino"}            # Japanese non-Astra
NC3_BRANDS = {"BYD", "Wuling", "Geely", "Chery", "Jetour", "DFSK", "GAC", "Neta", "Omoda", "Denza", "iCAR", "Hyundai"}  # brand Cina + Hyundai (konfirmasi user: NC3)
NC_UNCL = "Unclassified (New Car)"
NC_ORDER = ["NC1", "NC2", "NC3", NC_UNCL]

# New MCY: kode merek pada Marketing Proposal (/HOND/, /YAMA/). SMB = merek lain.
MCY_BRAND_CODE = {"HOND": "Honda", "YAMA": "Yamaha", "SUZU": "Suzuki", "PIAG": "Piaggio",
                  "POLY": "Polytron", "ALVA": "Alva", "QJMO": "QJ Motor"}
MCY_MAIN = {"HOND": "Honda", "YAMA": "Yamaha"}
NMCY_UNCL = "Unclassified (New MCY)"
NMCY_ORDER = ["Honda", "Yamaha", "SMB", NMCY_UNCL]
UNCL_LABEL = "Detail belum tersedia"

# Pembanding saja (tidak dipakai klasifikasi): kode MP mobil baru
NC_MP_CODE_REF = {"31R": "NC1", "32R": "NC2", "34R": "NC3"}

# ---------------- Dimension 3: Business Source ----------------
S_DEALER, S_DIRECT, S_NDS, S_CH, S_RE = "Dealer", "Direct Sales", "NDS", "Channeling", "Retention"
S_REFFO, S_OTHER = "REFFO", "Other"
SOURCE_ORDER = [S_DEALER, S_DIRECT, S_NDS, S_CH, S_RE, S_REFFO, S_OTHER]
SOURCE_RULES = [
    ("DLC mengandung 'CUST RETENTION' (CUST RETENTION MCY/CAR, ... MEDIATOR MCY/CAR)", S_RE),
    ("DLC mengandung 'NDS NON CHANNEL'", S_NDS),
    ("DLC mengandung 'NDS CHANNEL'", S_CH),
    ("DLC mengandung 'REFFO' (referral, tidak ada di daftar materi; ditampilkan terpisah)", S_REFFO),
    ("Sales Through = Dealer", S_DEALER),
    ("Sales Through = Direct Sales (di luar aturan di atas)", S_DIRECT),
    ("Lainnya", S_OTHER),
]

# ---- Brand / model family dari kata kunci pada Model (tidak ada kolom Brand di data) ----
# (brand, family, [kata kunci ter-normalisasi tanpa spasi/tanda baca])
_BRAND_FAMILIES = [
    # Motor - Honda
    *[("Honda", f, [f]) for f in ["BEAT", "VARIO", "PCX", "SCOOPY", "STYLO", "GENIO", "REVO", "SUPRA",
                                  "CRF", "CB150", "VERZA", "SONIC", "CBR", "ADV", "FORZA", "SPACY", "BLADE"]],
    # Motor - Yamaha
    *[("Yamaha", f, [f]) for f in ["NMAX", "AEROX", "FAZZIO", "LEXI", "MIO", "GEAR", "JUPITER", "FINO",
                                   "FILANO", "FREEGO", "XMAX", "VIXION", "R15", "XSR", "SOUL", "FASCINO",
                                   "VEGA", "MT15"]],
    # Motor - lain
    *[("Suzuki", f, [f]) for f in ["GSX", "SATRIA", "NEX", "ADDRESS", "BURGMAN", "SMASH", "SHOGUN", "AVENIS"]],
    *[("Kawasaki", f, [f]) for f in ["NINJA", "KLX", "W175", "VERSYS"]],
    ("Piaggio", "VESPA", ["VESPA", "PRIMAVERA", "SPRINT"]),
    ("Polytron", "FOX", ["FOX"]),
    # Mobil
    ("Toyota", "AVANZA", ["AVANZA"]), ("Toyota", "YARIS", ["YARIS"]),
    ("Toyota", "FORTUNER", ["FORTUNER", "FRTNR"]), ("Toyota", "INNOVA", ["INNOVA"]),
    ("Toyota", "CAMRY", ["CAMRY"]), ("Toyota", "VOXY", ["VOXY"]), ("Toyota", "VELLFIRE", ["VELLFIRE", "ALPHARD"]),
    ("Toyota", "ZENIX", ["ZENIX"]), ("Toyota", "RUSH", ["RUSH"]), ("Toyota", "RAIZE", ["RAIZE"]),
    ("Toyota", "CALYA", ["CALYA"]), ("Toyota", "AGYA", ["AGYA"]), ("Toyota", "ETIOS", ["ETIOS"]),
    ("Toyota", "VIOS", ["VIOS"]), ("Toyota", "HILUX", ["HILUX"]),
    ("Daihatsu", "SIGRA", ["SIGRA"]), ("Daihatsu", "GRANMAX", ["GRANMAX"]), ("Daihatsu", "AYLA", ["AYLA"]),
    ("Daihatsu", "TERIOS", ["TERIOS"]), ("Daihatsu", "XENIA", ["XENIA"]), ("Daihatsu", "SIRION", ["SIRION"]),
    ("Daihatsu", "LUXIO", ["LUXIO"]), ("Daihatsu", "ROCKY", ["ROCKY"]),
    ("Honda", "BRIO", ["BRIO"]), ("Honda", "JAZZ", ["JAZZ"]), ("Honda", "CRV", ["CRV"]),
    ("Honda", "HR-V", ["HRV"]), ("Honda", "MOBILIO", ["MOBILIO"]), ("Honda", "CIVIC", ["CIVIC"]),
    ("Honda", "CITY", ["CITY"]), ("Honda", "BR-V", ["BRV"]), ("Honda", "WR-V", ["WRV"]),
    ("Honda", "ACCORD", ["ACCORD"]), ("Honda", "FREED", ["FREED"]),
    ("Suzuki", "CARRY", ["CARRY"]), ("Suzuki", "ERTIGA", ["ERTIGA"]), ("Suzuki", "XL7", ["XL7"]),
    ("Suzuki", "FRONX", ["FRONX"]), ("Suzuki", "S-PRESSO", ["SPRESSO"]), ("Suzuki", "BALENO", ["BALENO"]),
    ("Suzuki", "APV", ["APV"]), ("Suzuki", "GRAND VITARA", ["VITARA"]), ("Suzuki", "JIMNY", ["JIMNY"]),
    ("Mitsubishi", "XPANDER", ["XPANDER"]), ("Mitsubishi", "PAJERO", ["PAJERO"]),
    ("Mitsubishi", "TRITON", ["TRITON"]), ("Mitsubishi", "XFORCE", ["XFORCE"]),
    ("Mitsubishi", "COLT DIESEL FE", ["FE74"]),
    ("Hyundai", "CRETA", ["CRETA"]), ("Hyundai", "STARGAZER", ["STARGAZER"]), ("Hyundai", "IONIQ", ["IONIQ"]),
    ("Mazda", "MAZDA2", ["MAZDA2"]), ("Mazda", "CX-5", ["CX5"]),
    ("Nissan", "MARCH", ["MARCH"]), ("Nissan", "GRAND LIVINA", ["LIVINA"]), ("Nissan", "TERRA", ["TERRA"]),
    ("Datsun", "DATSUN GO", ["DATSUN"]),
    ("Wuling", "AIRA", ["AIRA"]), ("Wuling", "ALMAZ", ["ALMAZ"]), ("Wuling", "ALVEZ", ["ALVEZ"]),
    ("BYD", "ATTO", ["ATTO"]), ("BYD", "SEAL", ["SEAL"]), ("BYD", "DOLPHIN", ["DOLPHIN"]),
    ("Geely", "EX5", ["EX5"]),
    ("iCAR", "V23", ["V23"]),
    ("Isuzu", "TRAGA", ["TRAGA"]), ("Isuzu", "ELF", ["ELF"]),
    ("Hino", "DUTRO", ["DUTRO", "HINO"]),
    ("Mercedes-Benz", "CLS", ["CLS"]),
]
BRAND_UNKNOWN = "Tidak teridentifikasi"

_KW = sorted(
    [(kw, brand, fam) for brand, fam, kws in _BRAND_FAMILIES for kw in kws],
    key=lambda t: -len(t[0]),
)


def _norm(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


def match_model(model) -> tuple:
    """Return (brand, family) berdasarkan kata kunci pada Model, atau (BRAND_UNKNOWN, model)."""
    n = _norm(model)
    for kw, brand, fam in _KW:
        if kw in n:
            return brand, fam
    return BRAND_UNKNOWN, str(model)


def _sel(conds, choices, default):
    """np.select yang aman untuk boolean nullable (NA -> False) di berbagai versi pandas."""
    arr = [np.asarray(pd.Series(c).fillna(False).astype(bool).to_numpy(), dtype=bool) for c in conds]
    return np.select(arr, choices, default=default)


def _clean_person(s: pd.Series) -> pd.Series:
    """Hapus ID numerik di depan nama (mis. '10005499  NORA W' -> 'NORA W')."""
    return s.astype("string").str.replace(r"^\s*\d+\s+", "", regex=True).str.strip()


def _clean_partner(s: pd.Series) -> pd.Series:
    t = s.astype("string").str.upper().str.strip()
    t = t.str.replace(r"^(CBD|CS)\s*[-_ ]\s*", "", regex=True)
    t = t.str.replace(r"^\d+\s*-\s*", "", regex=True)
    return t.str.replace(r"\s+", " ", regex=True).str.strip()


def _col(d, name):
    return d[name] if name in d.columns else pd.Series(pd.NA, index=d.index, dtype="string")


def classify_business_portfolio(df: pd.DataFrame) -> pd.DataFrame:
    """Tambah: portfolio (parent), wheel, business_portfolio (sub), brand, model_family, product-related."""
    d = df.copy()
    obj = _col(d, "Object").fillna("").astype("string").str.upper()
    prod = _col(d, "Jenis Produk").fillna("").astype("string").str.upper()
    mp = _col(d, "Marketing Proposal").astype("string")

    is_dff = prod.str.contains(DFF_KEYWORD, regex=False)
    parent = obj.map(OBJECT_TO_PORTFOLIO).fillna(P_OTHER)
    parent = parent.where(~(is_dff & parent.eq(P_MPL)), P_OTHER)
    d["portfolio"] = parent.astype(str)
    d["wheel"] = d["portfolio"].map(WHEEL_OF)
    d["is_dff"] = is_dff

    # brand & model family
    uniq = _col(d, "Model").fillna("").unique()
    mm = {m: match_model(m) for m in uniq}
    model = _col(d, "Model").fillna("")
    d["brand_kw"] = model.map(lambda m: mm[m][0])
    d["model_family"] = model.map(lambda m: mm[m][1])
    mcy_code = mp.str.extract(r"/([A-Z]{4})/")[0]
    d["mp_brand_code"] = mcy_code
    d["mp_nc_code"] = mp.str.extract(r"/(\d{2}R)/")[0]
    brand = d["brand_kw"].copy()
    code_brand = mcy_code.map(MCY_BRAND_CODE)
    use_code = d["portfolio"].eq(P_NMCY) & code_brand.notna()
    brand[use_code] = code_brand[use_code]
    d["brand"] = brand

    # sub-portfolio
    sub = d["portfolio"].copy()
    m = d["portfolio"].eq(P_NC)
    nc = _sel([d["brand_kw"].isin(NC1_BRANDS), d["brand_kw"].isin(NC2_BRANDS), d["brand_kw"].isin(NC3_BRANDS)],
                   ["NC1", "NC2", "NC3"], default=NC_UNCL)
    sub[m] = pd.Series(nc, index=d.index)[m]
    m = d["portfolio"].eq(P_NMCY)
    grp = mcy_code.map(MCY_MAIN)
    grp = grp.where(grp.notna(), np.where(mcy_code.notna(), "SMB", NMCY_UNCL))
    sub[m] = grp[m]
    m = d["portfolio"].eq(P_MPL)
    sub[m] = obj.map(MPL_UNIT)[m]
    d["business_portfolio"] = sub.astype(str)
    d["sub_unclassified"] = d["business_portfolio"].str.startswith("Unclassified") | d["portfolio"].eq(P_OTHER)
    d["mpl_unit"] = np.where(d["portfolio"].eq(P_MPL), d["business_portfolio"], "")
    return d


def classify_business_source(df: pd.DataFrame) -> pd.DataFrame:
    """Tambah: business_source, retention_category, partner, dlc_wheel (pembanding 2W/4W dari nama DLC)."""
    d = df.copy()
    dlc = _col(d, "DLC").fillna("").astype("string").str.upper()
    st_ = _col(d, "Sales Through").fillna("").astype("string").str.upper()
    conds = [dlc.str.contains("CUST RETENTION", regex=False), dlc.str.contains("NDS NON CHANNEL", regex=False),
             dlc.str.contains("NDS CHANNEL", regex=False), dlc.str.contains("REFFO", regex=False),
             st_.eq("DEALER"), st_.eq("DIRECT SALES")]
    d["business_source"] = _sel(conds, [S_RE, S_NDS, S_CH, S_REFFO, S_DEALER, S_DIRECT], default=S_OTHER)
    name = dlc.str.replace(r"^\d+\s*-\s*", "", regex=True)
    ret = name.str.replace("CUST RETENTION", "Customer Retention", regex=False).str.replace("MEDIATOR", "Mediator", regex=False)
    d["retention_category"] = np.where(d["business_source"].eq(S_RE), ret, "Bukan Retention")
    partner = _clean_partner(_col(d, "Ext Sales 1"))
    d["partner"] = partner.where(partner.notna() & (partner != ""), "Tanpa Ext Sales 1")
    d["dlc_wheel"] = _sel([dlc.str.contains(r"\bMCY\b", regex=True), dlc.str.contains(r"\bCAR\b", regex=True)],
                               ["2W", "4W"], default="")
    d["inisiator_name"] = _clean_person(_col(d, "Inisiator"))
    return d


def classify(df: pd.DataFrame) -> pd.DataFrame:
    return classify_business_source(classify_business_portfolio(df))