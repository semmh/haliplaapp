"""
=============================================================================
HALI ÜRETİM HESAPLAMA MOTORU  —  engine.py  (v1.1)
=============================================================================
Bu modül Streamlit'ten tamamen bağımsızdır.
UI katmanı (app.py) yalnızca bu modülü import eder.

Tasarım ilkeleri
────────────────
• Saf fonksiyonlar   : yan etki yok, aynı girdi → aynı çıktı
• Savunmacı doğrulama: sıfır-bölme ve negatif girdi → ValueError
• Tip güvenliği      : dataclass + tip anotasyonları
• Sabit havuzu       : CONSTANTS sınıfı

BUG FIX (v1.0 → v1.1):
    Reed ve Pick Türk halı sektöründe diş/m ve vuruş/m olarak girilir.
    Eski kodda ×10 çarpanı yanlışlıkla uygulanarak sonuç 100× büyüyordu.
    Çarpan kaldırıldı; birim analizi test_engine.py ile doğrulandı.
    Yeni tipik çıktı: 0.8 – 2.5 kg/m² (endüstri referansı).
=============================================================================
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# SABİTLER
# ─────────────────────────────────────────────────────────────────────────────

class CONSTANTS:
    NE_TO_NM_FACTOR:      float = 1.6535        # ISO 7211-5
    DTEX_NM_BASE:         float = 10_000.0
    HAV_FORMULA_DIVISOR:  float = 10_000_000.0  # 10^7  (birim analizi: g/m² → kg/m²)
    VARDIYA_SAATI:        int   = 8
    FIRE_MIN:             float = 0.0
    FIRE_MAX:             float = 0.50


# ─────────────────────────────────────────────────────────────────────────────
# VERİ YAPILARI
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class UretimGirdileri:
    tarak_no:          int    # Reed — diş/m
    atki_sikligi:      int    # Pick — vuruş/m
    hav_yuksekligi:    float  # mm
    baglanti_payi:     float  # mm
    fire_orani:        float  # ondalık
    high_bulk_faktoru: float
    iplik_birimi:      str    # "dtex" | "Nm"
    iplik_degeri:      float
    atki_iplik_ne:     float  # Ne
    cozgu_iplik_nm:    float  # Nm
    hali_genisligi:    float  # m
    toplam_metraj:     float  # m
    makine_hizi:       int    # RPM
    verimlilik:        float  # 0–100
    creel_kapasitesi:  int
    renk_sayisi:       int
    iplik_birim_fiyat: float  # TL/kg
    atki_birim_fiyat:  float
    cozgu_birim_fiyat: float


@dataclass
class CreelPlan:
    toplam_dis:      int
    renk_basi_dis:   float
    renk_basi_bobin: int
    toplam_bobin:    int
    kapasite_asimi:  bool
    kullanim_orani:  float


@dataclass
class MaliyetSonucu:
    hav_maliyet:   float
    atki_maliyet:  float
    cozgu_maliyet: float
    toplam:        float
    maliyet_m2:    float


@dataclass
class UretimSuresi:
    dakika:         float
    saat:           float
    gun_24h:        float
    is_gunu_8h:     float
    vardiya_sayisi: float
    gun_3vardiya:   float


@dataclass
class HesaplamaSonuclari:
    dtex_degeri:       float
    nm_degeri:         float
    atki_nm:           float
    hav_tuketim_kg_m2: float
    toplam_hav_kg:     float
    toplam_atki_kg:    float
    toplam_cozgu_kg:   float
    toplam_iplik_kg:   float
    alan_m2:           float
    sure:              UretimSuresi
    creel:             CreelPlan
    maliyet:           MaliyetSonucu


@dataclass
class OptimizasyonSatiri:
    hav_mm:        float
    tuketim_kg_m2: float
    toplam_kg:     float
    tasarruf_kg:   float
    tasarruf_tl:   float


# ─────────────────────────────────────────────────────────────────────────────
# BİRİM DÖNÜŞÜM
# ─────────────────────────────────────────────────────────────────────────────

def dtex_to_nm(dtex: float) -> float:
    if dtex <= 0:
        raise ValueError(f"dtex pozitif olmalı: {dtex}")
    return CONSTANTS.DTEX_NM_BASE / dtex


def nm_to_dtex(nm: float) -> float:
    if nm <= 0:
        raise ValueError(f"Nm pozitif olmalı: {nm}")
    return CONSTANTS.DTEX_NM_BASE / nm


def ne_to_nm(ne: float) -> float:
    """Ne → Nm  (ISO 7211-5: katsayı 1.6535)"""
    if ne <= 0:
        raise ValueError(f"Ne pozitif olmalı: {ne}")
    return ne * CONSTANTS.NE_TO_NM_FACTOR


def nm_to_ne(nm: float) -> float:
    if nm <= 0:
        raise ValueError(f"Nm pozitif olmalı: {nm}")
    return nm / CONSTANTS.NE_TO_NM_FACTOR


def resolve_dtex_nm(birimi: str, deger: float) -> Tuple[float, float]:
    """Girilen birim/değerden (dtex, nm) çifti döndürür."""
    if birimi == "dtex":
        return deger, dtex_to_nm(deger)
    elif birimi == "Nm":
        return nm_to_dtex(deger), deger
    raise ValueError(f"Bilinmeyen iplik birimi: '{birimi}'")


# ─────────────────────────────────────────────────────────────────────────────
# HESAPLAMA MOTORU
# ─────────────────────────────────────────────────────────────────────────────

def hav_iplik_tuketimi_hesapla(
    dtex:              float,
    reed:              int,
    pick:              int,
    hav_mm:            float,
    baglanti_mm:       float,
    fire_orani:        float,
    high_bulk_faktoru: float,
) -> float:
    """
    Hav ipliği tüketimi — kg/m²

    Formül (birim analizi):
        ilme_m = (2×hav + baglanti) / 1000        [mm → m]
        kg/m²  = dtex × reed[/m] × pick[/m]
                 × ilme_m × (1+fire) × HB  ÷ 10^7

    Birim kontrolü:
        [g/10000m] × [/m] × [/m] × [m]  =  g/m² / 10000
        → ÷ 1000  → kg/m²     payda toplam: 10^7  ✓

    Tipik aralık: 0.8 – 2.5 kg/m²
    """
    if dtex <= 0:              raise ValueError(f"dtex pozitif olmalı: {dtex}")
    if reed <= 0:              raise ValueError(f"Reed pozitif olmalı: {reed}")
    if pick <= 0:              raise ValueError(f"Pick pozitif olmalı: {pick}")
    if hav_mm <= 0:            raise ValueError(f"Hav yüksekliği pozitif olmalı: {hav_mm}")
    if baglanti_mm < 0:        raise ValueError(f"Bağlantı payı negatif olamaz: {baglanti_mm}")
    if fire_orani < 0:         raise ValueError(f"Fire oranı negatif olamaz: {fire_orani}")
    if high_bulk_faktoru < 1.0:raise ValueError(f"High-Bulk ≥ 1.0 olmalı: {high_bulk_faktoru}")

    ilme_m  = (2.0 * hav_mm + baglanti_mm) / 1000.0
    tuketim = (
        dtex * reed * pick * ilme_m
        * (1.0 + fire_orani)
        * high_bulk_faktoru
        / CONSTANTS.HAV_FORMULA_DIVISOR
    )
    return round(tuketim, 4)


def atki_iplik_hesapla(
    pick:       int,
    genislik_m: float,
    metraj:     float,
    atki_nm:    float,
    fire_orani: float = 0.05,
) -> float:
    """Atkı ipliği tüketimi — kg"""
    if atki_nm <= 0:               raise ValueError(f"Atkı Nm pozitif olmalı: {atki_nm}")
    if genislik_m <= 0 or metraj <= 0: raise ValueError("Genişlik ve metraj pozitif olmalı.")
    toplam_m = pick * metraj * genislik_m
    return round(toplam_m / (atki_nm * 1000.0) * (1.0 + fire_orani), 2)


def cozgu_iplik_hesapla(
    reed:       int,
    genislik_m: float,
    metraj:     float,
    cozgu_nm:   float,
    fire_orani: float = 0.05,
) -> float:
    """Çözgü ipliği tüketimi — kg"""
    if cozgu_nm <= 0:              raise ValueError(f"Çözgü Nm pozitif olmalı: {cozgu_nm}")
    if genislik_m <= 0 or metraj <= 0: raise ValueError("Genişlik ve metraj pozitif olmalı.")
    toplam_m = reed * genislik_m * metraj
    return round(toplam_m / (cozgu_nm * 1000.0) * (1.0 + fire_orani), 2)


def uretim_suresi_hesapla(
    metraj:           float,
    atki_sikligi:     int,
    rpm:              int,
    verimlilik_yuzde: float,
) -> UretimSuresi:
    """
    Üretim süresi — UretimSuresi

    dakika = (metraj × pick[vuruş/m]) / (RPM × verimlilik/100)
    """
    if rpm <= 0:                       raise ValueError(f"RPM pozitif olmalı: {rpm}")
    if not (0 < verimlilik_yuzde <= 100): raise ValueError(f"Verimlilik 0-100: {verimlilik_yuzde}")
    if metraj <= 0:                    raise ValueError(f"Metraj pozitif olmalı: {metraj}")

    efektif_rpm = rpm * (verimlilik_yuzde / 100.0)
    dakika = (metraj * atki_sikligi) / efektif_rpm
    saat   = dakika / 60.0
    gun_24 = saat   / 24.0

    return UretimSuresi(
        dakika         = round(dakika, 1),
        saat           = round(saat,   2),
        gun_24h        = round(gun_24, 2),
        is_gunu_8h     = round(saat / CONSTANTS.VARDIYA_SAATI, 1),
        vardiya_sayisi = round(saat / CONSTANTS.VARDIYA_SAATI, 1),
        gun_3vardiya   = round(gun_24, 2),
    )


def creel_plani_hesapla(
    reed:             int,
    genislik_m:       float,
    renk_sayisi:      int,
    creel_kapasitesi: int,
) -> CreelPlan:
    """Cağlık planı — CreelPlan  (Face-to-Face ×2 çarpanı)"""
    if renk_sayisi <= 0:      raise ValueError(f"Renk sayısı pozitif olmalı: {renk_sayisi}")
    if creel_kapasitesi <= 0: raise ValueError(f"Creel kapasitesi pozitif olmalı: {creel_kapasitesi}")
    if genislik_m <= 0:       raise ValueError(f"Genişlik pozitif olmalı: {genislik_m}")

    toplam_dis      = int(reed * genislik_m)
    renk_basi_dis   = toplam_dis / renk_sayisi
    renk_basi_bobin = math.ceil(renk_basi_dis)
    toplam_bobin    = renk_basi_bobin * renk_sayisi * 2
    kullanim        = toplam_bobin / creel_kapasitesi

    return CreelPlan(
        toplam_dis      = toplam_dis,
        renk_basi_dis   = round(renk_basi_dis, 1),
        renk_basi_bobin = renk_basi_bobin,
        toplam_bobin    = toplam_bobin,
        kapasite_asimi  = toplam_bobin > creel_kapasitesi,
        kullanim_orani  = round(kullanim, 4),
    )


def maliyet_hesapla(
    hav_kg: float, atki_kg: float, cozgu_kg: float,
    hav_fiyat: float, atki_fiyat: float, cozgu_fiyat: float,
    alan_m2: float,
) -> MaliyetSonucu:
    """Maliyet hesabı. Negatif fiyatlar 0'a çekilir."""
    if alan_m2 <= 0: raise ValueError(f"Alan m² pozitif olmalı: {alan_m2}")
    hav_fiyat   = max(0.0, hav_fiyat)
    atki_fiyat  = max(0.0, atki_fiyat)
    cozgu_fiyat = max(0.0, cozgu_fiyat)
    hav_m   = hav_kg   * hav_fiyat
    atki_m  = atki_kg  * atki_fiyat
    cozgu_m = cozgu_kg * cozgu_fiyat
    toplam  = hav_m + atki_m + cozgu_m
    return MaliyetSonucu(
        hav_maliyet   = round(hav_m,   2),
        atki_maliyet  = round(atki_m,  2),
        cozgu_maliyet = round(cozgu_m, 2),
        toplam        = round(toplam,  2),
        maliyet_m2    = round(toplam / alan_m2, 2),
    )


def fire_optimizasyon_simulasyonu(
    dtex: float, reed: int, pick: int,
    hav_mm: float, baglanti_mm: float,
    fire_orani: float, high_bulk: float,
    genislik: float, metraj: float, hav_fiyat: float,
    adim_mm: float = 1.0, adim_sayisi: int = 5,
) -> List[OptimizasyonSatiri]:
    """Hav yüksekliği optimizasyon simülasyonu — ilk satır baz (tasarruf=0)"""
    if adim_mm <= 0: raise ValueError(f"Adım mm pozitif olmalı: {adim_mm}")
    alan_m2    = genislik * metraj
    baz        = hav_iplik_tuketimi_hesapla(dtex, reed, pick, hav_mm, baglanti_mm, fire_orani, high_bulk)
    baz_toplam = baz * alan_m2
    sonuclar: List[OptimizasyonSatiri] = []
    for i in range(adim_sayisi + 1):
        h = round(hav_mm - i * adim_mm, 2)
        if h <= 0:
            break
        t      = hav_iplik_tuketimi_hesapla(dtex, reed, pick, h, baglanti_mm, fire_orani, high_bulk)
        toplam = t * alan_m2
        tas_kg = round(baz_toplam - toplam, 2)
        sonuclar.append(OptimizasyonSatiri(
            hav_mm        = h,
            tuketim_kg_m2 = t,
            toplam_kg     = round(toplam, 2),
            tasarruf_kg   = tas_kg,
            tasarruf_tl   = round(tas_kg * hav_fiyat, 2),
        ))
    return sonuclar


# ─────────────────────────────────────────────────────────────────────────────
# ORKESTRATÖR
# ─────────────────────────────────────────────────────────────────────────────

def hesapla(g: UretimGirdileri) -> HesaplamaSonuclari:
    """UI'nın tek çağrı noktası — tüm alt hesaplamaları çalıştırır."""
    dtex, nm  = resolve_dtex_nm(g.iplik_birimi, g.iplik_degeri)
    atki_nm   = ne_to_nm(g.atki_iplik_ne)
    alan_m2   = g.hali_genisligi * g.toplam_metraj
    alt_fire  = g.fire_orani * 0.5

    hav_kg_m2    = hav_iplik_tuketimi_hesapla(
        dtex, g.tarak_no, g.atki_sikligi,
        g.hav_yuksekligi, g.baglanti_payi,
        g.fire_orani, g.high_bulk_faktoru,
    )
    toplam_hav   = round(hav_kg_m2 * alan_m2, 2)
    toplam_atki  = atki_iplik_hesapla(g.atki_sikligi, g.hali_genisligi, g.toplam_metraj, atki_nm, alt_fire)
    toplam_cozgu = cozgu_iplik_hesapla(g.tarak_no, g.hali_genisligi, g.toplam_metraj, g.cozgu_iplik_nm, alt_fire)
    toplam_iplik = round(toplam_hav + toplam_atki + toplam_cozgu, 2)

    return HesaplamaSonuclari(
        dtex_degeri       = round(dtex, 2),
        nm_degeri         = round(nm,   3),
        atki_nm           = round(atki_nm, 3),
        hav_tuketim_kg_m2 = hav_kg_m2,
        toplam_hav_kg     = toplam_hav,
        toplam_atki_kg    = toplam_atki,
        toplam_cozgu_kg   = toplam_cozgu,
        toplam_iplik_kg   = toplam_iplik,
        alan_m2           = round(alan_m2, 2),
        sure    = uretim_suresi_hesapla(g.toplam_metraj, g.atki_sikligi, g.makine_hizi, g.verimlilik),
        creel   = creel_plani_hesapla(g.tarak_no, g.hali_genisligi, g.renk_sayisi, g.creel_kapasitesi),
        maliyet = maliyet_hesapla(
            toplam_hav, toplam_atki, toplam_cozgu,
            g.iplik_birim_fiyat, g.atki_birim_fiyat, g.cozgu_birim_fiyat, alan_m2,
        ),
    )