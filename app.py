"""
=============================================================================
HALI ÜRETİM PLANLAMA UYGULAMASI
Akrilik Face-to-Face Makine Halısı Üretim Planlama Sistemi
=============================================================================
Geliştirici: Tekstil Mühendisi & Kıdemli Python Geliştirici
Versiyon: 1.0.0
=============================================================================
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from dataclasses import dataclass
from typing import Dict, List, Tuple
import math

# ─────────────────────────────────────────────────────────────────────────────
# VERİ YAPILARI (Data Structures)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class UretimGirdileri:
    """Kullanıcıdan alınan tüm üretim parametrelerini tutan veri sınıfı."""
    # Teknik özellikler
    tarak_no: int           # Reed sayısı (diş/10cm)
    atki_sikligi: int       # Pick (vuruş/10cm)
    hav_yuksekligi: float   # mm cinsinden
    baglanti_payi: float    # mm cinsinden (1.5–2 mm)
    fire_orani: float       # Ondalık (örn: 0.10 = %10)

    # İplik özellikleri
    iplik_birimi: str       # "dtex" veya "Nm"
    iplik_degeri: float     # Girilen değer
    atki_iplik_ne: float    # Atkı ipliği numarası (Ne)
    cozgu_iplik_nm: float   # Çözgü ipliği numarası (Nm)

    # Üretim hedefleri
    hali_genisligi: float   # metre
    toplam_metraj: float    # metre
    makine_hizi: int        # RPM (devir/dakika)
    verimlilik: float       # 0–100 arası yüzde

    # Cağlık & renk
    creel_kapasitesi: int   # Toplam bobin yuvası
    renk_sayisi: int        # Kaç farklı renk kullanılıyor

    # Maliyet
    iplik_birim_fiyat: float  # TL/kg
    atki_birim_fiyat: float   # TL/kg
    cozgu_birim_fiyat: float  # TL/kg

    # Yüksek kabartma (High-Bulk) faktörü
    high_bulk_faktoru: float  # Genellikle 1.10–1.15


@dataclass
class HesaplamaSonuclari:
    """Tüm hesaplama çıktılarını tutan veri sınıfı."""
    # Hav ipliği tüketimi
    hav_tuketim_kg_m2: float
    toplam_hav_kg: float

    # Toplam hammadde
    toplam_atki_kg: float
    toplam_cozgu_kg: float
    toplam_iplik_kg: float

    # Üretim süresi
    toplam_dakika: float
    toplam_saat: float
    toplam_gun: float

    # Cağlık planı
    toplam_dis_sayisi: int
    renk_basi_bobin: int
    toplam_bobin: int

    # Maliyet
    toplam_maliyet: float
    maliyet_m2: float

    # İplik dönüşüm
    dtex_degeri: float
    nm_degeri: float


# ─────────────────────────────────────────────────────────────────────────────
# DÖNÜŞÜM FONKSİYONLARI (Unit Conversion)
# ─────────────────────────────────────────────────────────────────────────────

def dtex_to_nm(dtex: float) -> float:
    """dtex → Nm dönüşümü. Nm = 10000 / dtex"""
    return 10000.0 / dtex if dtex > 0 else 0.0

def nm_to_dtex(nm: float) -> float:
    """Nm → dtex dönüşümü. dtex = 10000 / Nm"""
    return 10000.0 / nm if nm > 0 else 0.0

def ne_to_nm(ne: float) -> float:
    """Ne (İngiliz pamuk sistemi) → Nm dönüşümü. Nm = Ne × 1.693"""
    return ne * 1.693

def nm_to_ne(nm: float) -> float:
    """Nm → Ne dönüşümü. Ne = Nm / 1.693"""
    return nm / 1.693


# ─────────────────────────────────────────────────────────────────────────────
# HESAPLAMA MOTORU (Calculation Engine)
# ─────────────────────────────────────────────────────────────────────────────

def hav_iplik_tuketimi_hesapla(
    dtex: float,
    reed: int,
    pick: int,
    hav_mm: float,
    baglanti_mm: float,
    fire_orani: float,
    high_bulk_faktoru: float
) -> float:
    """
    Hav ipliği tüketimini kg/m² cinsinden hesaplar.

    Formül:
        Tüketim (kg/m²) = [dtex × Reed × Pick × (2×Hav + Bağlantı) × (1 + fire)] 
                          × High-Bulk / 10_000_000

    Parametreler:
        dtex            : İplik inceliği (dtex)
        reed            : Tarak numarası (diş / 10 cm → metre için ×10)
        pick            : Atkı sıklığı (vuruş / 10 cm → metre için ×10)
        hav_mm          : Hav yüksekliği (mm)
        baglanti_mm     : Bağlantı payı (mm)
        fire_orani      : Ondalık fire (örn: 0.10)
        high_bulk_faktoru: Akrilik HB katsayısı (örn: 1.12)

    Döndürür:
        float: kg/m² cinsinden tüketim
    """
    # Reed ve Pick değerleri 10cm bazındadır; 1m² için ×10 gerek
    reed_m = reed * 10   # diş/m
    pick_m = pick * 10   # vuruş/m

    # İlme boyutu: 2×hav + bağlantı (mm), km'ye çevir → /1_000_000
    ilme_boyu_mm = (2 * hav_mm) + baglanti_mm

    # Ana formül (dtex/10_000_000 = kg/m iplik)
    tuketim = (dtex * reed_m * pick_m * ilme_boyu_mm * (1 + fire_orani) * high_bulk_faktoru) / 10_000_000_000

    return round(tuketim, 4)


def atki_iplik_hesapla(
    pick: int,
    genislik_m: float,
    metraj: float,
    atki_nm: float,
    fire_orani: float = 0.05
) -> float:
    """
    Atkı ipliği tüketimini kg cinsinden hesaplar.

    Formül: (Pick × 10 × Genişlik × Metraj) / (Nm × 1000) × (1 + fire)
    """
    pick_m = pick * 10  # vuruş/m
    toplam_atki_m = pick_m * metraj * genislik_m
    kg = toplam_atki_m / (atki_nm * 1000) * (1 + fire_orani)
    return round(kg, 2)


def cozgu_iplik_hesapla(
    reed: int,
    genislik_m: float,
    metraj: float,
    cozgu_nm: float,
    fire_orani: float = 0.05
) -> float:
    """
    Çözgü ipliği tüketimini kg cinsinden hesaplar.

    Formül: (Reed × 10 × Genişlik × Metraj) / (Nm × 1000) × (1 + fire)
    """
    reed_m = reed * 10  # diş/m
    toplam_cozgu_m = reed_m * genislik_m * metraj
    kg = toplam_cozgu_m / (cozgu_nm * 1000) * (1 + fire_orani)
    return round(kg, 2)


def uretim_suresi_hesapla(
    metraj: float,
    atki_sikligi: int,
    rpm: int,
    verimlilik_yuzde: float
) -> Tuple[float, float, float]:
    """
    Üretim süresini hesaplar.

    Formül: Süre (dakika) = (Metraj × Atkı_Sıklığı × 10) / (RPM × Verimlilik/100)

    Döndürür:
        Tuple[dakika, saat, gün]
    """
    if rpm <= 0 or verimlilik_yuzde <= 0:
        return 0.0, 0.0, 0.0

    # Atkı sıklığı vuruş/10cm → vuruş/m için ×10
    toplam_vurus = metraj * atki_sikligi * 10
    efektif_rpm = rpm * (verimlilik_yuzde / 100.0)

    dakika = toplam_vurus / efektif_rpm
    saat = dakika / 60.0
    gun = saat / 24.0

    return round(dakika, 1), round(saat, 2), round(gun, 2)


def calik_plani_hesapla(
    reed: int,
    genislik_m: float,
    renk_sayisi: int,
    creel_kapasitesi: int
) -> Dict:
    """
    Cağlık (Creel) dizilim planını hesaplar.

    Döndürür:
        Dict: toplam diş, renk başına bobin sayısı, uyarılar
    """
    toplam_dis = reed * 10 * genislik_m  # diş/m × genişlik
    toplam_dis = int(toplam_dis)

    if renk_sayisi <= 0:
        renk_sayisi = 1

    renk_basi_dis = toplam_dis / renk_sayisi
    renk_basi_bobin = math.ceil(renk_basi_dis)

    # Face-to-Face dokuma: her iki yüzey için ×2
    toplam_bobin = renk_basi_bobin * renk_sayisi * 2

    uyari = None
    if toplam_bobin > creel_kapasitesi:
        uyari = f"⚠️ Hesaplanan bobin sayısı ({toplam_bobin}) cağlık kapasitesini ({creel_kapasitesi}) aşıyor!"

    return {
        "toplam_dis": toplam_dis,
        "renk_basi_dis": round(renk_basi_dis, 1),
        "renk_basi_bobin": renk_basi_bobin,
        "toplam_bobin": toplam_bobin,
        "uyari": uyari
    }


def maliyet_hesapla(
    hav_kg: float,
    atki_kg: float,
    cozgu_kg: float,
    hav_fiyat: float,
    atki_fiyat: float,
    cozgu_fiyat: float,
    alan_m2: float
) -> Dict:
    """Toplam maliyeti ve m² bazlı maliyeti hesaplar."""
    hav_maliyet = hav_kg * hav_fiyat
    atki_maliyet = atki_kg * atki_fiyat
    cozgu_maliyet = cozgu_kg * cozgu_fiyat
    toplam = hav_maliyet + atki_maliyet + cozgu_maliyet

    return {
        "hav_maliyet": round(hav_maliyet, 2),
        "atki_maliyet": round(atki_maliyet, 2),
        "cozgu_maliyet": round(cozgu_maliyet, 2),
        "toplam": round(toplam, 2),
        "maliyet_m2": round(toplam / alan_m2, 2) if alan_m2 > 0 else 0
    }


def fire_optimizasyon_simulasyonu(
    dtex: float,
    reed: int,
    pick: int,
    hav_mm: float,
    baglanti_mm: float,
    fire_orani: float,
    high_bulk: float,
    genislik: float,
    metraj: float,
    hav_fiyat: float,
    adim_mm: float = 1.0,
    adim_sayisi: int = 5
) -> pd.DataFrame:
    """
    Hav yüksekliğini kademeli düşürerek tasarruf simülasyonu yapar.

    Döndürür:
        pd.DataFrame: Her hav yüksekliği için tüketim ve tasarruf
    """
    alan_m2 = genislik * metraj
    mevcut = hav_iplik_tuketimi_hesapla(dtex, reed, pick, hav_mm, baglanti_mm, fire_orani, high_bulk)
    mevcut_toplam = mevcut * alan_m2

    rows = []
    for i in range(adim_sayisi + 1):
        h = round(hav_mm - i * adim_mm, 1)
        if h <= 0:
            break
        tuketim = hav_iplik_tuketimi_hesapla(dtex, reed, pick, h, baglanti_mm, fire_orani, high_bulk)
        toplam = tuketim * alan_m2
        tasarruf_kg = mevcut_toplam - toplam
        tasarruf_tl = tasarruf_kg * hav_fiyat
        rows.append({
            "Hav Yüksekliği (mm)": h,
            "Tüketim (kg/m²)": tuketim,
            "Toplam Tüketim (kg)": round(toplam, 2),
            "Tasarruf (kg)": round(tasarruf_kg, 2),
            "Tasarruf (TL)": round(tasarruf_tl, 2)
        })

    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# SAYFA YAPISI & STREAMLIT ARAYÜZÜ
# ─────────────────────────────────────────────────────────────────────────────

def sayfa_ayarlari():
    """Streamlit sayfa yapılandırması."""
    st.set_page_config(
        page_title="Halı Üretim Planlama Sistemi",
        page_icon="🧶",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Özel CSS ile görünümü güzelleştir
    st.markdown("""
    <style>
        .metric-card {
            background: linear-gradient(135deg, #1e3a5f 0%, #2d6a9f 100%);
            padding: 20px;
            border-radius: 12px;
            color: white;
            text-align: center;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        }
        .metric-value {
            font-size: 2.2em;
            font-weight: 700;
            margin: 8px 0;
        }
        .metric-label {
            font-size: 0.85em;
            opacity: 0.85;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .warning-box {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 12px 16px;
            border-radius: 6px;
            margin: 10px 0;
        }
        .info-box {
            background: #d1ecf1;
            border-left: 4px solid #17a2b8;
            padding: 12px 16px;
            border-radius: 6px;
            margin: 10px 0;
        }
        .section-header {
            border-bottom: 2px solid #2d6a9f;
            padding-bottom: 8px;
            margin-bottom: 20px;
            color: #1e3a5f;
        }
    </style>
    """, unsafe_allow_html=True)


def sidebar_girdileri() -> UretimGirdileri:
    """Sidebar'dan tüm kullanıcı girdilerini toplar ve döndürür."""
    st.sidebar.image("https://img.icons8.com/fluency/96/carpet.png", width=80)
    st.sidebar.title("🧶 Üretim Parametreleri")

    # ── 1. TEKNİK ÖZELLİKLER ──────────────────────────────────────────────
    st.sidebar.markdown("### 📐 Teknik Özellikler")

    tarak_no = st.sidebar.selectbox(
        "Tarak Numarası (diş/10cm)",
        options=[400, 500, 600, 700, 800, 1000, 1200, 1400],
        index=2,
        help="Tezgah tarağındaki diş sayısı (10 cm başına)"
    )

    atki_sikligi = st.sidebar.number_input(
        "Atkı Sıklığı (vuruş/10cm)",
        min_value=100, max_value=2000, value=700, step=50,
        help="10 cm mesafedeki atkı ipliği geçiş sayısı"
    )

    hav_yuksekligi = st.sidebar.slider(
        "Hav Yüksekliği (mm)",
        min_value=1.0, max_value=30.0, value=8.0, step=0.5,
        help="Halının taban bezinden yüzey hav ipliği tepesine mesafe"
    )

    baglanti_payi = st.sidebar.slider(
        "Bağlantı Payı (mm)",
        min_value=1.0, max_value=3.0, value=1.5, step=0.1,
        help="Halı tabanındaki bağlantı ipliği payı (1.5-2 mm önerilen)"
    )

    fire_orani = st.sidebar.slider(
        "Fire Oranı (%)",
        min_value=5, max_value=20, value=10, step=1,
        help="Üretim sırasında ortaya çıkan iplik kayıp yüzdesi"
    ) / 100.0

    high_bulk_faktoru = st.sidebar.slider(
        "High-Bulk Faktörü",
        min_value=1.05, max_value=1.25, value=1.12, step=0.01,
        help="Akrilik ipliğin hacim kazanım katsayısı (HB özelliği)"
    )

    # ── 2. İPLİK ÖZELLİKLERİ ─────────────────────────────────────────────
    st.sidebar.markdown("### 🧵 İplik Özellikleri")

    iplik_birimi = st.sidebar.radio(
        "Akrilik İplik Numarası Birimi",
        options=["dtex", "Nm"],
        horizontal=True,
        help="dtex veya Nm; uygulama otomatik dönüşüm yapar"
    )

    if iplik_birimi == "dtex":
        iplik_degeri = st.sidebar.number_input(
            "İplik Numarası (dtex)",
            min_value=100.0, max_value=10000.0, value=1667.0, step=50.0,
            help="Örn: 1667 dtex ≈ Nm 6"
        )
    else:
        iplik_degeri = st.sidebar.number_input(
            "İplik Numarası (Nm)",
            min_value=1.0, max_value=100.0, value=6.0, step=0.5,
            help="Örn: Nm 6 ≈ 1667 dtex"
        )

    atki_iplik_ne = st.sidebar.number_input(
        "Atkı İpliği (Ne - Jüt/Pamuk)",
        min_value=1.0, max_value=30.0, value=8.0, step=0.5,
        help="Atkı ipliği İngiliz iplik numarası sistemi (Ne)"
    )

    cozgu_iplik_nm = st.sidebar.number_input(
        "Çözgü İpliği (Nm)",
        min_value=1.0, max_value=50.0, value=10.0, step=0.5,
        help="Çözgü ipliği metrik numara sistemi"
    )

    # ── 3. ÜRETİM HEDEFİ ─────────────────────────────────────────────────
    st.sidebar.markdown("### 🏭 Üretim Hedefi")

    hali_genisligi = st.sidebar.number_input(
        "Halı / Makine Genişliği (m)",
        min_value=0.5, max_value=6.0, value=4.0, step=0.1,
        help="Makinenin dokuma alanı genişliği"
    )

    toplam_metraj = st.sidebar.number_input(
        "Toplam Dokunacak Metraj (m)",
        min_value=10, max_value=100000, value=5000, step=100,
        help="Bu siparişte üretilecek toplam uzunluk"
    )

    makine_hizi = st.sidebar.number_input(
        "Makine Hızı (RPM)",
        min_value=50, max_value=1000, value=300, step=10,
        help="Dokuma makinesi devir/dakika hızı"
    )

    verimlilik = st.sidebar.slider(
        "Beklenen Verimlilik (%)",
        min_value=50, max_value=100, value=80, step=1,
        help="Makine çalışma verimliliği (duruşlar dahil)"
    )

    # ── 4. CAĞLIK PLANI ───────────────────────────────────────────────────
    st.sidebar.markdown("### 🎡 Cağlık (Creel) Planı")

    creel_kapasitesi = st.sidebar.number_input(
        "Cağlık Kapasitesi (bobin)",
        min_value=100, max_value=20000, value=8000, step=100,
        help="Makinenin kaldırabileceği toplam bobin sayısı"
    )

    renk_sayisi = st.sidebar.slider(
        "Renk Sayısı",
        min_value=1, max_value=16, value=8,
        help="Halıda kullanılacak renk çeşidi sayısı"
    )

    # ── 5. MALİYET ANALİZİ ───────────────────────────────────────────────
    st.sidebar.markdown("### 💰 Maliyet Analizi")

    iplik_birim_fiyat = st.sidebar.number_input(
        "Akrilik İplik Fiyatı (TL/kg)",
        min_value=0.0, max_value=10000.0, value=85.0, step=1.0
    )

    atki_birim_fiyat = st.sidebar.number_input(
        "Atkı İpliği Fiyatı (TL/kg)",
        min_value=0.0, max_value=1000.0, value=35.0, step=1.0
    )

    cozgu_birim_fiyat = st.sidebar.number_input(
        "Çözgü İpliği Fiyatı (TL/kg)",
        min_value=0.0, max_value=1000.0, value=40.0, step=1.0
    )

    return UretimGirdileri(
        tarak_no=tarak_no,
        atki_sikligi=atki_sikligi,
        hav_yuksekligi=hav_yuksekligi,
        baglanti_payi=baglanti_payi,
        fire_orani=fire_orani,
        high_bulk_faktoru=high_bulk_faktoru,
        iplik_birimi=iplik_birimi,
        iplik_degeri=iplik_degeri,
        atki_iplik_ne=atki_iplik_ne,
        cozgu_iplik_nm=cozgu_iplik_nm,
        hali_genisligi=hali_genisligi,
        toplam_metraj=toplam_metraj,
        makine_hizi=makine_hizi,
        verimlilik=float(verimlilik),
        creel_kapasitesi=creel_kapasitesi,
        renk_sayisi=renk_sayisi,
        iplik_birim_fiyat=iplik_birim_fiyat,
        atki_birim_fiyat=atki_birim_fiyat,
        cozgu_birim_fiyat=cozgu_birim_fiyat
    )


def hesaplamalari_calistir(g: UretimGirdileri) -> HesaplamaSonuclari:
    """Ana hesaplama motorunu çalıştırır ve sonuçları döndürür."""
    # İplik birim dönüşümü
    if g.iplik_birimi == "Nm":
        dtex = nm_to_dtex(g.iplik_degeri)
        nm   = g.iplik_degeri
    else:
        dtex = g.iplik_degeri
        nm   = dtex_to_nm(dtex)

    # Atkı ipliği Nm dönüşümü (Ne → Nm)
    atki_nm = ne_to_nm(g.atki_iplik_ne)

    # Toplam alan
    alan_m2 = g.hali_genisligi * g.toplam_metraj

    # Hav ipliği tüketimi
    hav_kg_m2 = hav_iplik_tuketimi_hesapla(
        dtex, g.tarak_no, g.atki_sikligi,
        g.hav_yuksekligi, g.baglanti_payi,
        g.fire_orani, g.high_bulk_faktoru
    )
    toplam_hav_kg = round(hav_kg_m2 * alan_m2, 2)

    # Atkı ve çözgü ipliği
    toplam_atki_kg = atki_iplik_hesapla(
        g.atki_sikligi, g.hali_genisligi, g.toplam_metraj,
        atki_nm, g.fire_orani * 0.5
    )
    toplam_cozgu_kg = cozgu_iplik_hesapla(
        g.tarak_no, g.hali_genisligi, g.toplam_metraj,
        g.cozgu_iplik_nm, g.fire_orani * 0.5
    )
    toplam_iplik_kg = round(toplam_hav_kg + toplam_atki_kg + toplam_cozgu_kg, 2)

    # Üretim süresi
    dakika, saat, gun = uretim_suresi_hesapla(
        g.toplam_metraj, g.atki_sikligi, g.makine_hizi, g.verimlilik
    )

    # Cağlık planı
    creel = calik_plani_hesapla(
        g.tarak_no, g.hali_genisligi, g.renk_sayisi, g.creel_kapasitesi
    )

    # Maliyet
    maliyet = maliyet_hesapla(
        toplam_hav_kg, toplam_atki_kg, toplam_cozgu_kg,
        g.iplik_birim_fiyat, g.atki_birim_fiyat, g.cozgu_birim_fiyat,
        alan_m2
    )

    return HesaplamaSonuclari(
        hav_tuketim_kg_m2=hav_kg_m2,
        toplam_hav_kg=toplam_hav_kg,
        toplam_atki_kg=toplam_atki_kg,
        toplam_cozgu_kg=toplam_cozgu_kg,
        toplam_iplik_kg=toplam_iplik_kg,
        toplam_dakika=dakika,
        toplam_saat=saat,
        toplam_gun=gun,
        toplam_dis_sayisi=creel["toplam_dis"],
        renk_basi_bobin=creel["renk_basi_bobin"],
        toplam_bobin=creel["toplam_bobin"],
        toplam_maliyet=maliyet["toplam"],
        maliyet_m2=maliyet["maliyet_m2"],
        dtex_degeri=dtex,
        nm_degeri=nm
    )


# ─────────────────────────────────────────────────────────────────────────────
# GÖRSEL BİLEŞENLER (Visual Components)
# ─────────────────────────────────────────────────────────────────────────────

def kpi_karti(label: str, value: str, renk: str = "#2d6a9f") -> str:
    """Anahtar gösterge (KPI) kartı HTML döndürür."""
    return f"""
    <div style="background: linear-gradient(135deg, {renk} 0%, {renk}cc 100%);
                padding: 20px; border-radius: 12px; color: white;
                text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.15);
                margin: 5px;">
        <div style="font-size:0.8em; opacity:0.85; text-transform:uppercase;
                    letter-spacing:1px; margin-bottom:8px;">{label}</div>
        <div style="font-size:1.9em; font-weight:700;">{value}</div>
    </div>
    """


def uretim_cizelgesi_grafigi(s: HesaplamaSonuclari, g: UretimGirdileri) -> go.Figure:
    """Üretim çizelgesi bar grafiği oluşturur."""
    kategoriler = ["Hav İpliği\n(Akrilik)", "Atkı İpliği\n(Jüt/Pamuk)", "Çözgü İpliği"]
    degerler = [s.toplam_hav_kg, s.toplam_atki_kg, s.toplam_cozgu_kg]
    renkler = ["#2d6a9f", "#e67e22", "#27ae60"]

    fig = go.Figure()

    for kat, deg, renk in zip(kategoriler, degerler, renkler):
        fig.add_trace(go.Bar(
            name=kat.replace("\n", " "),
            x=[kat],
            y=[deg],
            marker_color=renk,
            text=[f"{deg:,.1f} kg"],
            textposition="outside",
            hovertemplate=f"<b>{kat}</b><br>Miktar: {{y:,.2f}} kg<extra></extra>"
        ))

    fig.update_layout(
        title={
            "text": f"📦 Hammadde Tüketim Dağılımı — Toplam {g.toplam_metraj:,} m",
            "x": 0.5,
            "font": {"size": 16, "color": "#1e3a5f"}
        },
        yaxis_title="Miktar (kg)",
        xaxis_title="İplik Türü",
        showlegend=False,
        plot_bgcolor="#f8f9fa",
        paper_bgcolor="white",
        height=400,
        bargap=0.35,
        margin=dict(t=80, b=60, l=60, r=20)
    )

    fig.update_yaxes(gridcolor="#e0e0e0", gridwidth=0.5)

    return fig


def sure_dagitim_grafigi(s: HesaplamaSonuclari) -> go.Figure:
    """Üretim süresi pasta grafiği (8 saatlik vardiyalara göre)."""
    vardiya_sayisi = s.toplam_saat / 8
    toplam_gun_8h = s.toplam_saat / 8 / 3  # 3 vardiya / gün

    fig = go.Figure(go.Pie(
        labels=["Aktif Üretim", "Planlanan Duruş", "Bakım & Hazırlık"],
        values=[
            s.toplam_dakika,
            s.toplam_dakika * (1 - 0.80) * 0.6,
            s.toplam_dakika * (1 - 0.80) * 0.4
        ],
        marker_colors=["#2d6a9f", "#e67e22", "#95a5a6"],
        hole=0.4,
        textinfo="label+percent",
        hovertemplate="<b>%{label}</b><br>%{value:,.0f} dk<extra></extra>"
    ))

    fig.update_layout(
        title={
            "text": f"⏱️ Süre Dağılımı ({s.toplam_saat:,.1f} saat toplam)",
            "x": 0.5,
            "font": {"size": 15, "color": "#1e3a5f"}
        },
        height=350,
        margin=dict(t=70, b=20, l=20, r=20)
    )

    return fig


def maliyet_grafigi(s: HesaplamaSonuclari, g: UretimGirdileri) -> go.Figure:
    """Maliyet bileşenleri görselleştirmesi."""
    hav_m   = s.toplam_hav_kg   * g.iplik_birim_fiyat
    atki_m  = s.toplam_atki_kg  * g.atki_birim_fiyat
    cozgu_m = s.toplam_cozgu_kg * g.cozgu_birim_fiyat

    fig = go.Figure(go.Pie(
        labels=["Akrilik (Hav)", "Atkı İpliği", "Çözgü İpliği"],
        values=[hav_m, atki_m, cozgu_m],
        marker_colors=["#2d6a9f", "#e67e22", "#27ae60"],
        hole=0.35,
        textinfo="label+percent+value",
        texttemplate="%{label}<br>%{percent}<br>₺%{value:,.0f}",
        hovertemplate="<b>%{label}</b><br>Maliyet: ₺%{value:,.2f}<extra></extra>"
    ))

    fig.update_layout(
        title={
            "text": f"💰 Maliyet Dağılımı — Toplam ₺{s.toplam_maliyet:,.2f}",
            "x": 0.5,
            "font": {"size": 15, "color": "#1e3a5f"}
        },
        height=350,
        margin=dict(t=70, b=20, l=20, r=20)
    )

    return fig


def fire_optimizasyon_grafigi(df: pd.DataFrame) -> go.Figure:
    """Fire optimizasyon simülasyon grafiği."""
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["Hav Yüksekliği (mm)"],
        y=df["Toplam Tüketim (kg)"],
        mode="lines+markers+text",
        name="Toplam Tüketim",
        line=dict(color="#2d6a9f", width=2.5),
        marker=dict(size=8, color="#2d6a9f"),
        text=df["Toplam Tüketim (kg)"].apply(lambda x: f"{x:,.0f}kg"),
        textposition="top center",
        yaxis="y1"
    ))

    fig.add_trace(go.Bar(
        x=df["Hav Yüksekliği (mm)"],
        y=df["Tasarruf (TL)"],
        name="Tasarruf (TL)",
        marker_color="#27ae60",
        opacity=0.5,
        yaxis="y2"
    ))

    fig.update_layout(
        title={
            "text": "🔍 Hav Yüksekliği Optimizasyon Simülasyonu",
            "x": 0.5,
            "font": {"size": 15, "color": "#1e3a5f"}
        },
        xaxis_title="Hav Yüksekliği (mm)",
        yaxis=dict(title="Toplam Tüketim (kg)", side="left", color="#2d6a9f"),
        yaxis2=dict(title="Tasarruf (TL)", side="right", overlaying="y", color="#27ae60"),
        legend=dict(orientation="h", y=1.12),
        plot_bgcolor="#f8f9fa",
        height=400,
        margin=dict(t=80, b=60)
    )

    return fig


# ─────────────────────────────────────────────────────────────────────────────
# ANA UYGULAMA (Main App)
# ─────────────────────────────────────────────────────────────────────────────

def main():
    sayfa_ayarlari()

    # ── BAŞLIK ──────────────────────────────────────────────────────────────
    st.title("🧶 Akrilik Halı Üretim Planlama Sistemi")
    st.markdown(
        "**Face-to-Face Makine Halısı** | Hammadde · Zaman · Maliyet · Cağlık Planlaması"
    )
    st.divider()

    # Sidebar girdilerini al
    g = sidebar_girdileri()

    # ── İPLİK DÖNÜŞÜM GÖSTERGESI ────────────────────────────────────────────
    if g.iplik_birimi == "dtex":
        dtex_goster = g.iplik_degeri
        nm_goster   = dtex_to_nm(g.iplik_degeri)
    else:
        nm_goster   = g.iplik_degeri
        dtex_goster = nm_to_dtex(g.iplik_degeri)

    st.sidebar.markdown(
        f"<div class='info-box' style='background:#d4edda;border-color:#28a745'>"
        f"🔄 <b>Dönüşüm:</b> {dtex_goster:.0f} dtex = Nm {nm_goster:.2f}</div>",
        unsafe_allow_html=True
    )

    # ── HESAPLAMA ────────────────────────────────────────────────────────────
    s = hesaplamalari_calistir(g)
    alan_m2 = g.hali_genisligi * g.toplam_metraj
    atki_nm = ne_to_nm(g.atki_iplik_ne)

    creel_data = calik_plani_hesapla(
        g.tarak_no, g.hali_genisligi, g.renk_sayisi, g.creel_kapasitesi
    )
    maliyet_data = maliyet_hesapla(
        s.toplam_hav_kg, s.toplam_atki_kg, s.toplam_cozgu_kg,
        g.iplik_birim_fiyat, g.atki_birim_fiyat, g.cozgu_birim_fiyat,
        alan_m2
    )

    # ── KPI KARTLARI (ÜST BÖLÜM) ────────────────────────────────────────────
    st.markdown("### 📊 Anahtar Göstergeler")
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.markdown(kpi_karti("Toplam Hav İpliği", f"{s.toplam_hav_kg:,.1f} kg", "#1e3a5f"), unsafe_allow_html=True)
    with col2:
        st.markdown(kpi_karti("Toplam Hammadde", f"{s.toplam_iplik_kg:,.1f} kg", "#2980b9"), unsafe_allow_html=True)
    with col3:
        st.markdown(kpi_karti("Tahmini Süre", f"{s.toplam_gun:.1f} gün", "#e67e22"), unsafe_allow_html=True)
    with col4:
        st.markdown(kpi_karti("Toplam Maliyet", f"₺{s.toplam_maliyet:,.0f}", "#27ae60"), unsafe_allow_html=True)
    with col5:
        st.markdown(kpi_karti("Maliyet / m²", f"₺{s.maliyet_m2:,.2f}", "#8e44ad"), unsafe_allow_html=True)

    st.divider()

    # ── SEKMELER ────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📦 Hammadde & Teknik",
        "⏱️ Üretim Çizelgesi",
        "🎡 Cağlık Planı",
        "💰 Maliyet Analizi",
        "🔍 Optimizasyon"
    ])

    # ═══════════════════════════════════════════════════════════════════
    # TAB 1: HAMMADDE & TEKNİK
    # ═══════════════════════════════════════════════════════════════════
    with tab1:
        col_a, col_b = st.columns([3, 2])

        with col_a:
            st.markdown("#### 📋 Teknik ve Hammadde Özeti")
            teknik_df = pd.DataFrame({
                "Parametre": [
                    "Tarak Numarası", "Atkı Sıklığı", "Hav Yüksekliği",
                    "Bağlantı Payı", "Fire Oranı", "High-Bulk Faktörü",
                    "Makine Genişliği", "Toplam Metraj", "Toplam Alan",
                    "İplik Numarası (dtex)", "İplik Numarası (Nm)",
                    "Atkı İpliği (Ne → Nm)",
                    "─── SONUÇLAR ───", 
                    "Hav Tüketimi (kg/m²)",
                    "Toplam Hav İpliği (kg)",
                    "Toplam Atkı İpliği (kg)",
                    "Toplam Çözgü İpliği (kg)",
                    "TOPLAM HAMMADDE (kg)"
                ],
                "Değer": [
                    f"{g.tarak_no} diş/10cm",
                    f"{g.atki_sikligi} vuruş/10cm",
                    f"{g.hav_yuksekligi} mm",
                    f"{g.baglanti_payi} mm",
                    f"%{g.fire_orani*100:.0f}",
                    f"{g.high_bulk_faktoru:.2f}",
                    f"{g.hali_genisligi} m",
                    f"{g.toplam_metraj:,} m",
                    f"{alan_m2:,.0f} m²",
                    f"{s.dtex_degeri:,.0f} dtex",
                    f"Nm {s.nm_degeri:.2f}",
                    f"Ne {g.atki_iplik_ne} → Nm {atki_nm:.2f}",
                    "──────────────",
                    f"{s.hav_tuketim_kg_m2:.4f} kg/m²",
                    f"{s.toplam_hav_kg:,.2f} kg",
                    f"{s.toplam_atki_kg:,.2f} kg",
                    f"{s.toplam_cozgu_kg:,.2f} kg",
                    f"{s.toplam_iplik_kg:,.2f} kg"
                ]
            })
            st.dataframe(teknik_df, use_container_width=True, hide_index=True, height=540)

        with col_b:
            st.plotly_chart(uretim_cizelgesi_grafigi(s, g), use_container_width=True)

            st.markdown(
                f"""<div style='background:#eaf4ff;border-left:4px solid #2d6a9f;
                    padding:14px;border-radius:6px;margin-top:10px;'>
                    <b>ℹ️ Formül Özeti:</b><br>
                    <code>kg/m² = (dtex × Reed × Pick × (2×Hav + Bağlantı) × (1+Fire) × HB) / 10¹⁰</code><br><br>
                    <b>Hesaplama:</b><br>
                    dtex={s.dtex_degeri:.0f} × {g.tarak_no*10} × {g.atki_sikligi*10} × 
                    ({2*g.hav_yuksekligi+g.baglanti_payi:.1f}mm) × {1+g.fire_orani:.2f} × {g.high_bulk_faktoru:.2f}
                    = <b>{s.hav_tuketim_kg_m2:.4f} kg/m²</b>
                </div>""",
                unsafe_allow_html=True
            )

    # ═══════════════════════════════════════════════════════════════════
    # TAB 2: ÜRETİM ÇİZELGESİ
    # ═══════════════════════════════════════════════════════════════════
    with tab2:
        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("#### ⏱️ Üretim Süresi Detayları")
            sure_df = pd.DataFrame({
                "Süre Birimi": [
                    "Toplam Dakika", "Toplam Saat", "Toplam Gün (24h)",
                    "İş Günü (8h/gün)", "Vardiya (8h) Sayısı",
                    "3 Vardiyalı Gün"
                ],
                "Değer": [
                    f"{s.toplam_dakika:,.1f} dk",
                    f"{s.toplam_saat:,.2f} saat",
                    f"{s.toplam_gun:.2f} gün",
                    f"{s.toplam_saat/8:,.1f} iş günü",
                    f"{s.toplam_saat/8:,.1f} vardiya",
                    f"{s.toplam_saat/24:,.1f} gün"
                ]
            })
            st.dataframe(sure_df, use_container_width=True, hide_index=True)

            # Üretim hızı
            st.markdown("#### 📈 Üretim Hızı Göstergeleri")
            hiz_df = pd.DataFrame({
                "Gösterge": [
                    "Teorik Hız (RPM)",
                    "Efektif Hız (Verimlilik)",
                    "m/saat (teorik)",
                    "m/saat (gerçek)",
                    "m/gün (3 vardiya)"
                ],
                "Değer": [
                    f"{g.makine_hizi} RPM",
                    f"{g.makine_hizi * g.verimlilik/100:.0f} RPM",
                    f"{g.makine_hizi * 60 / (g.atki_sikligi * 10):.2f} m/saat",
                    f"{g.makine_hizi * g.verimlilik/100 * 60 / (g.atki_sikligi * 10):.2f} m/saat",
                    f"{g.makine_hizi * g.verimlilik/100 * 60 * 24 / (g.atki_sikligi * 10):.1f} m/gün"
                ]
            })
            st.dataframe(hiz_df, use_container_width=True, hide_index=True)

        with col_b:
            st.plotly_chart(sure_dagitim_grafigi(s), use_container_width=True)

            # Gantt-benzeri üretim çizelgesi
            st.markdown("#### 📅 Haftalık Üretim Planı")
            gunluk_m = g.makine_hizi * g.verimlilik/100 * 60 * 24 / (g.atki_sikligi * 10)
            hafta_sayisi = math.ceil(s.toplam_gun / 7)

            hafta_data = []
            kalan = g.toplam_metraj
            for hafta in range(1, min(hafta_sayisi + 1, 9)):
                bu_hafta = min(kalan, gunluk_m * 7)
                hafta_data.append({
                    "Hafta": f"Hafta {hafta}",
                    "Üretim (m)": round(bu_hafta, 0),
                    "Kümülatif (m)": round(g.toplam_metraj - max(0, kalan - bu_hafta), 0)
                })
                kalan -= bu_hafta

            hafta_df = pd.DataFrame(hafta_data)
            fig_hafta = px.bar(
                hafta_df, x="Hafta", y="Üretim (m)",
                color_discrete_sequence=["#2d6a9f"],
                title="Haftalık Üretim Dağılımı"
            )
            fig_hafta.update_layout(height=280, margin=dict(t=50, b=40))
            st.plotly_chart(fig_hafta, use_container_width=True)

    # ═══════════════════════════════════════════════════════════════════
    # TAB 3: CAĞLIK PLANI
    # ═══════════════════════════════════════════════════════════════════
    with tab3:
        st.markdown("#### 🎡 Cağlık (Creel) Dizilim Planı")

        col_a, col_b = st.columns([2, 3])

        with col_a:
            creel_ozet = pd.DataFrame({
                "Parametre": [
                    "Toplam Diş Sayısı",
                    "Diş / Renk",
                    "Bobin / Renk (×2 yüzey)",
                    "Toplam Bobin İhtiyacı",
                    "Cağlık Kapasitesi",
                    "Kapasite Kullanımı"
                ],
                "Değer": [
                    f"{creel_data['toplam_dis']:,} diş",
                    f"{creel_data['renk_basi_dis']:.0f} diş/renk",
                    f"{creel_data['renk_basi_bobin']:,} bobin/renk",
                    f"{creel_data['toplam_bobin']:,} bobin",
                    f"{g.creel_kapasitesi:,} bobin",
                    f"%{creel_data['toplam_bobin']/g.creel_kapasitesi*100:.1f}"
                ]
            })
            st.dataframe(creel_ozet, use_container_width=True, hide_index=True)

            if creel_data["uyari"]:
                st.markdown(
                    f"<div class='warning-box'>{creel_data['uyari']}</div>",
                    unsafe_allow_html=True
                )
            else:
                st.success(f"✅ Cağlık kapasitesi yeterli! ({creel_data['toplam_bobin']:,}/{g.creel_kapasitesi:,})")

        with col_b:
            # Renk bazlı bobin dağılımı grafiği
            renkler_listesi = [f"Renk {chr(65+i)}" for i in range(g.renk_sayisi)]
            bobin_listesi = [creel_data["renk_basi_bobin"]] * g.renk_sayisi

            renk_palette = [
                "#e74c3c", "#3498db", "#2ecc71", "#f39c12",
                "#9b59b6", "#1abc9c", "#e67e22", "#34495e",
                "#c0392b", "#2980b9", "#27ae60", "#d35400",
                "#8e44ad", "#16a085", "#f1c40f", "#7f8c8d"
            ]

            fig_renk = go.Figure(go.Bar(
                x=renkler_listesi,
                y=bobin_listesi,
                marker_color=renk_palette[:g.renk_sayisi],
                text=[f"{b:,}" for b in bobin_listesi],
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>Bobin: %{y:,}<extra></extra>"
            ))

            fig_renk.update_layout(
                title=f"🎨 Renk Başına Bobin Dağılımı ({g.renk_sayisi} Renk)",
                yaxis_title="Bobin Sayısı",
                plot_bgcolor="#f8f9fa",
                height=380,
                margin=dict(t=60, b=50)
            )
            st.plotly_chart(fig_renk, use_container_width=True)

        # Cağlık kapasitesi doluluk göstergesi
        kullanim = min(creel_data["toplam_bobin"] / g.creel_kapasitesi, 1.0)
        st.markdown(f"**Cağlık Doluluk Oranı: %{kullanim*100:.1f}**")
        st.progress(kullanim)

    # ═══════════════════════════════════════════════════════════════════
    # TAB 4: MALİYET ANALİZİ
    # ═══════════════════════════════════════════════════════════════════
    with tab4:
        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("#### 💰 Maliyet Detay Tablosu")
            maliyet_df = pd.DataFrame({
                "Kalem": [
                    "Akrilik İplik (Hav)",
                    "Atkı İpliği",
                    "Çözgü İpliği",
                    "─────────",
                    "TOPLAM"
                ],
                "Miktar (kg)": [
                    f"{s.toplam_hav_kg:,.2f}",
                    f"{s.toplam_atki_kg:,.2f}",
                    f"{s.toplam_cozgu_kg:,.2f}",
                    "─",
                    f"{s.toplam_iplik_kg:,.2f}"
                ],
                "Birim Fiyat (TL/kg)": [
                    f"₺{g.iplik_birim_fiyat:.2f}",
                    f"₺{g.atki_birim_fiyat:.2f}",
                    f"₺{g.cozgu_birim_fiyat:.2f}",
                    "─",
                    "─"
                ],
                "Toplam Maliyet (TL)": [
                    f"₺{maliyet_data['hav_maliyet']:,.2f}",
                    f"₺{maliyet_data['atki_maliyet']:,.2f}",
                    f"₺{maliyet_data['cozgu_maliyet']:,.2f}",
                    "─────────",
                    f"₺{s.toplam_maliyet:,.2f}"
                ]
            })
            st.dataframe(maliyet_df, use_container_width=True, hide_index=True)

            # m² maliyet özeti
            st.markdown(
                f"""<div style='background:#eaf4ff;border-left:4px solid #27ae60;
                    padding:16px;border-radius:8px;margin-top:10px;'>
                    <b>📐 Alan Bazlı Maliyet:</b><br>
                    Toplam Alan: <b>{alan_m2:,.0f} m²</b><br>
                    Maliyet / m²: <b>₺{s.maliyet_m2:,.2f}</b><br>
                    Toplam Maliyet: <b>₺{s.toplam_maliyet:,.2f}</b>
                </div>""",
                unsafe_allow_html=True
            )

            # Kâr marjı hesabı
            st.markdown("#### 💹 Kâr Marjı Simülatörü")
            satis_fiyati_m2 = st.number_input(
                "Satış Fiyatı (TL/m²)",
                min_value=0.0, value=float(round(s.maliyet_m2 * 1.3, 0)), step=10.0
            )
            toplam_gelir = satis_fiyati_m2 * alan_m2
            kar = toplam_gelir - s.toplam_maliyet
            kar_marji = (kar / toplam_gelir * 100) if toplam_gelir > 0 else 0

            c1, c2, c3 = st.columns(3)
            c1.metric("Toplam Gelir", f"₺{toplam_gelir:,.0f}")
            c2.metric("Kâr", f"₺{kar:,.0f}", delta=f"%{kar_marji:.1f}")
            c3.metric("Kâr Marjı", f"%{kar_marji:.1f}")

        with col_b:
            st.plotly_chart(maliyet_grafigi(s, g), use_container_width=True)

            # İplik oranları
            st.markdown("#### ⚖️ İplik Ağırlık Oranları")
            oran_df = pd.DataFrame({
                "İplik Türü": ["Akrilik (Hav)", "Atkı", "Çözgü"],
                "Oran (%)": [
                    round(s.toplam_hav_kg / s.toplam_iplik_kg * 100, 1),
                    round(s.toplam_atki_kg / s.toplam_iplik_kg * 100, 1),
                    round(s.toplam_cozgu_kg / s.toplam_iplik_kg * 100, 1)
                ]
            })
            fig_oran = px.bar(
                oran_df, x="İplik Türü", y="Oran (%)",
                color="İplik Türü",
                color_discrete_sequence=["#2d6a9f", "#e67e22", "#27ae60"],
                text="Oran (%)"
            )
            fig_oran.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            fig_oran.update_layout(showlegend=False, height=280, margin=dict(t=30, b=40))
            st.plotly_chart(fig_oran, use_container_width=True)

    # ═══════════════════════════════════════════════════════════════════
    # TAB 5: OPTİMİZASYON
    # ═══════════════════════════════════════════════════════════════════
    with tab5:
        st.markdown("#### 🔍 Hav Yüksekliği Fire Optimizasyon Simülasyonu")
        st.markdown(
            "Hav yüksekliği her 1 mm düşürüldüğünde elde edilecek iplik tasarrufu ve maliyet avantajı:"
        )

        adim = st.selectbox("Simülasyon Adım Aralığı (mm)", [0.5, 1.0, 2.0], index=1)
        adim_sayisi = st.slider("Simülasyon Adım Sayısı", 2, 10, 5)

        opt_df = fire_optimizasyon_simulasyonu(
            s.dtex_degeri, g.tarak_no, g.atki_sikligi,
            g.hav_yuksekligi, g.baglanti_payi, g.fire_orani,
            g.high_bulk_faktoru, g.hali_genisligi, g.toplam_metraj,
            g.iplik_birim_fiyat, adim_mm=adim, adim_sayisi=adim_sayisi
        )

        col_a, col_b = st.columns([3, 2])
        with col_a:
            st.plotly_chart(fire_optimizasyon_grafigi(opt_df), use_container_width=True)
        with col_b:
            st.markdown("#### 📊 Simülasyon Tablosu")
            st.dataframe(
                opt_df.style.background_gradient(subset=["Tasarruf (TL)"], cmap="Greens"),
                use_container_width=True, hide_index=True
            )

        max_tasarruf = opt_df["Tasarruf (TL)"].max()
        en_dusuk_hav = opt_df.loc[opt_df["Tasarruf (TL)"].idxmax(), "Hav Yüksekliği (mm)"]

        st.success(
            f"💡 **Öneri:** Hav yüksekliğini **{en_dusuk_hav} mm**'ye düşürerek "
            f"**₺{max_tasarruf:,.2f}** tasarruf elde edebilirsiniz. "
            f"(Halının görsel kalitesini ve konfor özelliğini göz önünde bulundurunuz.)"
        )

    # ── ALT BİLGİ ───────────────────────────────────────────────────────────
    st.divider()
    st.markdown(
        "<div style='text-align:center; color:#888; font-size:0.8em;'>"
        "🧶 Akrilik Face-to-Face Halı Üretim Planlama Sistemi v1.0 | "
        "Tüm hesaplamalar endüstri standardı formüller ile yapılmaktadır."
        "</div>",
        unsafe_allow_html=True
    )


# ─────────────────────────────────────────────────────────────────────────────
# BAŞLATICI
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()