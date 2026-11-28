# DODNI // Portföy Yönetimi (Masaüstü & Mobil PWA)

Borsa İstanbul (BIST) odaklı, **çevrimdışı öncelikli (offline-first)** çalışan ve isteğe bağlı olarak **Supabase** üzerinden PC ile mobil cihazlar arasında çift yönlü bulut senkronizasyonu sunan açık kaynak portföy takip uygulamasıdır.

## Öne Çıkan Özellikler

- **Çift Platform & Otomatik Senkronizasyon:** Windows masaüstü uygulaması (`dodni.py` — PyQt5) ve mobil/web arayüzü (`index.html` — PWA) aynı veri şeması (`REF_ID`) ile çift yönlü eşitlenir.
- **Kasa ve Pozisyon Yönetimi:** Alış, satış, nakit giriş/çıkış, nakit temettü ve bedelsiz bölünme işlemlerinde ağırlıklı ortalama maliyet ve realize kâr/zarar hesaplaması.
- **Akıllı Fiyat Takibi & Seans Koruması:** Hafta içi `09:55 – 18:15` seans saatlerinde otomatik güncelleme, 45 saniye hız sınırı koruması ve Vercel Edge Cache (`/api/fiyat`) desteği.
- **Hedef & Stop-Loss Alarmları:** Hisse bazlı üst hedef ve zarar durdur uyarıları.
- **Raporlama ve Yedekleme:** Tarih aralıklı komisyon/realize K/Z raporları, grafikli Excel (`.xlsx`) çıktısı, PC (`.zip`) ve Mobil (`.json`) yedekleme uyumluluğu.
- **Tema ve Yerel Format:** Karanlık / Aydınlık tema geçişi ve Türkçe para/sayı formatı (`1.000.000,01`).

---

## Kurulum ve Çalıştırma

### 1. Masaüstü Uygulaması (Windows / Python)

```bash
git clone [https://github.com/goclovpn-cmd/dodni-portfoy.git](https://github.com/goclovpn-cmd/dodni-portfoy.git)
cd dodni-portfoy
pip install -r requirements.txt
python dodni.py
Windows .exe Olarak Paketleme (PyInstaller & Inno Setup)
python -m PyInstaller --noconsole --onedir --clean --noupx --icon=dodni.ico --hidden-import yfinance --hidden-import openpyxl --copy-metadata yfinance --collect-all curl_cffi --collect-all certifi --exclude-module matplotlib --exclude-module scipy --exclude-module tkinter --exclude-module IPython dodni.py
Derleme sonrasında dodni_kurulum.iss dosyasını Inno Setup Compiler ile derleyerek tek dosyalık Windows kurulum sihirbazı oluşturabilirsiniz.
