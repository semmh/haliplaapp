"""
=============================================================================
HALI ÜRETİM HESAPLAMA MOTORU — BİRİM TESTLERİ  (test_engine.py)
=============================================================================
Çalıştırma:
    python -m pytest test_engine.py -v
    veya:
    python test_engine.py

Kapsam:
    • Birim dönüşüm fonksiyonları
    • Her hesaplama fonksiyonunun normal davranışı
    • Sınır değer analizleri  (boundary value analysis)
    • Negatif / sıfır / hatalı giriş senaryoları  (defensive tests)
    • Orkestratör entegrasyon testi
    • Fire optimizasyon simülasyonu
=============================================================================
"""

import sys
import math
import unittest
from pathlib import Path

# engine.py ile aynı dizinde olmak zorunlu değil — yolu ekle
sys.path.insert(0, str(Path(__file__).parent))
from engine import (
    CONSTANTS,
    UretimGirdileri,
    HesaplamaSonuclari,
    dtex_to_nm,
    nm_to_dtex,
    ne_to_nm,
    nm_to_ne,
    resolve_dtex_nm,
    hav_iplik_tuketimi_hesapla,
    atki_iplik_hesapla,
    cozgu_iplik_hesapla,
    uretim_suresi_hesapla,
    creel_plani_hesapla,
    maliyet_hesapla,
    fire_optimizasyon_simulasyonu,
    hesapla,
)


# ─────────────────────────────────────────────────────────────────────────────
# YARDIMCI: Tipik geçerli girdiler
# ─────────────────────────────────────────────────────────────────────────────

def tipik_girdiler(**overrides) -> UretimGirdileri:
    """Varsayılan geçerli UretimGirdileri döndürür; overrides ile değiştir."""
    defaults = dict(
        tarak_no=600, atki_sikligi=700, hav_yuksekligi=8.0,
        baglanti_payi=1.5, fire_orani=0.10, high_bulk_faktoru=1.12,
        iplik_birimi="dtex", iplik_degeri=1667.0,
        atki_iplik_ne=8.0, cozgu_iplik_nm=10.0,
        hali_genisligi=4.0, toplam_metraj=5000,
        makine_hizi=300, verimlilik=80.0,
        creel_kapasitesi=8000, renk_sayisi=8,
        iplik_birim_fiyat=85.0, atki_birim_fiyat=35.0, cozgu_birim_fiyat=40.0,
    )
    defaults.update(overrides)
    return UretimGirdileri(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# 1. BİRİM DÖNÜŞÜM TESTLERİ
# ─────────────────────────────────────────────────────────────────────────────

class TestBirimDonusum(unittest.TestCase):
    """dtex ↔ Nm ve Ne ↔ Nm dönüşüm testleri."""

    # ── dtex ↔ Nm ─────────────────────────────────────────────────────────

    def test_dtex_to_nm_bilinen_deger(self):
        """1667 dtex ≈ Nm 6.0 (endüstri standardı Nm6 akrilik)."""
        nm = dtex_to_nm(1667.0)
        self.assertAlmostEqual(nm, 5.998, places=2)

    def test_nm_to_dtex_bilinen_deger(self):
        """Nm 6.0 → 1666.67 dtex."""
        dtex = nm_to_dtex(6.0)
        self.assertAlmostEqual(dtex, 1666.67, places=1)

    def test_dtex_nm_donusum_terslenebilirlik(self):
        """dtex → Nm → dtex gidiş-dönüş aynı değeri vermeli."""
        orjinal = 2000.0
        self.assertAlmostEqual(nm_to_dtex(dtex_to_nm(orjinal)), orjinal, places=5)

    def test_dtex_to_nm_sifir_girdi_hata(self):
        """dtex = 0 → ValueError."""
        with self.assertRaises(ValueError):
            dtex_to_nm(0.0)

    def test_dtex_to_nm_negatif_girdi_hata(self):
        """dtex < 0 → ValueError."""
        with self.assertRaises(ValueError):
            dtex_to_nm(-100.0)

    def test_nm_to_dtex_sifir_hata(self):
        """Nm = 0 → ValueError."""
        with self.assertRaises(ValueError):
            nm_to_dtex(0.0)

    # ── Ne ↔ Nm ───────────────────────────────────────────────────────────

    def test_ne_to_nm_katsayi(self):
        """Ne 10 → Nm 16.535 (ISO katsayısı)."""
        self.assertAlmostEqual(ne_to_nm(10.0), 16.535, places=3)

    def test_nm_to_ne_katsayi(self):
        """Nm 16.535 → Ne ≈ 10."""
        self.assertAlmostEqual(nm_to_ne(16.535), 10.0, places=2)

    def test_ne_nm_terslenebilirlik(self):
        """Ne → Nm → Ne gidiş-dönüş."""
        ne = 12.5
        self.assertAlmostEqual(nm_to_ne(ne_to_nm(ne)), ne, places=5)

    def test_ne_to_nm_sifir_hata(self):
        with self.assertRaises(ValueError):
            ne_to_nm(0.0)

    # ── resolve_dtex_nm ────────────────────────────────────────────────────

    def test_resolve_dtex_birimi(self):
        dtex, nm = resolve_dtex_nm("dtex", 1667.0)
        self.assertAlmostEqual(dtex, 1667.0)
        self.assertAlmostEqual(nm, dtex_to_nm(1667.0), places=4)

    def test_resolve_nm_birimi(self):
        dtex, nm = resolve_dtex_nm("Nm", 6.0)
        self.assertAlmostEqual(nm, 6.0)
        self.assertAlmostEqual(dtex, nm_to_dtex(6.0), places=2)

    def test_resolve_bilinmeyen_birim_hata(self):
        with self.assertRaises(ValueError):
            resolve_dtex_nm("tex", 100.0)


# ─────────────────────────────────────────────────────────────────────────────
# 2. HAV İPLİĞİ TÜKETİMİ TESTLERİ
# ─────────────────────────────────────────────────────────────────────────────

class TestHavIplikTuketimi(unittest.TestCase):

    def _hesapla(self, **kw):
        """Tipik parametrelerle çağrı, overrides destekli."""
        defaults = dict(
            dtex=1667.0, reed=600, pick=700,
            hav_mm=8.0, baglanti_mm=1.5,
            fire_orani=0.10, high_bulk_faktoru=1.12,
        )
        defaults.update(kw)
        return hav_iplik_tuketimi_hesapla(**defaults)

    def test_sonuc_pozitif(self):
        """Hesap sonucu her zaman pozitif olmalı."""
        self.assertGreater(self._hesapla(), 0)

    def test_manuel_dogrulama(self):
        """
        Birim analizi (v1.1 düzeltmesi):
            dtex=1667, reed=600/m, pick=700/m, ilme=17.5mm=0.0175m
            1667 × 600 × 700 × 0.0175 / 10^7 × 1.10 × 1.12 ≈ 1.5095

        Endüstri referans aralığı: 0.8 – 2.5 kg/m²
        """
        sonuc = self._hesapla()
        self.assertAlmostEqual(sonuc, 1.5095, places=3)
        # Endüstri aralığı kontrolü
        self.assertGreater(sonuc, 0.8)
        self.assertLess(sonuc, 2.5)

    def test_hav_artinca_tuketim_artar(self):
        """Hav yüksekliği artınca tüketim monoton artmalı."""
        t1 = self._hesapla(hav_mm=6.0)
        t2 = self._hesapla(hav_mm=8.0)
        t3 = self._hesapla(hav_mm=12.0)
        self.assertLess(t1, t2)
        self.assertLess(t2, t3)

    def test_dtex_artinca_tuketim_artar(self):
        """Daha kalın iplik → daha fazla kg/m²."""
        self.assertLess(self._hesapla(dtex=1000), self._hesapla(dtex=2000))

    def test_fire_sifir_vs_fire_yuzde10(self):
        """Fire oranı 0 ile %10 arasındaki fark beklenen miktarda."""
        t0  = self._hesapla(fire_orani=0.0)
        t10 = self._hesapla(fire_orani=0.10)
        self.assertAlmostEqual(t10 / t0, 1.10, places=4)

    def test_high_bulk_etki(self):
        """HB faktörü 1.0 → 1.15 arasında orantılı artış."""
        t1 = self._hesapla(high_bulk_faktoru=1.0)
        t2 = self._hesapla(high_bulk_faktoru=1.15)
        self.assertAlmostEqual(t2 / t1, 1.15, places=3)

    def test_sifir_dtex_hata(self):
        with self.assertRaises(ValueError):
            self._hesapla(dtex=0)

    def test_negatif_hav_hata(self):
        with self.assertRaises(ValueError):
            self._hesapla(hav_mm=-1.0)

    def test_high_bulk_kucuk_1_hata(self):
        with self.assertRaises(ValueError):
            self._hesapla(high_bulk_faktoru=0.99)

    def test_negatif_fire_hata(self):
        with self.assertRaises(ValueError):
            self._hesapla(fire_orani=-0.01)

    def test_4_ondalik_hassasiyet(self):
        """Sonuç 4 ondalık basamak hassasiyetinde yuvarlı."""
        sonuc = self._hesapla()
        # str gösteriminde . sonrası en fazla 4 hane
        ondalik = len(str(sonuc).split(".")[-1])
        self.assertLessEqual(ondalik, 4)


# ─────────────────────────────────────────────────────────────────────────────
# 3. ATKI VE ÇÖZGÜ TESTLERİ
# ─────────────────────────────────────────────────────────────────────────────

class TestAtkiCozguIplik(unittest.TestCase):

    def test_atki_pozitif_sonuc(self):
        kg = atki_iplik_hesapla(700, 4.0, 5000, ne_to_nm(8.0), 0.05)
        self.assertGreater(kg, 0)

    def test_cozgu_pozitif_sonuc(self):
        kg = cozgu_iplik_hesapla(600, 4.0, 5000, 10.0, 0.05)
        self.assertGreater(kg, 0)

    def test_atki_metraj_2kati_kg_2kati(self):
        """Metraj 2 katına çıkınca kg da 2 katına çıkmalı (lineer)."""
        k1 = atki_iplik_hesapla(700, 4.0, 1000, 13.228, 0.0)
        k2 = atki_iplik_hesapla(700, 4.0, 2000, 13.228, 0.0)
        self.assertAlmostEqual(k2 / k1, 2.0, places=4)

    def test_cozgu_genislik_lineer(self):
        """Genişlik 2 katına çıkınca kg da 2 katına çıkmalı."""
        k1 = cozgu_iplik_hesapla(600, 2.0, 5000, 10.0, 0.0)
        k2 = cozgu_iplik_hesapla(600, 4.0, 5000, 10.0, 0.0)
        self.assertAlmostEqual(k2 / k1, 2.0, places=4)

    def test_atki_nm_sifir_hata(self):
        with self.assertRaises(ValueError):
            atki_iplik_hesapla(700, 4.0, 5000, 0.0)

    def test_cozgu_nm_negatif_hata(self):
        with self.assertRaises(ValueError):
            cozgu_iplik_hesapla(600, 4.0, 5000, -5.0)

    def test_atki_sifir_metraj_hata(self):
        with self.assertRaises(ValueError):
            atki_iplik_hesapla(700, 4.0, 0, 13.0)


# ─────────────────────────────────────────────────────────────────────────────
# 4. ÜRETİM SÜRESİ TESTLERİ
# ─────────────────────────────────────────────────────────────────────────────

class TestUretimSuresi(unittest.TestCase):

    def test_sonuc_tipleri(self):
        """UretimSuresi nesnesi döndürülmeli."""
        from engine import UretimSuresi
        s = uretim_suresi_hesapla(5000, 700, 300, 80.0)
        self.assertIsInstance(s, UretimSuresi)

    def test_saat_gun_tutarliligi(self):
        """gun_24h = saat / 24 olmalı (yuvarlamadan dolayı yaklaşık)."""
        s = uretim_suresi_hesapla(5000, 700, 300, 80.0)
        self.assertAlmostEqual(s.gun_24h, s.saat / 24, places=1)

    def test_metraj_2kati_sure_2kati(self):
        """Metraj 2 katı → süre 2 katı (lineer ölçekleme)."""
        s1 = uretim_suresi_hesapla(1000, 700, 300, 80.0)
        s2 = uretim_suresi_hesapla(2000, 700, 300, 80.0)
        self.assertAlmostEqual(s2.dakika / s1.dakika, 2.0, places=3)

    def test_verimlilik_artinca_sure_azalir(self):
        """Verimlilik artınca süre kısalmalı."""
        s1 = uretim_suresi_hesapla(5000, 700, 300, 60.0)
        s2 = uretim_suresi_hesapla(5000, 700, 300, 90.0)
        self.assertGreater(s1.dakika, s2.dakika)

    def test_rpm_sifir_hata(self):
        with self.assertRaises(ValueError):
            uretim_suresi_hesapla(5000, 700, 0, 80.0)

    def test_verimlilik_100_uzeri_hata(self):
        with self.assertRaises(ValueError):
            uretim_suresi_hesapla(5000, 700, 300, 101.0)

    def test_verimlilik_sifir_hata(self):
        with self.assertRaises(ValueError):
            uretim_suresi_hesapla(5000, 700, 300, 0.0)

    def test_negatif_metraj_hata(self):
        with self.assertRaises(ValueError):
            uretim_suresi_hesapla(-100, 700, 300, 80.0)

    def test_is_gunu_hesabi(self):
        """is_gunu_8h = dakika / 60 / 8."""
        s = uretim_suresi_hesapla(5000, 700, 300, 80.0)
        beklenen = s.dakika / 60.0 / 8.0
        self.assertAlmostEqual(s.is_gunu_8h, beklenen, places=0)


# ─────────────────────────────────────────────────────────────────────────────
# 5. CAĞLIK PLANI TESTLERİ
# ─────────────────────────────────────────────────────────────────────────────

class TestCreelPlani(unittest.TestCase):

    def test_toplam_dis_hesabi(self):
        """
        Reed=600 diş/m, genişlik=4m → toplam diş = 600×4 = 2400.
        (v1.1: Reed artık zaten /m bazında; ×10 çarpanı kaldırıldı.)
        """
        c = creel_plani_hesapla(600, 4.0, 8, 8000)
        self.assertEqual(c.toplam_dis, 2_400)

    def test_face_to_face_cift_katsayi(self):
        """Face-to-Face → toplam_bobin = renk_basi_bobin × renk × 2."""
        c = creel_plani_hesapla(600, 4.0, 8, 100_000)
        self.assertEqual(c.toplam_bobin, c.renk_basi_bobin * 8 * 2)

    def test_kapasite_asimi_tespiti(self):
        """Bobin sayısı kapasiteyi aşınca kapasite_asimi = True."""
        c = creel_plani_hesapla(600, 4.0, 8, 10)  # çok küçük kapasite
        self.assertTrue(c.kapasite_asimi)

    def test_kapasite_yeterli(self):
        """Kapasite yeterliyse kapasite_asimi = False."""
        c = creel_plani_hesapla(600, 4.0, 8, 200_000)
        self.assertFalse(c.kapasite_asimi)

    def test_kullanim_orani_aralik(self):
        """Kullanım oranı 0 < oran ≤ 1.0 veya > 1 (aşım)."""
        c = creel_plani_hesapla(600, 4.0, 8, 8000)
        self.assertGreater(c.kullanim_orani, 0)

    def test_renk_sifir_hata(self):
        with self.assertRaises(ValueError):
            creel_plani_hesapla(600, 4.0, 0, 8000)

    def test_creel_kapasitesi_sifir_hata(self):
        with self.assertRaises(ValueError):
            creel_plani_hesapla(600, 4.0, 8, 0)

    def test_negatif_genislik_hata(self):
        with self.assertRaises(ValueError):
            creel_plani_hesapla(600, -1.0, 8, 8000)

    def test_renk_basi_bobin_tavan(self):
        """renk_basi_bobin = ceil(toplam_dis / renk_sayisi)."""
        c = creel_plani_hesapla(700, 4.0, 8, 100_000)
        beklenen = math.ceil(c.toplam_dis / 8)
        self.assertEqual(c.renk_basi_bobin, beklenen)


# ─────────────────────────────────────────────────────────────────────────────
# 6. MALİYET TESTLERİ
# ─────────────────────────────────────────────────────────────────────────────

class TestMaliyet(unittest.TestCase):

    def _hesapla(self, **kw):
        defaults = dict(
            hav_kg=1000.0, atki_kg=200.0, cozgu_kg=150.0,
            hav_fiyat=85.0, atki_fiyat=35.0, cozgu_fiyat=40.0,
            alan_m2=20_000.0,
        )
        defaults.update(kw)
        return maliyet_hesapla(**defaults)

    def test_toplam_dogru(self):
        """Toplam = hav + atkı + çözgü maliyeti."""
        m = self._hesapla()
        beklenen = 1000*85 + 200*35 + 150*40
        self.assertAlmostEqual(m.toplam, beklenen, places=1)

    def test_maliyet_m2(self):
        """m² maliyeti = toplam / alan."""
        m = self._hesapla()
        self.assertAlmostEqual(m.maliyet_m2, m.toplam / 20_000.0, places=2)

    def test_sifir_alan_hata(self):
        with self.assertRaises(ValueError):
            self._hesapla(alan_m2=0)

    def test_negatif_alan_hata(self):
        with self.assertRaises(ValueError):
            self._hesapla(alan_m2=-500)

    def test_negatif_fiyat_sifira_cekiliyor(self):
        """Negatif fiyat 0'a çekilmeli, hata fırlatmamalı."""
        m = self._hesapla(hav_fiyat=-10.0)
        self.assertGreaterEqual(m.hav_maliyet, 0)

    def test_tum_sifir_fiyat(self):
        """Tüm fiyatlar 0 → toplam 0, m² maliyeti 0."""
        m = self._hesapla(hav_fiyat=0, atki_fiyat=0, cozgu_fiyat=0)
        self.assertEqual(m.toplam, 0.0)
        self.assertEqual(m.maliyet_m2, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 7. OPTİMİZASYON SİMÜLASYONU TESTLERİ
# ─────────────────────────────────────────────────────────────────────────────

class TestFireOptimizasyon(unittest.TestCase):

    def _sim(self, **kw):
        defaults = dict(
            dtex=1667.0, reed=600, pick=700,
            hav_mm=8.0, baglanti_mm=1.5,
            fire_orani=0.10, high_bulk=1.12,
            genislik=4.0, metraj=5000,
            hav_fiyat=85.0, adim_mm=1.0, adim_sayisi=5,
        )
        defaults.update(kw)
        return fire_optimizasyon_simulasyonu(**defaults)

    def test_ilk_satir_baz_deger(self):
        """İlk satır mevcut hav yüksekliğidir, tasarruf 0 olmalı."""
        sonuc = self._sim()
        self.assertEqual(sonuc[0].hav_mm, 8.0)
        self.assertEqual(sonuc[0].tasarruf_kg, 0.0)

    def test_satir_sayisi_dogru(self):
        """adim_sayisi=4 → 5 satır (0,1,2,3,4)."""
        sonuc = self._sim(adim_sayisi=4)
        self.assertEqual(len(sonuc), 5)

    def test_tasarruf_monoton_artan(self):
        """Her adımda tasarruf öncekinden büyük olmalı."""
        sonuc = self._sim()
        tasarruflar = [s.tasarruf_kg for s in sonuc]
        self.assertEqual(tasarruflar, sorted(tasarruflar))

    def test_hav_azalan_sira(self):
        """Hav yüksekliği her adımda azalmalı."""
        sonuc = self._sim()
        havlar = [s.hav_mm for s in sonuc]
        self.assertEqual(havlar, sorted(havlar, reverse=True))

    def test_sifir_adim_hata(self):
        with self.assertRaises(ValueError):
            self._sim(adim_mm=0.0)

    def test_hav_sifir_gecmez(self):
        """hav_mm - adım × n ≤ 0 olan adımlar atlanmalı."""
        sonuc = self._sim(hav_mm=3.0, adim_mm=1.0, adim_sayisi=10)
        for s in sonuc:
            self.assertGreater(s.hav_mm, 0)

    def test_tasarruf_tl_pozitif(self):
        """Fiyat > 0 ve tasarruf_kg > 0 ise tasarruf_tl > 0."""
        sonuc = self._sim()
        for s in sonuc[1:]:  # ilk satır baz, tasarruf 0
            self.assertGreater(s.tasarruf_tl, 0)


# ─────────────────────────────────────────────────────────────────────────────
# 8. ORKESTRATÖR ENTEGRASYON TESTİ
# ─────────────────────────────────────────────────────────────────────────────

class TestHesaplaOrkestrator(unittest.TestCase):
    """hesapla() fonksiyonunun uçtan uca davranışını test eder."""

    def setUp(self):
        self.g = tipik_girdiler()
        self.s = hesapla(self.g)

    def test_donus_tipi(self):
        self.assertIsInstance(self.s, HesaplamaSonuclari)

    def test_toplam_iplik_alt_parcalar_toplami(self):
        """Toplam iplik = hav + atkı + çözgü."""
        beklenen = round(
            self.s.toplam_hav_kg + self.s.toplam_atki_kg + self.s.toplam_cozgu_kg, 2
        )
        self.assertAlmostEqual(self.s.toplam_iplik_kg, beklenen, places=1)

    def test_alan_m2_dogru(self):
        """Alan = genişlik × metraj."""
        self.assertAlmostEqual(
            self.s.alan_m2,
            self.g.hali_genisligi * self.g.toplam_metraj,
            places=1,
        )

    def test_dtex_nm_tutarlilik(self):
        """dtex × nm ≈ 10 000."""
        self.assertAlmostEqual(
            self.s.dtex_degeri * self.s.nm_degeri,
            10_000.0, places=0
        )

    def test_sure_alt_nesne(self):
        from engine import UretimSuresi
        self.assertIsInstance(self.s.sure, UretimSuresi)

    def test_creel_alt_nesne(self):
        from engine import CreelPlan
        self.assertIsInstance(self.s.creel, CreelPlan)

    def test_maliyet_alt_nesne(self):
        from engine import MaliyetSonucu
        self.assertIsInstance(self.s.maliyet, MaliyetSonucu)

    def test_nm_birimi_ile_ayni_sonuc(self):
        """Nm girişi ile dtex girişi aynı sonucu vermeli."""
        g_nm = tipik_girdiler(iplik_birimi="Nm", iplik_degeri=dtex_to_nm(1667.0))
        s_nm = hesapla(g_nm)
        self.assertAlmostEqual(
            self.s.hav_tuketim_kg_m2, s_nm.hav_tuketim_kg_m2, places=3
        )

    def test_hav_tuketim_kg_m2_aralik(self):
        """
        Tipik endüstri değeri: 0.8 – 2.5 kg/m²
        (v1.1 düzeltmesi sonrası doğrulanmış aralık)
        """
        self.assertGreater(self.s.hav_tuketim_kg_m2, 0.8)
        self.assertLess(self.s.hav_tuketim_kg_m2, 2.5)

    def test_maliyet_m2_pozitif(self):
        self.assertGreater(self.s.maliyet.maliyet_m2, 0)

    def test_creel_toplam_dis_pozitif(self):
        self.assertGreater(self.s.creel.toplam_dis, 0)

    def test_farkli_genislik_farkli_toplam_kg(self):
        """Geniş halı daha fazla iplik tüketmeli."""
        g_dar  = tipik_girdiler(hali_genisligi=2.0)
        g_genis = tipik_girdiler(hali_genisligi=4.0)
        s_dar  = hesapla(g_dar)
        s_genis = hesapla(g_genis)
        self.assertLess(s_dar.toplam_iplik_kg, s_genis.toplam_iplik_kg)


# ─────────────────────────────────────────────────────────────────────────────
# 9. SINIR DEĞER ANALİZİ
# ─────────────────────────────────────────────────────────────────────────────

class TestSinirDegerleri(unittest.TestCase):
    """Parametre sınırlarındaki davranış testleri."""

    def test_minimum_hav_0_5mm(self):
        """Çok düşük hav yüksekliği hata fırlatmamalı."""
        sonuc = hav_iplik_tuketimi_hesapla(1667, 600, 700, 0.5, 0.5, 0.05, 1.05)
        self.assertGreater(sonuc, 0)

    def test_maksimum_verimlilik_100(self):
        """Verimlilik tam 100 geçerli olmalı."""
        s = uretim_suresi_hesapla(1000, 700, 300, 100.0)
        self.assertGreater(s.dakika, 0)

    def test_tek_renk_creel(self):
        """Tek renk ile creel planı hesaplanabilmeli."""
        c = creel_plani_hesapla(600, 4.0, 1, 50_000)
        self.assertEqual(c.renk_basi_bobin, c.toplam_dis)

    def test_cok_dar_hali(self):
        """0.5 m genişlik geçerli olmalı."""
        g = tipik_girdiler(hali_genisligi=0.5)
        s = hesapla(g)
        self.assertGreater(s.toplam_hav_kg, 0)

    def test_buyuk_metraj(self):
        """50 000 m metraj hesaplanabilmeli."""
        g = tipik_girdiler(toplam_metraj=50_000)
        s = hesapla(g)
        self.assertGreater(s.toplam_iplik_kg, 0)

    def test_yuksek_rpm(self):
        """RPM=1000 geçerli olmalı."""
        s = uretim_suresi_hesapla(5000, 700, 1000, 90.0)
        self.assertGreater(s.dakika, 0)


# ─────────────────────────────────────────────────────────────────────────────
# ÇALIŞTIRICI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Renkli ve ayrıntılı çıktı
    loader  = unittest.TestLoader()
    suite   = loader.discover(start_dir=".", pattern="test_engine.py")
    runner  = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result  = runner.run(suite)

    print("\n" + "═" * 60)
    print(f"  Toplam test  : {result.testsRun}")
    print(f"  ✅ Başarılı  : {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"  ❌ Başarısız : {len(result.failures)}")
    print(f"  💥 Hata      : {len(result.errors)}")
    print("═" * 60)

    sys.exit(0 if result.wasSuccessful() else 1)