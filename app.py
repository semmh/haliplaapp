"""
=============================================================================
HALI ÜRETİM PLANLAMA UYGULAMASI  —  app.py  (v1.2)
=============================================================================
• Sidebar tamamen kaldırıldı
• Tüm girdiler ana sayfada st.expander içinde
=============================================================================
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from engine import (
    CONSTANTS,
    UretimGirdileri,
    HesaplamaSonuclari,
    dtex_to_nm,
    nm_to_dtex,
    ne_to_nm,
    fire_optimizasyon_simulasyonu,
    hesapla,
)


# ─────────────────────────────────────────────────────────────────────────────
# SAYFA AYARLARI  &  CSS
# ─────────────────────────────────────────────────────────────────────────────

def _sayfa_ayarlari() -> None:
    st.set_page_config(
        page_title="Halı Üretim Planlama",
        page_icon="🧶",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(_CSS, unsafe_allow_html=True)


_CSS = """
<style>
html, body, [class*="css"] { font-family: 'Segoe UI', sans-serif; }

/* Sidebar tamamen gizle */
[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }

.kpi-card {
    background: linear-gradient(135deg, var(--c1) 0%, var(--c2) 100%);
    padding: clamp(10px, 3vw, 20px);
    border-radius: 12px;
    color: #fff;
    text-align: center;
    box-shadow: 0 4px 15px rgba(0,0,0,.15);
    margin-bottom: 8px;
}
.kpi-value {
    font-size: clamp(1.2em, 4vw, 2em);
    font-weight: 700;
    margin: 6px 0;
    word-break: break-word;
}
.kpi-label {
    font-size: clamp(0.65em, 2vw, 0.82em);
    opacity: .88;
    text-transform: uppercase;
    letter-spacing: 1px;
}
.info-box {
    background:#d4edda; border-left:4px solid #28a745;
    padding:10px 14px; border-radius:6px; margin:8px 0; font-size:.9em;
}
.warn-box {
    background:#fff3cd; border-left:4px solid #ffc107;
    padding:10px 14px; border-radius:6px; margin:8px 0; font-size:.9em;
}
.formula-box {
    background:#eaf4ff; border-left:4px solid #2d6a9f;
    padding:12px 16px; border-radius:6px; margin:10px 0; font-size:.88em;
    word-break: break-word;
}
@media (max-width: 768px) {
    [data-testid="stDataFrame"] { overflow-x: auto !important; }
    [data-testid="metric-container"] { padding: 8px 4px; }
    .block-container { padding: 1rem 0.75rem !important; }
}
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# RENK PALETİ
# ─────────────────────────────────────────────────────────────────────────────

PALETTE = {
    "koyu_mavi":  "#1e3a5f",
    "orta_mavi":  "#2d6a9f",
    "turuncu":    "#e67e22",
    "yesil":      "#27ae60",
    "mor":        "#8e44ad",
    "acik_mavi":  "#2980b9",
}

RENK_PALETTE_LIST = [
    "#e74c3c","#3498db","#2ecc71","#f39c12",
    "#9b59b6","#1abc9c","#e67e22","#34495e",
    "#c0392b","#2980b9","#27ae60","#d35400",
    "#8e44ad","#16a085","#f1c40f","#7f8c8d",
]

PLOTLY_LAYOUT_BASE = dict(
    paper_bgcolor="white",
    plot_bgcolor="#f8f9fa",
    font=dict(family="Segoe UI, sans-serif"),
    margin=dict(t=70, b=50, l=50, r=20),
)


# ─────────────────────────────────────────────────────────────────────────────
# KPI KART HTML
# ─────────────────────────────────────────────────────────────────────────────

def _kpi(label: str, value: str, c1: str, c2: str) -> str:
    return (
        f'<div class="kpi-card" style="--c1:{c1};--c2:{c2};">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'</div>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# GİRDİLER — EXPANDER İÇİNDE ANA SAYFADA
# ─────────────────────────────────────────────────────────────────────────────

def _expander_girdileri() -> UretimGirdileri:
    with st.expander("⚙️ Üretim Parametreleri", expanded=True):

        st.markdown("##### 📐 Teknik Özellikler")
        c1, c2, c3 = st.columns(3)
        tarak_no     = c1.selectbox("Reed — diş/m", [200,300,400,500,600,700,800,1000,1200], index=4)
        atki_sikligi = c2.number_input("Pick — vuruş/m", 100, 2000, 700, 50)
        hav_yuksekligi = c3.slider("Hav Yüksekliği (mm)", 1.0, 30.0, 8.0, 0.5)

        c4, c5, c6 = st.columns(3)
        baglanti_payi = c4.slider("Bağlantı Payı (mm)", 1.0, 3.0, 1.5, 0.1)
        fire_orani    = c5.slider("Fire Oranı (%)", 5, 20, 10, 1) / 100.0
        high_bulk     = c6.slider("High-Bulk Faktörü", 1.05, 1.25, 1.12, 0.01)

        st.markdown("##### 🧵 İplik Özellikleri")
        c7, c8, c9, c10 = st.columns(4)
        iplik_birimi = c7.radio("Akrilik Birimi", ["dtex", "Nm"], horizontal=True)
        if iplik_birimi == "dtex":
            iplik_degeri = c8.number_input("dtex", 100.0, 10000.0, 1667.0, 50.0)
            nm_g = dtex_to_nm(iplik_degeri)
            c8.markdown(f'<div class="info-box">🔄 Nm {nm_g:.2f}</div>', unsafe_allow_html=True)
        else:
            iplik_degeri = c8.number_input("Nm", 1.0, 100.0, 6.0, 0.5)
            dtex_g = nm_to_dtex(iplik_degeri)
            c8.markdown(f'<div class="info-box">🔄 {dtex_g:.0f} dtex</div>', unsafe_allow_html=True)
        atki_iplik_ne  = c9.number_input("Atkı İpliği (Ne)", 1.0, 30.0, 8.0, 0.5)
        cozgu_iplik_nm = c10.number_input("Çözgü İpliği (Nm)", 1.0, 50.0, 10.0, 0.5)

        st.markdown("##### 🏭 Üretim Hedefi")
        c11, c12, c13, c14 = st.columns(4)
        hali_genisligi = c11.number_input("Genişlik (m)", 0.5, 6.0, 4.0, 0.1)
        toplam_metraj  = c12.number_input("Metraj (m)", 10, 100_000, 5000, 100)
        makine_hizi    = c13.number_input("Hız (RPM)", 50, 1000, 300, 10)
        verimlilik     = float(c14.slider("Verimlilik (%)", 50, 100, 80))

        st.markdown("##### 🎡 Cağlık  &  💰 Maliyet (TL/kg)")
        c15, c16, c17, c18, c19 = st.columns(5)
        creel_kapasitesi = c15.number_input("Cağlık (bobin)", 100, 20_000, 8000, 100)
        renk_sayisi      = c16.slider("Renk Sayısı", 1, 16, 8)
        iplik_fiyat      = c17.number_input("Akrilik ₺/kg", 0.0, 10_000.0, 85.0, 1.0)
        atki_fiyat       = c18.number_input("Atkı ₺/kg", 0.0, 1_000.0, 35.0, 1.0)
        cozgu_fiyat      = c19.number_input("Çözgü ₺/kg", 0.0, 1_000.0, 40.0, 1.0)

    return UretimGirdileri(
        tarak_no=tarak_no, atki_sikligi=atki_sikligi,
        hav_yuksekligi=hav_yuksekligi, baglanti_payi=baglanti_payi,
        fire_orani=fire_orani, high_bulk_faktoru=high_bulk,
        iplik_birimi=iplik_birimi, iplik_degeri=iplik_degeri,
        atki_iplik_ne=atki_iplik_ne, cozgu_iplik_nm=cozgu_iplik_nm,
        hali_genisligi=hali_genisligi, toplam_metraj=toplam_metraj,
        makine_hizi=makine_hizi, verimlilik=verimlilik,
        creel_kapasitesi=creel_kapasitesi, renk_sayisi=renk_sayisi,
        iplik_birim_fiyat=iplik_fiyat, atki_birim_fiyat=atki_fiyat,
        cozgu_birim_fiyat=cozgu_fiyat,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GRAFİK OLUŞTURUCULAR
# ─────────────────────────────────────────────────────────────────────────────

def _grafik_hammadde(s: HesaplamaSonuclari, metraj: float) -> go.Figure:
    kategoriler = ["Akrilik (Hav)", "Atkı İpliği", "Çözgü İpliği"]
    degerler    = [s.toplam_hav_kg, s.toplam_atki_kg, s.toplam_cozgu_kg]
    renkler     = [PALETTE["orta_mavi"], PALETTE["turuncu"], PALETTE["yesil"]]
    fig = go.Figure()
    for k, d, r in zip(kategoriler, degerler, renkler):
        fig.add_trace(go.Bar(
            name=k, x=[k], y=[d],
            marker_color=r,
            text=[f"{d:,.1f} kg"], textposition="outside",
            hovertemplate=f"<b>{k}</b><br>%{{y:,.2f}} kg<extra></extra>",
        ))
    fig.update_layout(
        **PLOTLY_LAYOUT_BASE,
        title=dict(text=f"📦 Hammadde Dağılımı — {metraj:,} m", x=0.5,
                   font=dict(size=15, color=PALETTE["koyu_mavi"])),
        yaxis_title="kg", showlegend=False, height=360, bargap=0.35,
    )
    fig.update_yaxes(gridcolor="#e0e0e0")
    return fig


def _grafik_sure_pasta(s: HesaplamaSonuclari) -> go.Figure:
    aktif = s.sure.dakika
    fig = go.Figure(go.Pie(
        labels=["Aktif Üretim", "Planlı Duruş", "Bakım & Hazırlık"],
        values=[aktif, aktif*0.12, aktif*0.08],
        marker_colors=[PALETTE["orta_mavi"], PALETTE["turuncu"], "#95a5a6"],
        hole=0.42, textinfo="label+percent",
        hovertemplate="<b>%{label}</b><br>%{value:,.0f} dk<extra></extra>",
    ))
    pasta_layout = {**PLOTLY_LAYOUT_BASE, "margin": dict(t=60, b=10, l=10, r=10)}
    fig.update_layout(
        **pasta_layout,
        title=dict(text=f"⏱️ Süre Dağılımı ({s.sure.saat:,.1f} saat)",
                   x=0.5, font=dict(size=14, color=PALETTE["koyu_mavi"])),
        height=340,
    )
    return fig


def _grafik_maliyet_pasta(s: HesaplamaSonuclari, g: UretimGirdileri) -> go.Figure:
    vals   = [s.maliyet.hav_maliyet, s.maliyet.atki_maliyet, s.maliyet.cozgu_maliyet]
    labels = ["Akrilik (Hav)", "Atkı İpliği", "Çözgü İpliği"]
    fig = go.Figure(go.Pie(
        labels=labels, values=vals,
        marker_colors=[PALETTE["orta_mavi"], PALETTE["turuncu"], PALETTE["yesil"]],
        hole=0.35,
        texttemplate="%{label}<br>%{percent}<br>₺%{value:,.0f}",
        hovertemplate="<b>%{label}</b><br>₺%{value:,.2f}<extra></extra>",
    ))
    pasta_layout = {**PLOTLY_LAYOUT_BASE, "margin": dict(t=60, b=10, l=10, r=10)}
    fig.update_layout(
        **pasta_layout,
        title=dict(text=f"💰 Maliyet Dağılımı — ₺{s.maliyet.toplam:,.0f}",
                   x=0.5, font=dict(size=14, color=PALETTE["koyu_mavi"])),
        height=340,
    )
    return fig


def _grafik_renk_bobin(renk_sayisi: int, renk_basi_bobin: int) -> go.Figure:
    renkler  = [f"Renk {chr(65+i)}" for i in range(renk_sayisi)]
    bobinler = [renk_basi_bobin] * renk_sayisi
    fig = go.Figure(go.Bar(
        x=renkler, y=bobinler,
        marker_color=RENK_PALETTE_LIST[:renk_sayisi],
        text=[f"{b:,}" for b in bobinler], textposition="outside",
        hovertemplate="<b>%{x}</b><br>%{y:,} bobin<extra></extra>",
    ))
    fig.update_layout(
        **PLOTLY_LAYOUT_BASE,
        title=dict(text=f"🎨 Renk Başına Bobin ({renk_sayisi} Renk)",
                   x=0.5, font=dict(size=14, color=PALETTE["koyu_mavi"])),
        yaxis_title="Bobin", showlegend=False, height=340,
    )
    return fig


def _grafik_haftalik(gunluk_m: float, toplam_m: float) -> go.Figure:
    haftalik_m   = gunluk_m * 7
    hafta_sayisi = min(max(1, int(toplam_m / haftalik_m) + 1), 12)
    hafta_data, kalan = [], toplam_m
    for h in range(1, hafta_sayisi + 1):
        bu_hafta = min(kalan, haftalik_m)
        if bu_hafta <= 0:
            break
        hafta_data.append({"Hafta": f"H{h}", "Üretim (m)": round(bu_hafta)})
        kalan -= bu_hafta
    df  = pd.DataFrame(hafta_data)
    fig = px.bar(df, x="Hafta", y="Üretim (m)",
                 color_discrete_sequence=[PALETTE["orta_mavi"]],
                 title="📅 Haftalık Üretim Planı", text="Üretim (m)")
    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
    fig.update_layout(**PLOTLY_LAYOUT_BASE, title_x=0.5, height=300, showlegend=False)
    return fig


def _grafik_optimizasyon(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["Hav (mm)"], y=df["Toplam (kg)"],
        mode="lines+markers+text", name="Toplam Tüketim (kg)",
        line=dict(color=PALETTE["orta_mavi"], width=2.5), marker=dict(size=8),
        text=df["Toplam (kg)"].apply(lambda v: f"{v:,.0f}"),
        textposition="top center", yaxis="y1",
    ))
    fig.add_trace(go.Bar(
        x=df["Hav (mm)"], y=df["Tasarruf (TL)"],
        name="Tasarruf (TL)",
        marker_color=PALETTE["yesil"], opacity=0.45, yaxis="y2",
    ))
    fig.update_layout(
        **PLOTLY_LAYOUT_BASE,
        title=dict(text="🔍 Hav Yüksekliği Optimizasyon Simülasyonu",
                   x=0.5, font=dict(size=14, color=PALETTE["koyu_mavi"])),
        xaxis_title="Hav Yüksekliği (mm)",
        yaxis =dict(title="Toplam Tüketim (kg)", side="left",  color=PALETTE["orta_mavi"]),
        yaxis2=dict(title="Tasarruf (TL)",        side="right", overlaying="y", color=PALETTE["yesil"]),
        legend=dict(orientation="h", y=1.14), height=400,
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# TAB RENDERLEYCILERI
# ─────────────────────────────────────────────────────────────────────────────

def _render_tab_hammadde(g: UretimGirdileri, s: HesaplamaSonuclari) -> None:
    st.markdown("#### 📋 Teknik & Hammadde Özeti")
    col_tablo, col_grafik = st.columns([5, 4], gap="medium")
    with col_tablo:
        rows = [
            ("Tarak (Reed)",      f"{g.tarak_no} diş/m"),
            ("Atkı (Pick)",       f"{g.atki_sikligi} vuruş/m"),
            ("Hav Yüksekliği",    f"{g.hav_yuksekligi} mm"),
            ("Bağlantı Payı",     f"{g.baglanti_payi} mm"),
            ("Fire Oranı",        f"%{g.fire_orani*100:.0f}"),
            ("High-Bulk Faktörü", f"{g.high_bulk_faktoru:.2f}"),
            ("Makine Genişliği",  f"{g.hali_genisligi} m"),
            ("Toplam Metraj",     f"{g.toplam_metraj:,} m"),
            ("Toplam Alan",       f"{s.alan_m2:,.0f} m²"),
            ("İplik (dtex)",      f"{s.dtex_degeri:,.0f} dtex"),
            ("İplik (Nm)",        f"Nm {s.nm_degeri:.2f}"),
            ("Atkı Nm",           f"Ne {g.atki_iplik_ne} → Nm {s.atki_nm:.2f}"),
            ("── SONUÇLAR ──",    "──────────"),
            ("Hav Tüketimi",      f"{s.hav_tuketim_kg_m2:.4f} kg/m²"),
            ("Toplam Hav (kg)",   f"{s.toplam_hav_kg:,.2f} kg"),
            ("Toplam Atkı (kg)",  f"{s.toplam_atki_kg:,.2f} kg"),
            ("Toplam Çözgü (kg)", f"{s.toplam_cozgu_kg:,.2f} kg"),
            ("TOPLAM HAMMADDE",   f"{s.toplam_iplik_kg:,.2f} kg"),
        ]
        st.dataframe(pd.DataFrame(rows, columns=["Parametre", "Değer"]),
                     use_container_width=True, hide_index=True, height=530)
    with col_grafik:
        st.plotly_chart(_grafik_hammadde(s, g.toplam_metraj), use_container_width=True)
        ilme_mm = 2 * g.hav_yuksekligi + g.baglanti_payi
        st.markdown(
            f'<div class="formula-box">'
            f'<b>ℹ️ Formül:</b><br>'
            f'<code>kg/m² = dtex × Reed × Pick × ilme[m] × fire × HB / 10⁷</code><br><br>'
            f'<b>Bu hesap:</b><br>'
            f'{s.dtex_degeri:.0f} × {g.tarak_no} × {g.atki_sikligi} × '
            f'{ilme_mm:.1f}mm × {1+g.fire_orani:.2f} × {g.high_bulk_faktoru:.2f}'
            f' = <b>{s.hav_tuketim_kg_m2:.4f} kg/m²</b>'
            f'</div>', unsafe_allow_html=True)


def _render_tab_cizelge(g: UretimGirdileri, s: HesaplamaSonuclari) -> None:
    col_l, col_r = st.columns(2, gap="medium")
    with col_l:
        st.markdown("#### ⏱️ Üretim Süresi")
        rows = [
            ("Toplam Dakika",     f"{s.sure.dakika:,.1f} dk"),
            ("Toplam Saat",       f"{s.sure.saat:,.2f} saat"),
            ("Takvim Günü (24h)", f"{s.sure.gun_24h:.2f} gün"),
            ("İş Günü (8h)",      f"{s.sure.is_gunu_8h:.1f} gün"),
            ("8h Vardiya Sayısı", f"{s.sure.vardiya_sayisi:.1f}"),
        ]
        st.dataframe(pd.DataFrame(rows, columns=["Ölçü", "Değer"]),
                     use_container_width=True, hide_index=True)
        st.markdown("#### 📈 Hız Göstergeleri")
        etk_rpm     = g.makine_hizi * g.verimlilik / 100
        m_saat_teo  = g.makine_hizi * 60 / g.atki_sikligi
        m_saat_grc  = etk_rpm * 60 / g.atki_sikligi
        rows2 = [
            ("Teorik RPM",        f"{g.makine_hizi} RPM"),
            ("Efektif RPM",       f"{etk_rpm:.0f} RPM"),
            ("m/saat (teorik)",   f"{m_saat_teo:.2f} m/saat"),
            ("m/saat (gerçek)",   f"{m_saat_grc:.2f} m/saat"),
            ("m/gün (3 vardiya)", f"{m_saat_grc*24:.1f} m/gün"),
        ]
        st.dataframe(pd.DataFrame(rows2, columns=["Gösterge", "Değer"]),
                     use_container_width=True, hide_index=True)
    with col_r:
        st.plotly_chart(_grafik_sure_pasta(s), use_container_width=True)
        gunluk_m = m_saat_grc * 24
        st.plotly_chart(_grafik_haftalik(gunluk_m, g.toplam_metraj), use_container_width=True)


def _render_tab_creel(g: UretimGirdileri, s: HesaplamaSonuclari) -> None:
    col_l, col_r = st.columns([2, 3], gap="medium")
    c = s.creel
    with col_l:
        st.markdown("#### 🎡 Cağlık Dizilim Planı")
        rows = [
            ("Toplam Diş",            f"{c.toplam_dis:,} diş"),
            ("Diş / Renk",            f"{c.renk_basi_dis:.0f}"),
            ("Bobin / Renk (×2 F2F)", f"{c.renk_basi_bobin:,}"),
            ("Toplam Bobin İhtiyacı", f"{c.toplam_bobin:,}"),
            ("Cağlık Kapasitesi",     f"{g.creel_kapasitesi:,}"),
            ("Kapasite Kullanımı",    f"%{c.kullanim_orani*100:.1f}"),
        ]
        st.dataframe(pd.DataFrame(rows, columns=["Parametre", "Değer"]),
                     use_container_width=True, hide_index=True)
        if c.kapasite_asimi:
            st.markdown(
                f'<div class="warn-box">⚠️ Hesaplanan bobin sayısı '
                f'({c.toplam_bobin:,}) cağlık kapasitesini '
                f'({g.creel_kapasitesi:,}) <b>aşıyor!</b></div>',
                unsafe_allow_html=True)
        else:
            st.success(f"✅ Kapasite yeterli ({c.toplam_bobin:,} / {g.creel_kapasitesi:,})")
        st.markdown(f"**Doluluk: %{c.kullanim_orani*100:.1f}**")
        st.progress(min(c.kullanim_orani, 1.0))
    with col_r:
        st.plotly_chart(_grafik_renk_bobin(g.renk_sayisi, c.renk_basi_bobin),
                        use_container_width=True)


def _render_tab_maliyet(g: UretimGirdileri, s: HesaplamaSonuclari) -> None:
    col_l, col_r = st.columns(2, gap="medium")
    with col_l:
        st.markdown("#### 💰 Maliyet Tablosu")
        m = s.maliyet
        maliyet_rows = [
            ("Akrilik (Hav)", f"{s.toplam_hav_kg:,.2f}",  f"₺{g.iplik_birim_fiyat:.2f}", f"₺{m.hav_maliyet:,.2f}"),
            ("Atkı İpliği",   f"{s.toplam_atki_kg:,.2f}",  f"₺{g.atki_birim_fiyat:.2f}",  f"₺{m.atki_maliyet:,.2f}"),
            ("Çözgü İpliği",  f"{s.toplam_cozgu_kg:,.2f}", f"₺{g.cozgu_birim_fiyat:.2f}", f"₺{m.cozgu_maliyet:,.2f}"),
            ("TOPLAM",        f"{s.toplam_iplik_kg:,.2f}", "—",                            f"₺{m.toplam:,.2f}"),
        ]
        st.dataframe(pd.DataFrame(maliyet_rows, columns=["Kalem","Miktar (kg)","₺/kg","Toplam"]),
                     use_container_width=True, hide_index=True)
        st.markdown(
            f'<div class="formula-box">'
            f'Alan: <b>{s.alan_m2:,.0f} m²</b> &nbsp;|&nbsp; '
            f'Maliyet/m²: <b>₺{m.maliyet_m2:,.2f}</b> &nbsp;|&nbsp; '
            f'Toplam: <b>₺{m.toplam:,.0f}</b>'
            f'</div>', unsafe_allow_html=True)
        st.markdown("#### 💹 Kâr Marjı Simülatörü")
        satis = st.number_input("Satış Fiyatı (₺/m²)", min_value=0.0,
                                value=float(round(m.maliyet_m2 * 1.30)), step=5.0)
        gelir = satis * s.alan_m2
        kar   = gelir - m.toplam
        marj  = (kar / gelir * 100) if gelir > 0 else 0.0
        c1, c2, c3 = st.columns(3)
        c1.metric("Toplam Gelir", f"₺{gelir:,.0f}")
        c2.metric("Kâr",          f"₺{kar:,.0f}", delta=f"%{marj:.1f}")
        c3.metric("Kâr Marjı",    f"%{marj:.1f}")
    with col_r:
        st.plotly_chart(_grafik_maliyet_pasta(s, g), use_container_width=True)
        st.markdown("#### ⚖️ İplik Ağırlık Oranları")
        oran_df = pd.DataFrame({
            "İplik": ["Akrilik", "Atkı", "Çözgü"],
            "%": [
                round(s.toplam_hav_kg   / s.toplam_iplik_kg * 100, 1),
                round(s.toplam_atki_kg  / s.toplam_iplik_kg * 100, 1),
                round(s.toplam_cozgu_kg / s.toplam_iplik_kg * 100, 1),
            ],
        })
        fig_oran = px.bar(oran_df, x="İplik", y="%", color="İplik",
                          color_discrete_sequence=[PALETTE["orta_mavi"], PALETTE["turuncu"], PALETTE["yesil"]],
                          text="%")
        fig_oran.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
        oran_layout = {**PLOTLY_LAYOUT_BASE, "margin": dict(t=30, b=40, l=40, r=10)}
        fig_oran.update_layout(**oran_layout, showlegend=False, height=260)
        st.plotly_chart(fig_oran, use_container_width=True)


def _render_tab_optimizasyon(g: UretimGirdileri, s: HesaplamaSonuclari) -> None:
    st.markdown("#### 🔍 Hav Yüksekliği Optimizasyon Simülasyonu")
    col_set1, col_set2 = st.columns(2)
    adim   = col_set1.selectbox("Adım Aralığı (mm)", [0.5, 1.0, 2.0], index=1)
    adim_n = col_set2.slider("Adım Sayısı", 2, 10, 5)
    opt = fire_optimizasyon_simulasyonu(
        s.dtex_degeri, g.tarak_no, g.atki_sikligi,
        g.hav_yuksekligi, g.baglanti_payi, g.fire_orani,
        g.high_bulk_faktoru, g.hali_genisligi, g.toplam_metraj,
        g.iplik_birim_fiyat, adim_mm=adim, adim_sayisi=adim_n,
    )
    opt_df = pd.DataFrame([{
        "Hav (mm)":      r.hav_mm,
        "Tüketim kg/m²": r.tuketim_kg_m2,
        "Toplam (kg)":   r.toplam_kg,
        "Tasarruf (kg)": r.tasarruf_kg,
        "Tasarruf (TL)": r.tasarruf_tl,
    } for r in opt])
    col_grafik, col_tablo = st.columns([3, 2], gap="medium")
    with col_grafik:
        st.plotly_chart(_grafik_optimizasyon(opt_df), use_container_width=True)
    with col_tablo:
        st.dataframe(opt_df.style.background_gradient(subset=["Tasarruf (TL)"], cmap="Greens"),
                     use_container_width=True, hide_index=True)
    max_idx  = opt_df["Tasarruf (TL)"].idxmax()
    en_dusuk = opt_df.loc[max_idx, "Hav (mm)"]
    max_tl   = opt_df.loc[max_idx, "Tasarruf (TL)"]
    st.success(
        f"💡 **Öneri:** Hav yüksekliğini **{en_dusuk} mm**'ye düşürerek "
        f"**₺{max_tl:,.2f}** tasarruf sağlanabilir."
    )


# ─────────────────────────────────────────────────────────────────────────────
# ANA FONKSİYON
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    _sayfa_ayarlari()

    st.title("🧶 Üretim Planlama")
    st.divider()

    # ── Girdiler (expander) ───────────────────────────────────────────────
    g = _expander_girdileri()
    s = hesapla(g)

    st.divider()

    # ── KPI Kartları ──────────────────────────────────────────────────────
    st.markdown("### 📊 Anahtar Göstergeler")
    kpi_cols = st.columns(5)
    kpis = [
        ("Toplam Hav İpliği", f"{s.toplam_hav_kg:,.1f} kg",  PALETTE["koyu_mavi"],  "#2d6a9f"),
        ("Toplam Hammadde",   f"{s.toplam_iplik_kg:,.1f} kg", "#1a5276",             "#2471a3"),
        ("Üretim Süresi",     f"{s.sure.gun_24h:.1f} gün",    "#784212",             PALETTE["turuncu"]),
        ("Toplam Maliyet",    f"₺{s.maliyet.toplam:,.0f}",    "#1e8449",             PALETTE["yesil"]),
        ("Maliyet / m²",      f"₺{s.maliyet.maliyet_m2:,.2f}","#6c3483",            PALETTE["mor"]),
    ]
    for col, (label, value, c1, c2) in zip(kpi_cols, kpis):
        col.markdown(_kpi(label, value, c1, c2), unsafe_allow_html=True)

    st.divider()

    # ── Sekmeler ──────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📦 Hammadde",
        "⏱️ Üretim Çizelgesi",
        "🎡 Cağlık Planı",
        "💰 Maliyet",
        "🔍 Optimizasyon",
    ])
    with tab1: _render_tab_hammadde(g, s)
    with tab2: _render_tab_cizelge(g, s)
    with tab3: _render_tab_creel(g, s)
    with tab4: _render_tab_maliyet(g, s)
    with tab5: _render_tab_optimizasyon(g, s)

    st.divider()
    st.caption("🧶 Akrilik Face-to-Face Halı Üretim Planlama v1.2 · Sidebar → Expander")


if __name__ == "__main__":
    main()