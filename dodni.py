import sys, os, traceback, json, zipfile, time, ssl
import urllib.request, urllib.error
from datetime import datetime, timezone
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QLineEdit, QPushButton, QComboBox, QDateEdit, QListWidget,
    QListWidgetItem, QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QMessageBox, QMenu, QAbstractItemView, QDialog, QTabWidget)
from PyQt5.QtCore import QTimer, QDate, QThread, pyqtSignal, Qt, QRectF
from PyQt5.QtGui import QColor, QPainter, QPen, QFont


SUPABASE_URL = "https://eacnkzveqmzgxicbyggy.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_CdZhVbLOSlOISJmIYeN6dw_TsAwR9bf"

YASAL_UYARI = (
    "Yasal Uyarı (Disclaimer): Bu proje yalnızca eğitim ve kişisel portföy takibi amacıyla "
    "açık kaynak olarak geliştirilmiştir. Borsa İstanbul A.Ş. veya Yahoo Finance ile hiçbir "
    "resmi bağlantısı bulunmamaktadır. Uygulamada gösterilen fiyat verileri Yahoo Finance "
    "üzerinden sağlanmakta olup gecikmeli veya hatalı olabilir; kesinlikle yatırım tavsiyesi "
    "niteliği taşımaz."
)


def tr_para(deger, isaretli=False):
    if deger is None:
        return "-"
    s = f"{deger:+,.2f}" if isaretli else f"{deger:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def tr_sayi(deger):
    if deger is None:
        return "0"
    return f"{int(deger):,}".replace(",", ".")


def iso_zaman_tr(iso_str):
    if not iso_str:
        return "Bilinmiyor"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        yerel_dt = dt.astimezone()
        return yerel_dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return iso_str


def seans_acik_mi():
    simdi = datetime.now()
    if simdi.weekday() >= 5:
        return False
    dakika = simdi.hour * 60 + simdi.minute
    return (9 * 60 + 55) <= dakika <= (18 * 60 + 15)


class SupabaseClient:
    """Harici kütüphane gerektirmeyen hafif Supabase Auth & PostgREST istemcisi."""
    def __init__(self, session_file):
        self.url = SUPABASE_URL.rstrip("/")
        self.key = SUPABASE_ANON_KEY
        self.session_file = session_file
        self.session = self._oturum_oku()
        try:
            import certifi
            self._ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            self._ssl_ctx = ssl.create_default_context()

    def _oturum_oku(self):
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and data.get("access_token") and data.get("user_id"):
                        return data
        except Exception:
            pass
        return None

    def _oturum_kaydet(self, data):
        self.session = data
        try:
            if data is None:
                if os.path.exists(self.session_file):
                    os.remove(self.session_file)
            else:
                gecici = self.session_file + ".tmp"
                with open(gecici, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(gecici, self.session_file)
        except Exception:
            pass

    def giris_yapildi_mi(self):
        return bool(self.session and self.session.get("access_token") and self.session.get("user_id"))

    def kullanici_email(self):
        return self.session.get("email", "") if self.session else ""

    def cikis_yap(self):
        self._oturum_kaydet(None)

    def _istek(self, path, method="GET", body=None, token=None, extra_headers=None):
        headers = {
            "apikey": self.key,
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token or self.key}"
        }
        if extra_headers:
            headers.update(extra_headers)
        raw_body = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(f"{self.url}{path}", data=raw_body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15, context=self._ssl_ctx) as resp:
                txt = resp.read().decode("utf-8")
                return resp.status, (json.loads(txt) if txt else None)
        except urllib.error.HTTPError as e:
            err_txt = e.read().decode("utf-8", errors="ignore")
            try:
                err_json = json.loads(err_txt)
                msg = err_json.get("msg") or err_json.get("error_description") or err_json.get("message") or err_txt
            except Exception:
                msg = err_txt or str(e)
            raise RuntimeError(f"HTTP {e.code}: {msg}")
        except Exception as e:
            raise RuntimeError(f"Bağlantı hatası: {str(e)}")

    def token_yenile(self):
        if not self.session or not self.session.get("refresh_token"):
            raise RuntimeError("Oturum süresi doldu, lütfen yeniden giriş yapın.")
        _, res = self._istek(
            "/auth/v1/token?grant_type=refresh_token",
            method="POST",
            body={"refresh_token": self.session["refresh_token"]}
        )
        if not res or not res.get("access_token"):
            self.cikis_yap()
            raise RuntimeError("Oturum yenilenemedi, lütfen yeniden giriş yapın.")
        user = res.get("user") or {}
        self._oturum_kaydet({
            "access_token": res["access_token"],
            "refresh_token": res.get("refresh_token", self.session["refresh_token"]),
            "user_id": user.get("id", self.session["user_id"]),
            "email": user.get("email", self.session.get("email", ""))
        })

    def giris_yap(self, email, password):
        _, res = self._istek(
            "/auth/v1/token?grant_type=password",
            method="POST",
            body={"email": email.strip(), "password": password}
        )
        if not res or not res.get("access_token"):
            raise RuntimeError("Giriş başarısız. E-posta veya şifrenizi kontrol edin.")
        user = res.get("user") or {}
        self._oturum_kaydet({
            "access_token": res["access_token"],
            "refresh_token": res.get("refresh_token", ""),
            "user_id": user.get("id"),
            "email": user.get("email", email.strip())
        })

    def kayit_ol(self, email, password, invite_code=""):
        _, res = self._istek(
            "/auth/v1/signup",
            method="POST",
            body={
                "email": email.strip(),
                "password": password,
                "data": {"invite_code": invite_code.strip().upper()}
            }
        )
        if res and res.get("access_token"):
            user = res.get("user") or {}
            self._oturum_kaydet({
                "access_token": res["access_token"],
                "refresh_token": res.get("refresh_token", ""),
                "user_id": user.get("id"),
                "email": user.get("email", email.strip())
            })
            return True
        return False

    def buluttan_cek(self):
        if not self.giris_yapildi_mi():
            return None
        uid = self.session["user_id"]
        path = f"/rest/v1/portfolios?user_id=eq.{uid}&select=data,updated_at"
        try:
            _, rows = self._istek(path, method="GET", token=self.session["access_token"])
        except RuntimeError as e:
            if "HTTP 401" in str(e):
                self.token_yenile()
                _, rows = self._istek(path, method="GET", token=self.session["access_token"])
            else:
                raise
        return rows[0] if rows else None

    def buluta_yaz(self, payload):
        if not self.giris_yapildi_mi():
            return
        uid = self.session["user_id"]
        utc_simdi = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        body = {
            "user_id": uid,
            "data": payload,
            "updated_at": utc_simdi
        }
        headers = {"Prefer": "resolution=merge-duplicates,return=minimal"}
        path = "/rest/v1/portfolios?on_conflict=user_id"
        try:
            self._istek(path, method="POST", body=body, token=self.session["access_token"], extra_headers=headers)
        except RuntimeError as e:
            if "HTTP 401" in str(e):
                self.token_yenile()
                self._istek(path, method="POST", body=body, token=self.session["access_token"], extra_headers=headers)
            else:
                raise


class BulutSyncThread(QThread):
    tamamlandi = pyqtSignal(str, object)
    hata = pyqtSignal(str, str)

    def __init__(self, sb_client, mod, payload=None):
        super().__init__()
        self.sb = sb_client
        self.mod = mod  # "PUSH" veya "PULL"
        self.payload = payload

    def run(self):
        try:
            if self.mod == "PUSH":
                self.sb.buluta_yaz(self.payload)
                self.tamamlandi.emit("PUSH", None)
            elif self.mod == "PULL":
                kayit = self.sb.buluttan_cek()
                self.tamamlandi.emit("PULL", kayit)
        except Exception as e:
            self.hata.emit(self.mod, str(e))


class BulutDialog(QDialog):
    """Supabase Hesap Girişi / Kayıt ve Senkronizasyon Penceresi."""
    def __init__(self, sb_client, parent=None):
        super().__init__(parent)
        self.sb = sb_client
        self.aksiyon = None
        self.setWindowTitle("DODNI // Bulut Senkronizasyonu (Supabase)")
        self.setMinimumWidth(410)

        lay = QVBoxLayout(self)

        if self.sb.giris_yapildi_mi():
            lbl = QLabel(f"Aktif Bulut Hesabı:\n{self.sb.kullanici_email()}")
            lbl.setStyleSheet("font-weight:bold; padding:8px; border:1px solid #00d2ff;")
            lay.addWidget(lbl)

            b_push = QPushButton("⬆ Bu Cihazdaki Verileri Buluta Gönder")
            b_push.clicked.connect(lambda: self._sec("PUSH"))
            b_pull = QPushButton("⬇ Buluttaki Verileri Bu Cihaza İndir")
            b_pull.clicked.connect(lambda: self._sec("PULL"))
            b_out = QPushButton("🚪 Bulut Hesabından Çıkış Yap")
            b_out.clicked.connect(lambda: self._sec("LOGOUT"))

            lay.addWidget(b_push)
            lay.addWidget(b_pull)
            lay.addWidget(b_out)
        else:
            info = QLabel("PC ve telefonunuzu otomatik eşitlemek için giriş yapın veya davet koduyla ücretsiz hesap oluşturun.")
            info.setWordWrap(True)
            lay.addWidget(info)

            grid = QGridLayout()
            self.t_email = QLineEdit()
            self.t_email.setPlaceholderText("ornek@eposta.com")
            self.t_pass = QLineEdit()
            self.t_pass.setEchoMode(QLineEdit.Password)
            self.t_pass.setPlaceholderText("En az 6 karakter")
            self.t_invite = QLineEdit()
            self.t_invite.setPlaceholderText("Yalnızca yeni kayıt için gerekli")

            grid.addWidget(QLabel("E-posta:"), 0, 0); grid.addWidget(self.t_email, 0, 1)
            grid.addWidget(QLabel("Şifre:"), 1, 0); grid.addWidget(self.t_pass, 1, 1)
            grid.addWidget(QLabel("Davet Kodu:"), 2, 0); grid.addWidget(self.t_invite, 2, 1)
            lay.addLayout(grid)

            hb = QHBoxLayout()
            b_in = QPushButton("Giriş Yap")
            b_in.clicked.connect(self.giris_tik)
            b_up = QPushButton("Yeni Hesap Oluştur")
            b_up.clicked.connect(self.kayit_tik)
            hb.addWidget(b_in); hb.addWidget(b_up)
            lay.addLayout(hb)

    def _sec(self, kod):
        self.aksiyon = kod
        self.accept()

    def giris_tik(self):
        em, pw = self.t_email.text().strip(), self.t_pass.text()
        if not em or len(pw) < 6:
            return QMessageBox.warning(self, "Eksik Bilgi", "Geçerli bir e-posta ve en az 6 karakterli şifre girin.")
        try:
            self.sb.giris_yap(em, pw)
            self.aksiyon = "LOGIN_OK"
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Giriş Hatası", str(e))

    def kayit_tik(self):
        em, pw = self.t_email.text().strip(), self.t_pass.text()
        kod = self.t_invite.text().strip()
        if not em or len(pw) < 6:
            return QMessageBox.warning(self, "Eksik Bilgi", "Geçerli bir e-posta ve en az 6 karakterli şifre girin.")
        if not kod:
            return QMessageBox.warning(self, "Davet Kodu Gerekli", "Yeni hesap oluşturmak için geçerli bir davet kodu girmelisiniz.")
        try:
            otomatik_giris = self.sb.kayit_ol(em, pw, kod)
            if otomatik_giris:
                self.aksiyon = "SIGNUP_OK"
                self.accept()
            else:
                QMessageBox.information(self, "Kayıt Başarılı", "Hesabınız oluşturuldu. Şimdi Giriş Yap butonuna basabilirsiniz.")
        except Exception as e:
            QMessageBox.warning(self, "Kayıt Hatası", str(e))


class PortfoyMotoru:
    """PyQt5 arayüzünden tamamen bağımsız veri okuma/yazma, hesaplama ve yedekleme katmanı."""
    def __init__(self, base_dir):
        self.d_dir = os.path.join(base_dir, "data")
        self.f_kasa = os.path.join(self.d_dir, "kasa.txt")
        self.f_hisse = os.path.join(self.d_dir, "sntlst.txt")
        self.f_islem = os.path.join(self.d_dir, "datac.txt")
        self.f_kom = os.path.join(self.d_dir, "komisyon.txt")
        self.f_tema = os.path.join(self.d_dir, "tema.txt")
        self.f_alarm = os.path.join(self.d_dir, "alarmlar.txt")
        self.f_sb_session = os.path.join(self.d_dir, "sb_session.json")
        self._id_sayac = 0

        os.makedirs(self.d_dir, exist_ok=True)
        for f in (self.f_kasa, self.f_hisse, self.f_islem, self.f_alarm):
            if not os.path.exists(f):
                open(f, "w", encoding="utf-8").close()
        if not os.path.exists(self.f_kom):
            self._atomik_yaz(self.f_kom, "10")

        self._ref_id_goc_kontrol()

    def yeni_ref_id(self):
        self._id_sayac = (self._id_sayac + 1) % 1000
        return f"R{int(time.time() * 1000)}{self._id_sayac:03d}"

    @staticmethod
    def _atomik_yaz(yol, icerik):
        gecici = yol + ".tmp"
        with open(gecici, "w", encoding="utf-8") as f:
            f.write(icerik)
        os.replace(gecici, yol)

    @staticmethod
    def _tr_to_iso(tr_tar):
        p = tr_tar.strip().split("-")
        return f"{p[2]}-{p[1]}-{p[0]}" if len(p) == 3 and len(p[0]) == 2 else tr_tar

    @staticmethod
    def _iso_to_tr(iso_tar):
        p = iso_tar.strip().split("-")
        return f"{p[2]}-{p[1]}-{p[0]}" if len(p) == 3 and len(p[0]) == 4 else iso_tar

    @staticmethod
    def _tarih_obj(tar_str):
        try:
            return datetime.strptime(tar_str.strip(), "%d-%m-%Y").date()
        except Exception:
            return None

    def _satirlari_oku(self, yol):
        try:
            if not os.path.exists(yol):
                return []
            with open(yol, encoding="utf-8") as f:
                return list(f)
        except Exception:
            return []

    def _ref_id_goc_kontrol(self):
        k_ham = self._satirlari_oku(self.f_kasa)
        i_ham = self._satirlari_oku(self.f_islem)

        k_eksik = any(
            len(s.strip().split("|")) >= 3 and (len(s.strip().split("|")) < 5 or not s.strip().split("|")[4].strip())
            for s in k_ham if s.strip()
        )
        i_eksik = any(
            len(s.strip().split("|")) >= 6 and (len(s.strip().split("|")) < 7 or not s.strip().split("|")[6].strip())
            for s in i_ham if s.strip()
        )
        if not k_eksik and not i_eksik:
            return

        k_kayitlar = []
        for s in k_ham:
            if not s.strip():
                continue
            p = s.strip().split("|")
            if len(p) < 3:
                k_kayitlar.append({"ham": s})
                continue
            detay = p[3].strip() if len(p) >= 4 else ""
            ref_id = p[4].strip() if len(p) >= 5 else ""
            try:
                tut_f = float(p[1])
            except Exception:
                tut_f = None
            k_kayitlar.append({
                "tip": p[0].strip(), "tut_str": p[1].strip(), "tut_f": tut_f,
                "tar": p[2].strip(), "detay": detay, "ref_id": ref_id
            })

        i_yeni = []
        for s in i_ham:
            if not s.strip():
                continue
            p = s.strip().split("|")
            if len(p) < 6:
                i_yeni.append(s)
                continue
            tip, hisse, fy, ad, kom, tar = [x.strip() for x in p[:6]]
            ref_id = p[6].strip() if len(p) >= 7 else ""
            if not ref_id:
                ref_id = self.yeni_ref_id()
                if tip in ("A", "S"):
                    try:
                        ff, ai, kf = float(fy), int(float(ad)), float(kom)
                        hedef_tip = "ALIS" if tip == "A" else "SATIS"
                        hedef_tut = (ff * ai) + kf if tip == "A" else (ff * ai) - kf
                        for kr in k_kayitlar:
                            if "ham" in kr or kr["ref_id"]:
                                continue
                            if (
                                kr["tip"] == hedef_tip
                                and kr["tar"] == tar
                                and kr["tut_f"] is not None
                                and abs(kr["tut_f"] - hedef_tut) < 0.02
                            ):
                                kr["ref_id"] = ref_id
                                if not kr["detay"]:
                                    kr["detay"] = hisse.upper()
                                break
                    except Exception:
                        pass
            i_yeni.append(f"{tip}|{hisse.upper()}|{fy}|{ad}|{kom}|{tar}|{ref_id}\n")

        k_yeni = []
        for kr in k_kayitlar:
            if "ham" in kr:
                k_yeni.append(kr["ham"])
                continue
            if not kr["ref_id"]:
                kr["ref_id"] = self.yeni_ref_id()
            k_yeni.append(f"{kr['tip']}|{kr['tut_str']}|{kr['tar']}|{kr['detay']}|{kr['ref_id']}\n")

        self._atomik_yaz(self.f_kasa, "".join(k_yeni))
        self._atomik_yaz(self.f_islem, "".join(i_yeni))

    @staticmethod
    def _pozisyon_guncelle(pf, x):
        h = x["hisse"]
        tip, ff, ai, kf = x["tip"], x["fiyat"], x["adet"], x["kom"]
        if h not in pf:
            pf[h] = {"adet": 0, "mal": 0.0, "ort": 0.0}
        p = pf[h]
        realize = 0.0
        uyari = None

        if tip == "A":
            p["adet"] += ai
            p["mal"] += (ff * ai) + kf
            p["ort"] = p["mal"] / p["adet"] if p["adet"] > 0 else 0.0
        elif tip == "B":
            p["adet"] += ai
            p["ort"] = p["mal"] / p["adet"] if p["adet"] > 0 else 0.0
        elif tip == "S":
            if p["adet"] <= 0:
                uyari = f"{h} ({x['tarih']}): Elde lot yokken {tr_sayi(ai)} lot satış kaydı tespit edildi."
                return 0.0, uyari
            satilan = ai
            if ai > p["adet"]:
                uyari = f"{h} ({x['tarih']}): Satış adedi ({tr_sayi(ai)}) eldekinden ({tr_sayi(p['adet'])}) fazla; mevcut lotla sınırlandırıldı."
                satilan = p["adet"]
            kom_payi = kf * (satilan / ai) if ai > 0 else 0.0
            realize = ((ff * satilan) - kom_payi) - (p["ort"] * satilan)
            p["adet"] -= satilan
            if p["adet"] <= 0:
                pf[h] = {"adet": 0, "mal": 0.0, "ort": 0.0}
            else:
                p["mal"] = p["adet"] * p["ort"]

        return realize, uyari

    def tema_oku(self):
        try:
            with open(self.f_tema, encoding="utf-8") as ft:
                okunan = ft.read().strip().lower()
                if okunan in ("dark", "light"):
                    return okunan
        except Exception:
            pass
        return "dark"

    def tema_kaydet(self, mod):
        try:
            self._atomik_yaz(self.f_tema, mod)
        except Exception:
            pass

    def komisyon_orani_oku(self):
        try:
            with open(self.f_kom, encoding="utf-8") as fk:
                return fk.read().strip() or "10"
        except Exception:
            return "10"

    def komisyon_orani_kaydet(self, oran_metin):
        try:
            self._atomik_yaz(self.f_kom, oran_metin.strip() or "0")
        except Exception:
            pass

    def hisseleri_oku(self):
        return [s.strip().upper() for s in self._satirlari_oku(self.f_hisse) if s.strip()]

    def hisse_ekle(self, kod):
        kod = kod.strip().upper()
        mev = self.hisseleri_oku()
        if not kod or kod in mev:
            return False
        mev.append(kod)
        self._atomik_yaz(self.f_hisse, "".join(h + "\n" for h in mev))
        return True

    def hisse_sil(self, kod):
        kod = kod.strip().upper()
        mev = [h for h in self.hisseleri_oku() if h != kod]
        self._atomik_yaz(self.f_hisse, "".join(h + "\n" for h in mev))

    def alarmlari_oku(self):
        alarmlar = {}
        for s in self._satirlari_oku(self.f_alarm):
            p = s.strip().split("|")
            if len(p) >= 3:
                try:
                    h, hedef, stop = p[0].upper(), float(p[1]), float(p[2])
                    if hedef > 0 or stop > 0:
                        alarmlar[h] = {"hedef": hedef, "stop": stop}
                except Exception:
                    continue
        return alarmlar

    def alarmlari_kaydet(self, alarmlar):
        satirlar = [
            f"{h.upper()}|{v['hedef']:.2f}|{v['stop']:.2f}\n"
            for h, v in alarmlar.items()
            if v["hedef"] > 0 or v["stop"] > 0
        ]
        self._atomik_yaz(self.f_alarm, "".join(satirlar))

    def kasa_kayitlari_oku(self):
        kayitlar = []
        for idx, s in enumerate(self._satirlari_oku(self.f_kasa)):
            p = s.strip().split("|")
            if len(p) < 3:
                continue
            try:
                tip = p[0].strip()
                tutar = float(p[1])
                tarih = p[2].strip()
                detay = p[3].strip() if len(p) >= 4 else ""
                ref_id = p[4].strip() if len(p) >= 5 else ""
                kayitlar.append({
                    "idx": idx, "tip": tip, "tutar": tutar, "tarih": tarih,
                    "tarih_dt": self._tarih_obj(tarih), "detay": detay, "ref_id": ref_id
                })
            except Exception:
                continue
        return kayitlar

    def islem_kayitlari_oku(self):
        kayitlar = []
        for idx, s in enumerate(self._satirlari_oku(self.f_islem)):
            p = s.strip().split("|")
            if len(p) < 6:
                continue
            try:
                tip = p[0].strip()
                hisse = p[1].strip().upper()
                fiyat = float(p[2])
                adet = int(float(p[3]))
                kom = float(p[4])
                tarih = p[5].strip()
                ref_id = p[6].strip() if len(p) >= 7 else ""
                kayitlar.append({
                    "idx": idx, "tip": tip, "hisse": hisse, "fiyat": fiyat,
                    "adet": adet, "kom": kom, "tarih": tarih,
                    "tarih_dt": self._tarih_obj(tarih), "ref_id": ref_id
                })
            except Exception:
                continue
        return kayitlar

    def hesapla(self):
        kasalar = self.kasa_kayitlari_oku()
        islemler = self.islem_kayitlari_oku()

        bakiye = 0.0
        for k in kasalar:
            bakiye += k["tutar"] if k["tip"] in ("KE", "SATIS", "TEMETTU") else -k["tutar"]
        bakiye = round(bakiye, 2)

        pf = {}
        uyarilar = []
        for x in islemler:
            _, uyari = self._pozisyon_guncelle(pf, x)
            if uyari:
                uyarilar.append(uyari)

        return bakiye, pf, islemler, kasalar, uyarilar

    def kasa_ekle(self, tip, tutar, tarih, detay=""):
        ref_id = self.yeni_ref_id()
        with open(self.f_kasa, "a", encoding="utf-8") as f:
            f.write(f"{tip}|{tutar:.2f}|{tarih}|{detay.upper()}|{ref_id}\n")
        return ref_id

    def islem_ekle(self, tip, hisse, fiyat, adet, kom, tarih):
        hisse = hisse.strip().upper()
        ref_id = self.yeni_ref_id()
        if tip == "A":
            mal = (fiyat * adet) + kom
            with open(self.f_kasa, "a", encoding="utf-8") as fk:
                fk.write(f"ALIS|{mal:.2f}|{tarih}|{hisse}|{ref_id}\n")
        elif tip == "S":
            net = (fiyat * adet) - kom
            with open(self.f_kasa, "a", encoding="utf-8") as fk:
                fk.write(f"SATIS|{net:.2f}|{tarih}|{hisse}|{ref_id}\n")
        with open(self.f_islem, "a", encoding="utf-8") as fi:
            fi.write(f"{tip}|{hisse}|{fiyat:.2f}|{adet}|{kom:.2f}|{tarih}|{ref_id}\n")
        return ref_id

    def kayit_sil(self, kaynak, ref_id):
        if not ref_id:
            return False
        silindi = False

        if kaynak == "ISLEM":
            i_satirlar = self._satirlari_oku(self.f_islem)
            yeni_i = []
            for s in i_satirlar:
                p = s.strip().split("|")
                if len(p) >= 7 and p[6].strip() == ref_id:
                    silindi = True
                    continue
                yeni_i.append(s)
            if silindi:
                self._atomik_yaz(self.f_islem, "".join(yeni_i))

            k_satirlar = self._satirlari_oku(self.f_kasa)
            yeni_k = [
                s for s in k_satirlar
                if not (len(s.strip().split("|")) >= 5 and s.strip().split("|")[4].strip() == ref_id)
            ]
            if len(yeni_k) != len(k_satirlar):
                self._atomik_yaz(self.f_kasa, "".join(yeni_k))

        elif kaynak == "KASA":
            k_satirlar = self._satirlari_oku(self.f_kasa)
            yeni_k = []
            for s in k_satirlar:
                p = s.strip().split("|")
                if len(p) >= 5 and p[4].strip() == ref_id:
                    silindi = True
                    continue
                yeni_k.append(s)
            if silindi:
                self._atomik_yaz(self.f_kasa, "".join(yeni_k))

        return silindi

    def rapor_hesapla(self, tur, d1, d2):
        def aralikta(dt):
            return dt is not None and d1 <= dt <= d2

        if tur == "kom":
            return sum(x["kom"] for x in self.islem_kayitlari_oku() if aralikta(x["tarih_dt"]))
        elif tur == "cek":
            return sum(k["tutar"] for k in self.kasa_kayitlari_oku() if k["tip"] == "KC" and aralikta(k["tarih_dt"]))
        elif tur == "kz":
            pf, toplam_r = {}, 0.0
            for x in self.islem_kayitlari_oku():
                r, _ = self._pozisyon_guncelle(pf, x)
                if x["tip"] == "S" and aralikta(x["tarih_dt"]):
                    toplam_r += r
            return toplam_r
        return 0.0

    def mobil_json_olustur(self, alarmlar, fiyatlar, tema):
        base_id = int(time.time() * 1000)
        kasa_list = []
        ref_to_kasa_id = {}

        for idx, k in enumerate(self.kasa_kayitlari_oku()):
            kid = base_id + idx
            rid = k["ref_id"] or self.yeni_ref_id()
            kayit = {
                "id": kid,
                "tip": k["tip"],
                "tutar": k["tutar"],
                "tarih": self._tr_to_iso(k["tarih"]),
                "refId": rid
            }
            if k["detay"]:
                kayit["hisse"] = k["detay"]
            ref_to_kasa_id[rid] = kid
            kasa_list.append(kayit)

        islem_list = []
        for idx, x in enumerate(self.islem_kayitlari_oku()):
            iso_t = self._tr_to_iso(x["tarih"])
            rid = x["ref_id"] or f"R{base_id + 10000 + idx}"
            eslesen_kasa_id = ref_to_kasa_id.get(rid)
            islem_list.append({
                "id": base_id + 10000 + idx,
                "tip": x["tip"],
                "hisse": x["hisse"],
                "fiyat": x["fiyat"],
                "adet": x["adet"],
                "kom": x["kom"],
                "tarih": iso_t,
                "kasaId": eslesen_kasa_id,
                "refId": rid
            })

        return {
            "hisseler": self.hisseleri_oku(),
            "kasa": kasa_list,
            "islemler": islem_list,
            "alarmlar": alarmlar,
            "fiyatlar": fiyatlar,
            "komOran": self.komisyon_orani_oku(),
            "tema": tema
        }

    def mobil_json_yukle(self, veri):
        if not isinstance(veri, dict):
            raise ValueError("JSON kök yapısı geçerli bir nesne değil.")

        hisseler = veri.get("hisseler", [])
        kasa_list = veri.get("kasa", [])
        islem_list = veri.get("islemler", [])
        alarmlar_raw = veri.get("alarmlar", {})
        kom_oran = str(veri.get("komOran", "10")).strip() or "10"
        tema = str(veri.get("tema", "dark")).strip().lower()

        if not all(isinstance(x, list) for x in (hisseler, kasa_list, islem_list)):
            raise ValueError("hisseler, kasa ve islemler alanları liste olmalıdır.")
        if not isinstance(alarmlar_raw, dict):
            raise ValueError("alarmlar alanı nesne (dict) olmalıdır.")

        hisse_satirlari = [
            str(h).strip().upper() + "\n"
            for h in hisseler if str(h).strip()
        ]

        kasa_id_to_ref = {}
        islem_satirlari = []
        for idx, x in enumerate(islem_list):
            if not isinstance(x, dict):
                raise ValueError(f"İşlem kaydı #{idx + 1} geçersiz formatta.")
            tip = str(x.get("tip", "")).strip().upper()
            if tip not in ("A", "S", "B"):
                raise ValueError(f"İşlem kaydı #{idx + 1}: Geçersiz işlem tipi ({tip}).")
            h = str(x.get("hisse", "")).strip().upper()
            if not h:
                raise ValueError(f"İşlem kaydı #{idx + 1}: Hisse kodu boş.")
            fy = float(x.get("fiyat", 0))
            ad = int(float(x.get("adet", 0)))
            kom = float(x.get("kom", 0))
            tar = self._iso_to_tr(str(x.get("tarih", "")).strip())
            if self._tarih_obj(tar) is None:
                raise ValueError(f"İşlem kaydı #{idx + 1}: Geçersiz tarih ({x.get('tarih')}).")
            rid = str(x.get("refId") or f"R{x.get('id', self.yeni_ref_id())}").strip()
            if x.get("kasaId") is not None:
                kasa_id_to_ref[x["kasaId"]] = rid
            islem_satirlari.append(f"{tip}|{h}|{fy:.2f}|{ad}|{kom:.2f}|{tar}|{rid}\n")

        kasa_satirlari = []
        for idx, k in enumerate(kasa_list):
            if not isinstance(k, dict):
                raise ValueError(f"Kasa kaydı #{idx + 1} geçersiz formatta.")
            tip = str(k.get("tip", "")).strip().upper()
            if tip not in ("KE", "KC", "ALIS", "SATIS", "TEMETTU"):
                raise ValueError(f"Kasa kaydı #{idx + 1}: Geçersiz kasa tipi ({tip}).")
            tut = float(k.get("tutar", 0))
            tar = self._iso_to_tr(str(k.get("tarih", "")).strip())
            if self._tarih_obj(tar) is None:
                raise ValueError(f"Kasa kaydı #{idx + 1}: Geçersiz tarih ({k.get('tarih')}).")
            detay = str(k.get("hisse", "")).strip().upper()
            rid = str(k.get("refId") or kasa_id_to_ref.get(k.get("id"), self.yeni_ref_id())).strip()
            kasa_satirlari.append(f"{tip}|{tut:.2f}|{tar}|{detay}|{rid}\n")

        alarmlar = {}
        for h, v in alarmlar_raw.items():
            if not isinstance(v, dict):
                raise ValueError(f"Alarm kaydı ({h}) geçersiz formatta.")
            hedef = float(v.get("hedef", 0))
            stop = float(v.get("stop", 0))
            if hedef > 0 or stop > 0:
                alarmlar[str(h).strip().upper()] = {"hedef": hedef, "stop": stop}

        self._atomik_yaz(self.f_hisse, "".join(hisse_satirlari))
        self._atomik_yaz(self.f_kasa, "".join(kasa_satirlari))
        self._atomik_yaz(self.f_islem, "".join(islem_satirlari))
        self.alarmlari_kaydet(alarmlar)
        self.komisyon_orani_kaydet(kom_oran)
        if tema in ("dark", "light"):
            self.tema_kaydet(tema)
        else:
            tema = self.tema_oku()

        return alarmlar, kom_oran, tema


class ParaLineEdit(QLineEdit):
    def __init__(self, ondalik=True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ondalik = ondalik
        self.textEdited.connect(self._formatla)

    def _formatla(self, metin):
        if not metin:
            return
        pos = self.cursorPosition()
        sol_metin = metin[:pos]
        anlamli_sol = sum(1 for c in sol_metin if c.isdigit() or (self.ondalik and c == ","))

        temiz = "".join(c for c in metin if c.isdigit() or (self.ondalik and c == ","))
        if self.ondalik and "," in temiz:
            parcalar = temiz.split(",")
            tam_kisim = parcalar[0]
            ondalik_kisim = "".join(parcalar[1:])[:2]
            virgul_var = True
        else:
            tam_kisim = temiz.replace(",", "")
            ondalik_kisim = ""
            virgul_var = False

        if tam_kisim:
            tam_formatli = f"{int(tam_kisim):,}".replace(",", ".")
        else:
            tam_formatli = "0" if virgul_var else ""
            if virgul_var and "," in sol_metin:
                anlamli_sol += 1

        yeni_metin = f"{tam_formatli},{ondalik_kisim}" if virgul_var else tam_formatli

        if yeni_metin != metin:
            yeni_pos = 0
            sayac = 0
            for i, c in enumerate(yeni_metin):
                if sayac >= anlamli_sol:
                    break
                if c.isdigit() or (self.ondalik and c == ","):
                    sayac += 1
                yeni_pos = i + 1

            self.blockSignals(True)
            self.setText(yeni_metin)
            self.setCursorPosition(yeni_pos)
            self.blockSignals(False)


class TemettuBedelsizDialog(QDialog):
    def __init__(self, hisseler, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Temettü / Bedelsiz İşlemi")
        self.setMinimumWidth(380)
        self.sonuc = None

        ana = QVBoxLayout(self)
        self.tabs = QTabWidget()

        w_tem = QWidget()
        l_tem = QGridLayout(w_tem)
        self.cmb_tem = QComboBox(); self.cmb_tem.addItems(hisseler)
        self.t_tem_tut = ParaLineEdit(ondalik=True); self.t_tem_tut.setPlaceholderText("Net Toplam Tutar (TL)")
        self.dt_tem = QDateEdit(QDate.currentDate()); self.dt_tem.setCalendarPopup(True); self.dt_tem.setDisplayFormat("dd-MM-yyyy")
        b_tem_ok = QPushButton("Nakit Temettüyü Kasaya Ekle")
        b_tem_ok.clicked.connect(self.temettu_onayla)
        l_tem.addWidget(QLabel("Hisse:"), 0, 0); l_tem.addWidget(self.cmb_tem, 0, 1)
        l_tem.addWidget(QLabel("Net Tutar (TL):"), 1, 0); l_tem.addWidget(self.t_tem_tut, 1, 1)
        l_tem.addWidget(QLabel("Tarih:"), 2, 0); l_tem.addWidget(self.dt_tem, 2, 1)
        l_tem.addWidget(b_tem_ok, 3, 0, 1, 2)
        self.tabs.addTab(w_tem, "Nakit Temettü")

        w_bed = QWidget()
        l_bed = QGridLayout(w_bed)
        self.cmb_bed = QComboBox(); self.cmb_bed.addItems(hisseler)
        self.t_bed_ad = ParaLineEdit(ondalik=False); self.t_bed_ad.setPlaceholderText("Yeni Gelen Bedelsiz Lot")
        self.dt_bed = QDateEdit(QDate.currentDate()); self.dt_bed.setCalendarPopup(True); self.dt_bed.setDisplayFormat("dd-MM-yyyy")
        b_bed_ok = QPushButton("Bedelsiz Lotları Portföye Ekle")
        b_bed_ok.clicked.connect(self.bedelsiz_onayla)
        l_bed.addWidget(QLabel("Hisse:"), 0, 0); l_bed.addWidget(self.cmb_bed, 0, 1)
        l_bed.addWidget(QLabel("Yeni Lot Adedi:"), 1, 0); l_bed.addWidget(self.t_bed_ad, 1, 1)
        l_bed.addWidget(QLabel("Tarih:"), 2, 0); l_bed.addWidget(self.dt_bed, 2, 1)
        l_bed.addWidget(b_bed_ok, 3, 0, 1, 2)
        self.tabs.addTab(w_bed, "Bedelsiz Bölünme")

        ana.addWidget(self.tabs)

    def _parse(self, s, tp=float):
        try:
            t = s.strip().replace(".", "").replace(",", ".")
            if not t: return None
            v = tp(float(t)) if tp == int else tp(t)
            return v if v > 0 else None
        except Exception:
            return None

    def temettu_onayla(self):
        h = self.cmb_tem.currentText().strip().upper()
        tut = self._parse(self.t_tem_tut.text(), float)
        if not h or not tut:
            return QMessageBox.warning(self, "Eksik Bilgi", "Lütfen geçerli bir hisse ve net temettü tutarı girin.")
        self.sonuc = ("TEMETTU", h, tut, self.dt_tem.date().toString("dd-MM-yyyy"))
        self.accept()

    def bedelsiz_onayla(self):
        h = self.cmb_bed.currentText().strip().upper()
        ad = self._parse(self.t_bed_ad.text(), int)
        if not h or not ad:
            return QMessageBox.warning(self, "Eksik Bilgi", "Lütfen geçerli bir hisse ve bedelsiz lot adedi girin.")
        self.sonuc = ("BEDELSIZ", h, ad, self.dt_bed.date().toString("dd-MM-yyyy"))
        self.accept()


class AlarmDialog(QDialog):
    def __init__(self, hisse, mevcut_hedef=0.0, mevcut_stop=0.0, guncel_fiyat=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{hisse} // Hedef & Stop-Loss Alarmı")
        self.setMinimumWidth(340)
        self.sonuc = None

        lay = QGridLayout(self)
        gf_yazi = f"{tr_para(guncel_fiyat)} TL" if guncel_fiyat is not None else "Bilinmiyor"
        lay.addWidget(QLabel(f"Hisse: {hisse}   |   Güncel: {gf_yazi}"), 0, 0, 1, 2)

        self.t_hedef = ParaLineEdit(ondalik=True)
        self.t_hedef.setPlaceholderText("Üst Hedef Fiyat (0 = Kapalı)")
        if mevcut_hedef > 0:
            self.t_hedef.setText(tr_para(mevcut_hedef))

        self.t_stop = ParaLineEdit(ondalik=True)
        self.t_stop.setPlaceholderText("Stop-Loss Fiyatı (0 = Kapalı)")
        if mevcut_stop > 0:
            self.t_stop.setText(tr_para(mevcut_stop))

        b_kaydet = QPushButton("Alarmı Kaydet")
        b_kaydet.clicked.connect(self.kaydet)
        b_sil = QPushButton("Alarmı Kaldır")
        b_sil.clicked.connect(self.kaldir)

        lay.addWidget(QLabel("Hedef Fiyat (≥):"), 1, 0); lay.addWidget(self.t_hedef, 1, 1)
        lay.addWidget(QLabel("Stop-Loss (≤):"), 2, 0); lay.addWidget(self.t_stop, 2, 1)
        lay.addWidget(b_kaydet, 3, 0); lay.addWidget(b_sil, 3, 1)

    def _parse(self, s):
        try:
            t = s.strip().replace(".", "").replace(",", ".")
            return float(t) if t else 0.0
        except Exception:
            return 0.0

    def kaydet(self):
        h = self._parse(self.t_hedef.text())
        s = self._parse(self.t_stop.text())
        self.sonuc = (0.0, 0.0) if (h <= 0 and s <= 0) else (h, s)
        self.accept()

    def kaldir(self):
        self.sonuc = (0.0, 0.0)
        self.accept()


class DodniPastaGrafik(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.veriler = {}
        self.tema = "dark"
        self.setMinimumWidth(300)
        self.setMinimumHeight(230)
        self.renkler_dark = [
            QColor("#00d2ff"), QColor("#ffaa00"), QColor("#2ecc71"), QColor("#e74c3c"),
            QColor("#9b59b6"), QColor("#3498db"), QColor("#e67e22"), QColor("#1abc9c"),
        ]
        self.renkler_light = [
            QColor("#0f4c81"), QColor("#d97706"), QColor("#15803d"), QColor("#dc2626"),
            QColor("#7c3aed"), QColor("#0284c7"), QColor("#ea580c"), QColor("#0d9488"),
        ]

    def set_tema(self, mod):
        self.tema = mod
        self.update()

    def guncelle(self, yeni_veriler):
        self.veriler = {k: v for k, v in yeni_veriler.items() if v > 0}
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        koyu = (self.tema == "dark")

        bg_renk = QColor("#090d12") if koyu else QColor("#ffffff")
        cerceve_renk = QColor("#1c3144") if koyu else QColor("#cbd5e1")
        vurgu_renk = QColor("#00d2ff") if koyu else QColor("#0f4c81")
        bos_yazi_renk = QColor("#5c768d") if koyu else QColor("#64748b")
        merkez_yazi_renk = QColor("#e2eef7") if koyu else QColor("#0f172a")
        lejant_yazi_renk = QColor("#d0e1f0") if koyu else QColor("#1e293b")
        palet = self.renkler_dark if koyu else self.renkler_light

        painter.fillRect(0, 0, w, h, bg_renk)

        painter.setPen(QPen(cerceve_renk, 1))
        painter.drawRect(0, 0, w - 1, h - 1)
        painter.setPen(QPen(vurgu_renk, 2))
        painter.drawLine(0, 0, 12, 0); painter.drawLine(0, 0, 0, 12)
        painter.drawLine(w-1, h-1, w-13, h-1); painter.drawLine(w-1, h-1, w-1, h-13)

        toplam = sum(self.veriler.values())
        if toplam <= 0:
            painter.setPen(bos_yazi_renk)
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            painter.drawText(self.rect(), Qt.AlignCenter, "PORTFÖY VERİSİ YOK")
            return

        sirali = sorted(self.veriler.items(), key=lambda x: x[1], reverse=True)

        cap = min(int(w * 0.48), h - 28)
        cap = max(cap, 90)
        sol_x = 14
        ust_y = (h - cap) // 2
        rect = QRectF(sol_x, ust_y, cap, cap)

        baslangic_aci = 90 * 16
        for i, (hisse, deger) in enumerate(sirali):
            oran = deger / toplam
            yay_aci = -int(round(oran * 360 * 16))
            if i == len(sirali) - 1:
                yay_aci = -(360 * 16) - (baslangic_aci - 90 * 16)

            renk = palet[i % len(palet)]
            painter.setBrush(renk)
            painter.setPen(QPen(bg_renk, 2))
            painter.drawPie(rect, baslangic_aci, yay_aci)
            baslangic_aci += yay_aci

        ic_cap = cap * 0.58
        ic_rect = QRectF(sol_x + (cap - ic_cap) / 2, ust_y + (cap - ic_cap) / 2, ic_cap, ic_cap)
        painter.setBrush(bg_renk)
        painter.setPen(QPen(vurgu_renk, 1))
        painter.drawEllipse(ic_rect)

        painter.setPen(merkez_yazi_renk)
        painter.setFont(QFont("Bahnschrift", 9, QFont.Bold))
        painter.drawText(ic_rect, Qt.AlignCenter, f"TOPLAM\n{tr_para(toplam)}")

        lejant_x = int(sol_x + cap + 16)
        lejant_y = max(18, ust_y + 4)
        satir_yukseklik = 22

        painter.setFont(QFont("Consolas", 10, QFont.Bold))
        for i, (hisse, deger) in enumerate(sirali[:8]):
            if lejant_y + satir_yukseklik > h - 6:
                break
            renk = palet[i % len(palet)]
            yuzde = (deger / toplam) * 100

            painter.setBrush(renk)
            painter.setPen(QPen(bg_renk, 1))
            painter.drawRect(lejant_x, lejant_y, 12, 12)

            painter.setPen(lejant_yazi_renk)
            painter.drawText(lejant_x + 18, lejant_y + 11, f"{hisse:<5} %{yuzde:4.1f}")
            lejant_y += satir_yukseklik


class FiyatThread(QThread):
    hazir = pyqtSignal(dict)
    hata = pyqtSignal(str)

    def __init__(self, hisseler):
        super().__init__()
        self.hisseler = [h.strip().upper() for h in hisseler if h.strip()]

    def run(self):
        import yfinance as yf
        sonuc = {}
        if not self.hisseler:
            return
        try:
            semboller = [f"{h}.IS" for h in self.hisseler]
            df = yf.download(semboller, period="5d", progress=False, threads=False)
            if df is not None and not df.empty and "Close" in df:
                close_df = df["Close"]
                if len(self.hisseler) == 1:
                    s = close_df.dropna()
                    if not s.empty:
                        val = s.iloc[-1]
                        if hasattr(val, "iloc"):
                            val = val.iloc[0]
                        sonuc[self.hisseler[0]] = round(float(val), 2)
                else:
                    for h in self.hisseler:
                        sembol = f"{h}.IS"
                        if sembol in close_df:
                            s = close_df[sembol].dropna()
                            if not s.empty:
                                val = s.iloc[-1]
                                if hasattr(val, "iloc"):
                                    val = val.iloc[0]
                                sonuc[h] = round(float(val), 2)
            if not sonuc:
                self.hata.emit("Veri alınamadı. Hisse kodunu veya internet bağlantınızı kontrol edin.")
            else:
                self.hazir.emit(sonuc)
        except Exception as e:
            self.hata.emit(f"Bağlantı/Hız Sınırı Hatası: {str(e)}")


class DodniPortfoyApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(" DODNI // PORTFÖY YÖNETİMİ ")
        self.resize(1420, 860)

        base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        self.motor = PortfoyMotoru(base)
        self.sb = SupabaseClient(self.motor.f_sb_session)

        self.fiyatlar = {}
        self.alarmlar = self.motor.alarmlari_oku()
        self.tetiklenen_alarmlar = set()
        self.tema = self.motor.tema_oku()

        self._cache_portfoy = {}
        self._cache_bakiye = 0.0
        self._gosterilen_veri_uyari = None
        self.th = None
        self.sync_th = None
        self._eski_threadler = []
        self._bekleyen_sync = None  # None, "PUSH" veya ("PULL", sessiz_bool)
        self.son_fiyat_zamani = 0.0
        self.fiyat_cooldown_sn = 45

        self.ui()
        self.tema_uygula(self.tema)
        self.bulut_buton_guncelle()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.statusBar().clearMessage)

        self.oto_timer = QTimer(self)
        self.oto_timer.timeout.connect(lambda: self.fiyat_cek(sessiz=True))

        self.yukle()
        if self.sb.giris_yapildi_mi():
            QTimer.singleShot(1200, lambda: self.bulut_cek_baslat(sessiz=True))

    def closeEvent(self, event):
        self.oto_timer.stop()
        for t in [self.th, self.sync_th] + self._eski_threadler:
            if t is not None and t.isRunning():
                t.wait(1500)
        event.accept()

    def bulut_buton_guncelle(self):
        if self.sb.giris_yapildi_mi():
            mail = self.sb.kullanici_email()
            kisa = mail.split("@")[0] if "@" in mail else mail
            self.btn_bulut.setText(f"☁ {kisa}")
            self.btn_bulut.setToolTip(f"Bulut Senkronizasyonu Aktif ({mail})")
        else:
            self.btn_bulut.setText("☁ Bulut Giriş")
            self.btn_bulut.setToolTip("PC ve telefonunuzu otomatik eşitlemek için giriş yapın")

    def bulut_pencere_ac(self):
        dlg = BulutDialog(self.sb, self)
        if dlg.exec_() == QDialog.Accepted:
            self.bulut_buton_guncelle()
            if dlg.aksiyon in ("LOGIN_OK", "SIGNUP_OK"):
                self.msg(f"Bulut hesabına bağlanıldı ({self.sb.kullanici_email()}). Eşitleniyor...")
                self.bulut_cek_baslat(sessiz=False)
            elif dlg.aksiyon == "PUSH":
                self.bulut_gonder_baslat(sessiz=False)
            elif dlg.aksiyon == "PULL":
                self.bulut_cek_baslat(sessiz=False)
            elif dlg.aksiyon == "LOGOUT":
                self._bekleyen_sync = None
                self.sb.cikis_yap()
                self.bulut_buton_guncelle()
                self.msg("Bulut hesabından çıkış yapıldı.")

    def bulut_gonder_baslat(self, sessiz=True):
        if not self.sb.giris_yapildi_mi():
            return
        if self.sync_th is not None and self.sync_th.isRunning():
            if not isinstance(self._bekleyen_sync, tuple):
                self._bekleyen_sync = "PUSH"
            return
        payload = self.motor.mobil_json_olustur(self.alarmlar, self.fiyatlar, self.tema)
        self.sync_th = BulutSyncThread(self.sb, "PUSH", payload)
        self.sync_th.tamamlandi.connect(lambda mod, res: self._sync_tamamlandi(mod, res, sessiz))
        self.sync_th.hata.connect(lambda mod, err: self._sync_hata(mod, err, sessiz))
        self.sync_th.finished.connect(self._sync_thread_temizle)
        self.sync_th.start()

    def bulut_cek_baslat(self, sessiz=True):
        if not self.sb.giris_yapildi_mi():
            return
        if self.sync_th is not None and self.sync_th.isRunning():
            self._bekleyen_sync = ("PULL", sessiz)
            return
        self.sync_th = BulutSyncThread(self.sb, "PULL")
        self.sync_th.tamamlandi.connect(lambda mod, res: self._sync_tamamlandi(mod, res, sessiz))
        self.sync_th.hata.connect(lambda mod, err: self._sync_hata(mod, err, sessiz))
        self.sync_th.finished.connect(self._sync_thread_temizle)
        self.sync_th.start()

    def _sync_thread_temizle(self):
        if self.sync_th is not None:
            t = self.sync_th
            self.sync_th = None
            t.wait(1000)
            if t.isRunning():
                self._eski_threadler.append(t)
            else:
                t.deleteLater()
        self._eski_threadler = [t for t in self._eski_threadler if t.isRunning()]
        bekleyen = self._bekleyen_sync
        self._bekleyen_sync = None
        if isinstance(bekleyen, tuple) and bekleyen[0] == "PULL":
            self.bulut_cek_baslat(sessiz=bekleyen[1])
        elif bekleyen == "PUSH":
            self.bulut_gonder_baslat(sessiz=True)

    def _sync_hata(self, mod, err, sessiz):
        if not sessiz:
            QMessageBox.warning(self, "Bulut Senkronizasyon Hatası", err)
        else:
            self.msg(f"Bulut uyarısı: {err}")

    def _sync_tamamlandi(self, mod, res, sessiz):
        if mod == "PUSH":
            if not sessiz:
                self.msg("Veriler buluta başarıyla kaydedildi.")
        elif mod == "PULL":
            if not res or not isinstance(res.get("data"), dict):
                self.bulut_gonder_baslat(sessiz=True)
                if not sessiz:
                    self.msg("Bulutta kayıt bulunamadı; bu cihazdaki veriler buluta yüklendi.")
                return

            bulut_veri = res["data"]
            bulut_zaman = iso_zaman_tr(res.get("updated_at"))
            yerel_veri = self.motor.mobil_json_olustur(self.alarmlar, self.fiyatlar, self.tema)
            if json.dumps(bulut_veri, sort_keys=True) == json.dumps(yerel_veri, sort_keys=True):
                if not sessiz:
                    self.msg(f"Bulut ve yerel verileriniz zaten güncel (Son bulut kaydı: {bulut_zaman}).")
                return

            yerel_bos = (len(yerel_veri["islemler"]) == 0 and len(yerel_veri["kasa"]) == 0)
            bulut_bos = (len(bulut_veri.get("islemler", [])) == 0 and len(bulut_veri.get("kasa", [])) == 0)

            if bulut_bos and not yerel_bos:
                self.bulut_gonder_baslat(sessiz=True)
                return

            uygula = True
            if not yerel_bos:
                onay = QMessageBox.question(
                    self, "Bulut Verisi Güncellemesi",
                    f"Bulut hesabınızda bu cihazdakinden farklı bir portföy kaydı bulundu.\n"
                    f"Son Bulut Güncellemesi: {bulut_zaman}\n\n"
                    "• Evet: Buluttaki verileri bu cihaza indir\n"
                    "• Hayır: Bu cihazdaki verileri koru ve buluta yaz",
                    QMessageBox.Yes | QMessageBox.No
                )
                if onay != QMessageBox.Yes:
                    uygula = False
                    self.bulut_gonder_baslat(sessiz=False)

            if uygula:
                try:
                    alarmlar, kom_oran, tema = self.motor.mobil_json_yukle(bulut_veri)
                    self.alarmlar = alarmlar
                    self.t_oran.setText(kom_oran)
                    if tema in ("dark", "light"):
                        self.tema = tema
                        self.tema_uygula(tema)
                    if isinstance(bulut_veri.get("fiyatlar"), dict):
                        self.fiyatlar.update(bulut_veri["fiyatlar"])
                    self.yukle()
                    self.msg(f"Buluttaki veriler ({bulut_zaman}) cihaza aktarıldı.")
                except Exception as e:
                    QMessageBox.warning(self, "Bulut Veri Hatası", str(e))

    def alarmlari_kontrol_et(self):
        uyarilar = []
        for h, v in self.alarmlar.items():
            gf = self.fiyatlar.get(h)
            if gf is None:
                continue
            if v["hedef"] > 0 and gf >= v["hedef"]:
                anahtar = (h, "HEDEF", v["hedef"])
                if anahtar not in self.tetiklenen_alarmlar:
                    self.tetiklenen_alarmlar.add(anahtar)
                    uyarilar.append(f"🎯 HEDEF ULAŞILDI: {h} güncel {tr_para(gf)} TL (Hedef: {tr_para(v['hedef'])} TL)")
            if v["stop"] > 0 and gf <= v["stop"]:
                anahtar = (h, "STOP", v["stop"])
                if anahtar not in self.tetiklenen_alarmlar:
                    self.tetiklenen_alarmlar.add(anahtar)
                    uyarilar.append(f"🛑 STOP-LOSS TETİKLENDİ: {h} güncel {tr_para(gf)} TL (Stop: {tr_para(v['stop'])} TL)")
        if uyarilar:
            QApplication.beep()
            QMessageBox.information(self, "Fiyat Alarmı Tetiklendi!", "\n\n".join(uyarilar))

    def tema_degistir(self):
        yeni_mod = "light" if self.tema == "dark" else "dark"
        self.tema = yeni_mod
        self.motor.tema_kaydet(yeni_mod)
        self.tema_uygula(yeni_mod)
        self.yukle()
        self.bulut_gonder_baslat(sessiz=True)
        self.msg("Aydınlık Mod aktif edildi." if yeni_mod == "light" else "Karanlık Mod aktif edildi.")

    def tema_uygula(self, mod):
        if mod == "dark":
            self.setStyleSheet("""
                QMainWindow, QWidget, QDialog {
                    background-color: #070a0e;
                    color: #d8e6f2;
                    font-family: 'Bahnschrift', 'Segoe UI Semibold', 'Segoe UI', sans-serif;
                    font-size: 14px;
                }
                QGroupBox {
                    background-color: #0d131a;
                    border: 1px solid #1c3144;
                    border-top: 2px solid #00d2ff;
                    border-radius: 2px;
                    margin-top: 16px;
                    padding-top: 14px;
                    font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    left: 12px;
                    padding: 2px 8px;
                    background-color: #070a0e;
                    border: 1px solid #00d2ff;
                    color: #00d2ff;
                    font-size: 13px;
                    letter-spacing: 1px;
                }
                QTabWidget::pane { border: 1px solid #1c3144; background-color: #0d131a; }
                QTabBar::tab {
                    background-color: #101c28; color: #8fa3b8;
                    padding: 7px 14px; border: 1px solid #1c3144; font-weight: bold;
                }
                QTabBar::tab:selected {
                    background-color: #005577; color: #ffffff; border-bottom: 2px solid #00d2ff;
                }
                QLineEdit, QComboBox, QDateEdit {
                    background-color: #121b24; border: 1px solid #26415a; border-radius: 2px;
                    padding: 6px 8px; color: #ffffff;
                    font-family: 'Consolas', 'Segoe UI', monospace; font-size: 14px; font-weight: bold;
                }
                QLineEdit:focus, QComboBox:focus, QDateEdit:focus {
                    border: 1px solid #00d2ff; background-color: #162430;
                }
                QComboBox QAbstractItemView {
                    background-color: #121b24; color: #ffffff;
                    selection-background-color: #006b8f; selection-color: #ffffff;
                }
                QPushButton {
                    background-color: #132230; border: 1px solid #0099cc; border-radius: 2px;
                    color: #e0f2fe; padding: 7px 10px; font-size: 13px; font-weight: bold; letter-spacing: 0.4px;
                }
                QPushButton:hover { background-color: #005577; border: 1px solid #00d2ff; color: #ffffff; }
                QPushButton:pressed { background-color: #00334d; }
                QPushButton:disabled { background-color: #0f161d; color: #4a6075; border: 1px solid #1c2b38; }
                QTableWidget {
                    background-color: #090d12; alternate-background-color: #0e151d;
                    gridline-color: #1b2d3e; border: 1px solid #1c3144; color: #ffffff;
                    font-family: 'Consolas', 'Segoe UI', monospace; font-size: 14px;
                }
                QTableWidget::item { padding: 4px 8px; }
                QTableWidget::item:selected { background-color: #004d66; color: #00d2ff; }
                QHeaderView::section {
                    background-color: #101c28; color: #ffaa00; border: 1px solid #1c3144;
                    border-bottom: 2px solid #ffaa00; padding: 7px 8px; font-weight: bold; font-size: 13px;
                }
                QTableCornerButton::section { background-color: #101c28; border: 1px solid #1c3144; }
                QListWidget {
                    background-color: #090d12; border: 1px solid #1c3144; color: #d0e1f0;
                    font-family: 'Consolas', monospace; font-size: 13px; padding: 4px;
                }
                QListWidget::item { padding: 5px; border-bottom: 1px solid #131d28; }
                QListWidget::item:selected { background-color: #004d66; color: #ffaa00; }
                QMenu { background-color: #101c28; border: 1px solid #00d2ff; color: #ffffff; font-weight: bold; }
                QMenu::item { padding: 6px 20px; }
                QMenu::item:selected { background-color: #005577; color: #ffffff; }
                QStatusBar {
                    background-color: #05070a; color: #00d2ff; border-top: 1px solid #1c3144;
                    font-weight: bold; font-size: 13px;
                }
            """)
            ozet_renk = "#ffaa00"
            vurgu_renk = "#00d2ff"
            self.btn_kaydet.setStyleSheet("background-color:#005577; border:1px solid #00d2ff; color:#ffffff; padding:8px;")
            self.btn_xl.setStyleSheet("background-color:#3a2a0d; border:1px solid #ffaa00; color:#ffdd99;")
            self.btn_tem_bed.setStyleSheet("background-color:#2a183b; border:1px solid #a855f7; color:#e9d5ff; padding:7px;")
            self.btn_bulut.setStyleSheet("background-color:#0b2c3d; border:1px solid #00d2ff; color:#00d2ff; padding:6px 10px;")
            self.btn_tema.setText("☀ Aydınlık Mod")
            self.btn_tema.setStyleSheet("background-color:#1a2938; border:1px solid #ffaa00; color:#ffaa00; padding:6px 10px;")
            self.lbl_uyari.setStyleSheet("color:#7f9bb3; font-size:11px; padding:4px 8px; background-color:#090d12; border:1px solid #1c3144;")
        else:
            self.setStyleSheet("""
                QMainWindow, QWidget, QDialog {
                    background-color: #eef2f6; color: #1e293b;
                    font-family: 'Bahnschrift', 'Segoe UI Semibold', 'Segoe UI', sans-serif; font-size: 14px;
                }
                QGroupBox {
                    background-color: #ffffff; border: 1px solid #cbd5e1; border-top: 2px solid #0f4c81;
                    border-radius: 4px; margin-top: 16px; padding-top: 14px; font-weight: bold;
                }
                QGroupBox::title {
                    subcontrol-origin: margin; subcontrol-position: top left; left: 12px;
                    padding: 2px 8px; background-color: #ffffff; border: 1px solid #0f4c81;
                    border-radius: 2px; color: #0f4c81; font-size: 13px; letter-spacing: 0.8px;
                }
                QTabWidget::pane { border: 1px solid #cbd5e1; background-color: #ffffff; }
                QTabBar::tab {
                    background-color: #e2e8f0; color: #475569; padding: 7px 14px;
                    border: 1px solid #cbd5e1; font-weight: bold;
                }
                QTabBar::tab:selected { background-color: #0f4c81; color: #ffffff; }
                QLineEdit, QComboBox, QDateEdit {
                    background-color: #f8fafc; border: 1px solid #94a3b8; border-radius: 3px;
                    padding: 6px 8px; color: #0f172a;
                    font-family: 'Consolas', 'Segoe UI', monospace; font-size: 14px; font-weight: bold;
                }
                QLineEdit:focus, QComboBox:focus, QDateEdit:focus { border: 1px solid #0f4c81; background-color: #ffffff; }
                QComboBox QAbstractItemView {
                    background-color: #ffffff; color: #0f172a;
                    selection-background-color: #0f4c81; selection-color: #ffffff;
                }
                QPushButton {
                    background-color: #e2e8f0; border: 1px solid #94a3b8; border-radius: 3px;
                    color: #0f172a; padding: 7px 10px; font-size: 13px; font-weight: bold; letter-spacing: 0.3px;
                }
                QPushButton:hover { background-color: #0f4c81; border: 1px solid #0f4c81; color: #ffffff; }
                QPushButton:pressed { background-color: #0a365c; color: #ffffff; }
                QPushButton:disabled { background-color: #f1f5f9; color: #94a3b8; border: 1px solid #cbd5e1; }
                QTableWidget {
                    background-color: #ffffff; alternate-background-color: #f8fafc;
                    gridline-color: #e2e8f0; border: 1px solid #cbd5e1; color: #0f172a;
                    font-family: 'Consolas', 'Segoe UI', monospace; font-size: 14px;
                }
                QTableWidget::item { padding: 4px 8px; }
                QTableWidget::item:selected { background-color: #dbeafe; color: #0f4c81; }
                QHeaderView::section {
                    background-color: #f1f5f9; color: #0f4c81; border: 1px solid #cbd5e1;
                    border-bottom: 2px solid #0f4c81; padding: 7px 8px; font-weight: bold; font-size: 13px;
                }
                QTableCornerButton::section { background-color: #f1f5f9; border: 1px solid #cbd5e1; }
                QListWidget {
                    background-color: #ffffff; border: 1px solid #cbd5e1; color: #1e293b;
                    font-family: 'Consolas', monospace; font-size: 13px; padding: 4px;
                }
                QListWidget::item { padding: 5px; border-bottom: 1px solid #e2e8f0; }
                QListWidget::item:selected { background-color: #dbeafe; color: #0f4c81; }
                QMenu { background-color: #ffffff; border: 1px solid #0f4c81; color: #0f172a; font-weight: bold; }
                QMenu::item { padding: 6px 20px; }
                QMenu::item:selected { background-color: #0f4c81; color: #ffffff; }
                QStatusBar {
                    background-color: #e2e8f0; color: #0f4c81; border-top: 1px solid #cbd5e1;
                    font-weight: bold; font-size: 13px;
                }
            """)
            ozet_renk = "#0f4c81"
            vurgu_renk = "#0f4c81"
            self.btn_kaydet.setStyleSheet("background-color:#0f4c81; border:1px solid #0a365c; color:#ffffff; padding:8px;")
            self.btn_xl.setStyleSheet("background-color:#fef3c7; border:1px solid #d97706; color:#92400e;")
            self.btn_tem_bed.setStyleSheet("background-color:#f3e8ff; border:1px solid #7c3aed; color:#5b21b6; padding:7px;")
            self.btn_bulut.setStyleSheet("background-color:#e0f2fe; border:1px solid #0284c7; color:#0369a1; padding:6px 10px;")
            self.btn_tema.setText("☾ Karanlık Mod")
            self.btn_tema.setStyleSheet("background-color:#1e293b; border:1px solid #0f172a; color:#f8fafc; padding:6px 10px;")
            self.lbl_uyari.setStyleSheet("color:#475569; font-size:11px; padding:4px 8px; background-color:#f8fafc; border:1px solid #cbd5e1;")

        for lbl in (self.lbl_kasa, self.lbl_mal, self.lbl_deg, self.lbl_bal, self.lbl_bsat):
            lbl.setStyleSheet(f"font-weight:bold; font-size:15px; color:{ozet_renk}; font-family:'Consolas', monospace;")
        self.lbl_oto.setStyleSheet(f"color:{vurgu_renk}; font-weight:bold; margin-left:8px;")
        self.lbl_rap.setStyleSheet(f"font-weight:bold; font-size:14px; color:{vurgu_renk}; font-family:'Consolas', monospace;")
        self.pasta_grafik.set_tema(mod)

    def ui(self):
        w = QWidget()
        self.setCentralWidget(w)
        ana = QVBoxLayout(w)

        g1 = QGroupBox("DODNI // PORTFÖY YÖNETİMİ — GENEL ÖZET")
        l1 = QGridLayout(g1)
        self.lbl_kasa, self.lbl_mal, self.lbl_deg = QLabel("0,00 TL"), QLabel("0,00 TL"), QLabel("-")
        self.lbl_kz, self.lbl_bal, self.lbl_bsat = QLabel("-"), QLabel("0,00 TL"), QLabel("0,00 TL")

        arac_box = QHBoxLayout()
        self.btn_bulut = QPushButton("☁ Bulut Giriş")
        self.btn_bulut.setCursor(Qt.PointingHandCursor)
        self.btn_bulut.clicked.connect(self.bulut_pencere_ac)

        b_yedek = QPushButton("💾 Yedekle")
        b_yedek.setToolTip("PC (.zip) veya Mobil (.json) yedeği oluşturur")
        b_yedek.clicked.connect(self.yedekle_dosya)
        b_geri = QPushButton("📂 Geri Yükle")
        b_geri.setToolTip("PC (.zip) veya Mobil (.json) yedeğini geri yükler")
        b_geri.clicked.connect(self.geri_yukle_dosya)
        self.btn_tema = QPushButton("☀ Aydınlık Mod")
        self.btn_tema.setCursor(Qt.PointingHandCursor)
        self.btn_tema.clicked.connect(self.tema_degistir)

        arac_box.addWidget(self.btn_bulut)
        arac_box.addWidget(b_yedek)
        arac_box.addWidget(b_geri)
        arac_box.addWidget(self.btn_tema)

        l1.addWidget(QLabel("Kasa Nakit:"),0,0); l1.addWidget(self.lbl_kasa,0,1)
        l1.addWidget(QLabel("Portföy Maliyet:"),0,2); l1.addWidget(self.lbl_mal,0,3)
        l1.addWidget(QLabel("Anlık Değer:"),0,4); l1.addWidget(self.lbl_deg,0,5)
        l1.addWidget(QLabel("Anlık Kar/Zarar:"),1,0); l1.addWidget(self.lbl_kz,1,1)
        l1.addWidget(QLabel("Bugün Alım:"),1,2); l1.addWidget(self.lbl_bal,1,3)
        l1.addWidget(QLabel("Bugün Satım:"),1,4); l1.addWidget(self.lbl_bsat,1,5)
        l1.addLayout(arac_box, 0, 6, 2, 1, Qt.AlignRight | Qt.AlignVCenter)
        ana.addWidget(g1)

        orta = QHBoxLayout()
        g2 = QGroupBox("İŞLEM GİRİŞİ")
        l2 = QGridLayout(g2)
        self.cmb = QComboBox()
        self.t_al = ParaLineEdit(ondalik=True)
        self.t_sat = ParaLineEdit(ondalik=True)
        self.t_ad = ParaLineEdit(ondalik=False)
        self.t_oran = ParaLineEdit(ondalik=True)
        self.t_kom = ParaLineEdit(ondalik=True)

        self.t_oran.setText(self.motor.komisyon_orani_oku())

        self.t_al.setPlaceholderText("Alış Fiyatı veya 0")
        self.t_sat.setPlaceholderText("Satış Fiyatı veya 0")
        self.t_ad.setPlaceholderText("Lot Adedi")
        self.t_oran.setPlaceholderText("Örn: 5 (Onbinde 5)")
        self.t_oran.setToolTip("Aracı kurum komisyon oranınızı ONBİNDE cinsinden girin (Örn: Binde 1 için 10, Onbinde 5 için 5)")
        self.t_kom.setPlaceholderText("Otomatik Hesaplanır")

        self.t_al.textChanged.connect(self.komisyon_otomatik_hesapla)
        self.t_sat.textChanged.connect(self.komisyon_otomatik_hesapla)
        self.t_ad.textChanged.connect(self.komisyon_otomatik_hesapla)
        self.t_oran.textChanged.connect(self.komisyon_otomatik_hesapla)
        self.t_oran.editingFinished.connect(self.komisyon_orani_kaydet)

        self.dt_isl = QDateEdit(QDate.currentDate())
        self.dt_isl.setCalendarPopup(True)
        self.dt_isl.setDisplayFormat("dd-MM-yyyy")

        self.btn_kaydet = QPushButton("İŞLEMİ ONAYLA VE KAYDET")
        self.btn_kaydet.clicked.connect(self.islem_ekle)

        alanlar = [
            ("Hisse:", self.cmb),
            ("Alış:", self.t_al),
            ("Satış:", self.t_sat),
            ("Adet:", self.t_ad),
            ("Kom. Oranı (‱):", self.t_oran),
            ("Komisyon (TL):", self.t_kom),
            ("Tarih:", self.dt_isl)
        ]
        for i, (ad, wg) in enumerate(alanlar):
            l2.addWidget(QLabel(ad), i, 0)
            l2.addWidget(wg, i, 1)
        l2.addWidget(self.btn_kaydet, len(alanlar), 0, 1, 2)
        orta.addWidget(g2, 1)

        g3 = QGroupBox("MEVCUT PORTFÖY (Çift Tık: Hızlı İşlem  |  Sağ Tık: Hedef/Stop-Loss Alarmı)")
        l3 = QVBoxLayout(g3)
        hb = QHBoxLayout()

        self.btn_fiyat = QPushButton("Güncel Fiyatları Çek")
        self.btn_fiyat.clicked.connect(lambda: self.fiyat_cek(sessiz=False))

        self.lbl_oto = QLabel("Oto Güncelleme:")
        self.cmb_oto = QComboBox()
        self.cmb_oto.addItems(["Kapalı", "5 Dakika", "15 Dakika", "30 Dakika"])
        self.cmb_oto.setToolTip("Yalnızca hafta içi 09:55 – 18:15 seans saatlerinde otomatik sorgu atar.")
        self.cmb_oto.currentIndexChanged.connect(self.oto_ayar_degisti)

        self.btn_xl = QPushButton("Grafikli Excel Raporu")
        self.btn_xl.clicked.connect(self.excel_aktar)

        hb.addWidget(self.btn_fiyat, 2)
        hb.addWidget(self.lbl_oto)
        hb.addWidget(self.cmb_oto, 1)
        hb.addWidget(self.btn_xl, 2)
        l3.addLayout(hb)

        portfoy_icerik = QHBoxLayout()
        self.tablo = QTableWidget(0, 7)
        self.tablo.setAlternatingRowColors(True)
        self.tablo.verticalHeader().setVisible(False)
        self.tablo.setWordWrap(False)
        self.tablo.setHorizontalHeaderLabels(("Hisse", "Adet", "Ort. Maliyet", "Güncel Fiyat", "Güncel Değer", "Anlık K/Z", "Getiri (%)"))

        header = self.tablo.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        self.tablo.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tablo.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tablo.cellDoubleClicked.connect(self.tablo_cift_tik)
        self.tablo.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tablo.customContextMenuRequested.connect(self.tablo_sag_tik_menu)

        self.pasta_grafik = DodniPastaGrafik()

        portfoy_icerik.addWidget(self.tablo, 7)
        portfoy_icerik.addWidget(self.pasta_grafik, 4)
        l3.addLayout(portfoy_icerik)
        orta.addWidget(g3, 4)

        sag = QVBoxLayout()
        g4 = QGroupBox("KASA YÖNETİMİ"); l4 = QGridLayout(g4)
        self.t_kasa = ParaLineEdit(ondalik=True)
        self.t_kasa.setPlaceholderText("Örn: 1.000.000,00")
        b_ke = QPushButton("Nakit Ekle (+)"); b_ke.clicked.connect(lambda: self.kasa_isl("KE"))
        b_kc = QPushButton("Nakit Çek (-)"); b_kc.clicked.connect(lambda: self.kasa_isl("KC"))
        l4.addWidget(self.t_kasa,0,0,1,2); l4.addWidget(b_ke,1,0); l4.addWidget(b_kc,1,1)
        sag.addWidget(g4)

        g5 = QGroupBox("HİSSE & KURUMSAL İŞLEM"); l5 = QGridLayout(g5)
        self.t_his = QLineEdit(); self.t_his.setPlaceholderText("Örn: ASELS")
        b_he = QPushButton("Listeye Ekle"); b_he.clicked.connect(self.hisse_ekle)
        b_hs = QPushButton("Listeden Sil"); b_hs.clicked.connect(self.hisse_sil)
        self.btn_tem_bed = QPushButton("Temettü / Bedelsiz Ekle")
        self.btn_tem_bed.clicked.connect(self.temettu_bedelsiz_ac)
        l5.addWidget(self.t_his,0,0,1,2); l5.addWidget(b_he,1,0); l5.addWidget(b_hs,1,1)
        l5.addWidget(self.btn_tem_bed,2,0,1,2)
        sag.addWidget(g5); orta.addLayout(sag, 1); ana.addLayout(orta)

        alt = QHBoxLayout()
        g6 = QGroupBox("VERİ ANALİZ & RAPORLAMA"); l6 = QGridLayout(g6)
        self.dt1 = QDateEdit(QDate.currentDate().addMonths(-1)); self.dt1.setCalendarPopup(True); self.dt1.setDisplayFormat("dd-MM-yyyy")
        self.dt2 = QDateEdit(QDate.currentDate()); self.dt2.setCalendarPopup(True); self.dt2.setDisplayFormat("dd-MM-yyyy")
        b_r1 = QPushButton("Toplam Komisyon"); b_r1.clicked.connect(lambda: self.rapor_goster("kom"))
        b_r2 = QPushButton("Realize Kar/Zarar"); b_r2.clicked.connect(lambda: self.rapor_goster("kz"))
        b_r3 = QPushButton("Kasadan Çekilen"); b_r3.clicked.connect(lambda: self.rapor_goster("cek"))
        self.lbl_rap = QLabel("Sonuç: -")
        l6.addWidget(QLabel("Başlangıç:"),0,0); l6.addWidget(self.dt1,0,1)
        l6.addWidget(QLabel("Bitiş:"),1,0); l6.addWidget(self.dt2,1,1)
        l6.addWidget(b_r1,2,0,1,2); l6.addWidget(b_r2,3,0,1,2); l6.addWidget(b_r3,4,0,1,2); l6.addWidget(self.lbl_rap,5,0,1,2)
        alt.addWidget(g6, 1)

        g7 = QGroupBox("İŞLEM & KASA GEÇMİŞİ (Hatalı kaydı silmek için üzerine SAĞ TIKLAYIN)")
        l7 = QVBoxLayout(g7)
        self.liste = QListWidget()
        self.liste.setContextMenuPolicy(Qt.CustomContextMenu)
        self.liste.customContextMenuRequested.connect(self.gecmis_sag_tik_menu)
        l7.addWidget(self.liste)
        alt.addWidget(g7, 3); ana.addLayout(alt)

        self.lbl_uyari = QLabel(YASAL_UYARI)
        self.lbl_uyari.setWordWrap(True)
        ana.addWidget(self.lbl_uyari)

    def msg(self, m):
        self.statusBar().showMessage(f" [DODNI // PORTFÖY YÖNETİMİ]: {m}")
        self.timer.start(6000)

    def yedekle_dosya(self):
        tarih_etiket = datetime.now().strftime('%Y%m%d_%H%M')
        yol, secilen_filtre = QFileDialog.getSaveFileName(
            self, "Yedek Dosyasını Kaydet",
            f"DODNI_Portfoy_Yedek_{tarih_etiket}.zip",
            "PC Yedeği (*.zip);;Mobil JSON Yedeği (*.json)"
        )
        if not yol:
            return
        try:
            if yol.lower().endswith(".json") or "JSON" in secilen_filtre:
                if not yol.lower().endswith(".json"):
                    yol += ".json"
                veri = self.motor.mobil_json_olustur(self.alarmlar, self.fiyatlar, self.tema)
                self.motor._atomik_yaz(yol, json.dumps(veri, ensure_ascii=False, indent=2))
                self.msg("Mobil uyumlu .json yedeği kaydedildi.")
            else:
                if not yol.lower().endswith(".zip"):
                    yol += ".zip"
                with zipfile.ZipFile(yol, "w", zipfile.ZIP_DEFLATED) as zf:
                    for dosya in os.listdir(self.motor.d_dir):
                        if dosya.endswith(".txt"):
                            zf.write(os.path.join(self.motor.d_dir, dosya), arcname=dosya)
                self.msg("PC yedeği (.zip) başarıyla kaydedildi.")
        except Exception as e:
            QMessageBox.warning(self, "Yedekleme Hatası", f"Yedek alınırken hata oluştu:\n{str(e)}")

    def geri_yukle_dosya(self):
        yol, _ = QFileDialog.getOpenFileName(
            self, "Yedek Dosyası Seç (PC .zip veya Mobil .json)", "",
            "Yedek Dosyaları (*.zip *.json);;ZIP Arşivi (*.zip);;Mobil JSON (*.json)"
        )
        if not yol:
            return
        onay = QMessageBox.question(
            self, "Yedekten Geri Yükleme",
            "Mevcut tüm işlem, kasa ve alarm verileriniz seçtiğiniz yedekle değiştirilecektir.\n\nDevam etmek istiyor musunuz?",
            QMessageBox.Yes | QMessageBox.No
        )
        if onay != QMessageBox.Yes:
            return
        try:
            if yol.lower().endswith(".json"):
                with open(yol, encoding="utf-8") as f:
                    veri = json.load(f)
                alarmlar, kom_oran, tema = self.motor.mobil_json_yukle(veri)
                self.alarmlar = alarmlar
                self.t_oran.setText(kom_oran)
                if tema in ("dark", "light"):
                    self.tema = tema
                    self.tema_uygula(tema)
                if isinstance(veri.get("fiyatlar"), dict):
                    self.fiyatlar.update(veri["fiyatlar"])
                self.yukle()
                self.bulut_gonder_baslat(sessiz=True)
                self.msg("Mobil .json yedeği doğrulandı ve başarıyla içe aktarıldı.")
            else:
                with zipfile.ZipFile(yol, "r") as zf:
                    for uye in zf.namelist():
                        if uye.endswith(".txt") and "/" not in uye and "\\" not in uye:
                            zf.extract(uye, self.motor.d_dir)
                self.motor._ref_id_goc_kontrol()
                self.alarmlar = self.motor.alarmlari_oku()
                self.t_oran.setText(self.motor.komisyon_orani_oku())
                self.tema = self.motor.tema_oku()
                self.tema_uygula(self.tema)
                self.yukle()
                self.bulut_gonder_baslat(sessiz=True)
                self.msg("ZIP yedeği başarıyla geri yüklendi.")
        except Exception as e:
            QMessageBox.warning(self, "Geri Yükleme Hatası", f"Yedek doğrulanamadı veya açılamadı (mevcut verileriniz korundu):\n{str(e)}")

    def temettu_bedelsiz_ac(self):
        hisseler = self.motor.hisseleri_oku()
        if not hisseler:
            return self.msg("Önce takip listenize en az bir hisse eklemelisiniz.")

        dlg = TemettuBedelsizDialog(hisseler, self)
        if dlg.exec_() == QDialog.Accepted and dlg.sonuc:
            tip, h, deger, tar = dlg.sonuc
            if tip == "TEMETTU":
                self.motor.kasa_ekle("TEMETTU", deger, tar, detay=h)
                self.yukle()
                self.bulut_gonder_baslat(sessiz=True)
                self.msg(f"{h} için {tr_para(deger)} TL nakit temettü kasaya eklendi.")
            elif tip == "BEDELSIZ":
                self.motor.islem_ekle("B", h, 0.0, deger, 0.0, tar)
                self.yukle()
                self.bulut_gonder_baslat(sessiz=True)
                self.msg(f"{h} için +{tr_sayi(deger)} bedelsiz lot portföye eklendi.")

    def tablo_sag_tik_menu(self, pos):
        item = self.tablo.itemAt(pos)
        if not item:
            return
        hisse_item = self.tablo.item(item.row(), 0)
        if not hisse_item:
            return
        hisse = hisse_item.data(Qt.UserRole) or hisse_item.text()

        menu = QMenu(self)
        act_alarm = menu.addAction(f"🔔 {hisse} için Hedef / Stop-Loss Alarmı Kur")
        act_sil = menu.addAction(f"❌ {hisse} Alarmını Kaldır") if hisse in self.alarmlar else None

        secim = menu.exec_(self.tablo.viewport().mapToGlobal(pos))
        if secim == act_alarm:
            mev = self.alarmlar.get(hisse, {"hedef": 0.0, "stop": 0.0})
            dlg = AlarmDialog(hisse, mev["hedef"], mev["stop"], self.fiyatlar.get(hisse), self)
            if dlg.exec_() == QDialog.Accepted and dlg.sonuc is not None:
                hedef, stop = dlg.sonuc
                self.tetiklenen_alarmlar = {x for x in self.tetiklenen_alarmlar if x[0] != hisse}
                if hedef <= 0 and stop <= 0:
                    self.alarmlar.pop(hisse, None)
                    self.msg(f"{hisse} alarmı kaldırıldı.")
                else:
                    self.alarmlar[hisse] = {"hedef": hedef, "stop": stop}
                    self.msg(f"{hisse} alarmı kaydedildi (Hedef: {tr_para(hedef)} / Stop: {tr_para(stop)}).")
                self.motor.alarmlari_kaydet(self.alarmlar)
                self.yukle()
                self.bulut_gonder_baslat(sessiz=True)
                self.alarmlari_kontrol_et()
        elif act_sil and secim == act_sil:
            self.alarmlar.pop(hisse, None)
            self.tetiklenen_alarmlar = {x for x in self.tetiklenen_alarmlar if x[0] != hisse}
            self.motor.alarmlari_kaydet(self.alarmlar)
            self.yukle()
            self.bulut_gonder_baslat(sessiz=True)
            self.msg(f"{hisse} alarmı kaldırıldı.")

    def komisyon_orani_kaydet(self):
        self.motor.komisyon_orani_kaydet(self.t_oran.text())

    def komisyon_otomatik_hesapla(self):
        al = self.num(self.t_al.text()) or 0.0
        sat = self.num(self.t_sat.text()) or 0.0
        ad = self.num(self.t_ad.text(), int) or 0
        oran = self.num(self.t_oran.text()) or 0.0

        fiyat = al if al > 0 else sat
        if fiyat > 0 and ad > 0 and oran >= 0:
            kom_tutari = round((fiyat * ad) * (oran / 10000.0), 2)
            self.t_kom.setText(tr_para(kom_tutari))
        elif ad == 0 or (al == 0 and sat == 0):
            self.t_kom.clear()

    def tablo_cift_tik(self, row, col):
        hisse_item = self.tablo.item(row, 0)
        if not hisse_item:
            return
        hisse = hisse_item.data(Qt.UserRole) or hisse_item.text()
        bilgi = self._cache_portfoy.get(hisse)
        if not bilgi:
            return

        self.cmb.setCurrentText(hisse)
        self.t_ad.setText(tr_sayi(bilgi["adet"]))
        self.t_al.setText("0")

        gf = self.fiyatlar.get(hisse)
        if gf is not None:
            self.t_sat.setText(tr_para(gf))
        else:
            self.t_sat.clear()
        self.komisyon_otomatik_hesapla()
        self.t_sat.setFocus()
        self.msg(f"{hisse} ({tr_sayi(bilgi['adet'])} Lot) ve komisyonu sol panele aktarıldı.")

    def oto_ayar_degisti(self, idx):
        self.oto_timer.stop()
        dakikalar = {1: 5, 2: 15, 3: 30}
        if idx in dakikalar:
            ms = dakikalar[idx] * 60 * 1000
            self.oto_timer.start(ms)
            if seans_acik_mi():
                self.msg(f"Otomatik fiyat güncelleme aktif ({dakikalar[idx]} dakikada bir, seans saatlerinde).")
            else:
                self.msg(f"Otomatik güncelleme aktif ({dakikalar[idx]} dk). Seans kapalı olduğu için açılışta (09:55) devreye girecek.")
        else:
            self.msg("Otomatik fiyat güncelleme kapatıldı.")

    def gecmis_sag_tik_menu(self, pos):
        item = self.liste.itemAt(pos)
        if not item:
            return
        veri = item.data(Qt.UserRole)
        if not veri:
            return

        menu = QMenu(self)
        sil_aksiyon = menu.addAction("❌ Seçili Kaydı Sil (İptal Et)")
        secim = menu.exec_(self.liste.mapToGlobal(pos))
        if secim == sil_aksiyon:
            self.gecmis_islem_sil(veri)

    def gecmis_islem_sil(self, veri):
        kaynak, ref_id, ham_satir = veri
        onay = QMessageBox.question(
            self, "Kayıt Silme Onayı",
            f"Aşağıdaki kayıt sistemden silinecek ve kasa/portföy bakiyesi güncellenecektir:\n\n{ham_satir}\n\nOnaylıyor musunuz?",
            QMessageBox.Yes | QMessageBox.No
        )
        if onay != QMessageBox.Yes:
            return

        if self.motor.kayit_sil(kaynak, ref_id):
            self.yukle()
            self.bulut_gonder_baslat(sessiz=True)
            self.msg("Kayıt (REF_ID) başarıyla silindi ve bakiyeler yeniden hesaplandı.")
        else:
            self.msg("Silinecek kayıt bulunamadı; liste yenilendi.")
            self.yukle()

    def num(self, s, tp=float):
        try:
            temiz = s.strip().replace(".", "").replace(",", ".")
            if not temiz:
                return None
            v = tp(float(temiz)) if tp == int else tp(temiz)
            return v if v >= 0 else None
        except Exception:
            return None

    def fiyat_cek(self, sessiz=False):
        if self.th is not None and self.th.isRunning():
            if not sessiz:
                self.msg("Fiyat güncellemesi zaten devam ediyor, lütfen bekleyin.")
            return

        aktif = [k for k, v in self._cache_portfoy.items() if v["adet"] > 0]
        if not aktif:
            if not sessiz:
                self.msg("Portföyünüzde aktif hisse bulunmuyor.")
            return

        if sessiz and not seans_acik_mi():
            self.msg("Otomatik güncelleme: Seans kapalı olduğu için bekleniyor (Hafta içi 09:55–18:15).")
            return

        gecen = time.time() - self.son_fiyat_zamani
        eksik_var = any(h not in self.fiyatlar for h in aktif)
        if gecen < self.fiyat_cooldown_sn and not eksik_var:
            kalan = int(self.fiyat_cooldown_sn - gecen)
            if not sessiz:
                self.msg(f"Fiyatlar zaten güncel. Hız sınırı koruması için {kalan} sn bekleyin.")
            return

        self.btn_fiyat.setEnabled(False)
        self.btn_fiyat.setText("Veriler Çekiliyor...")
        self.th = FiyatThread(aktif)
        self.th.hazir.connect(self._fiyatlar_geldi)
        self.th.hata.connect(lambda e: self._fiyat_hata(e, sessiz))
        self.th.finished.connect(self._thread_temizle)
        self.th.start()

    def _thread_temizle(self):
        if self.th is not None:
            t = self.th
            self.th = None
            t.wait(1000)
            if t.isRunning():
                self._eski_threadler.append(t)
            else:
                t.deleteLater()
        self._eski_threadler = [t for t in self._eski_threadler if t.isRunning()]

    def _fiyat_hata(self, e, sessiz):
        self.btn_fiyat.setEnabled(True)
        self.btn_fiyat.setText("Güncel Fiyatları Çek")
        if sessiz:
            self.msg(e)
        else:
            QMessageBox.warning(self, "Bağlantı Uyarısı", e)

    def _fiyatlar_geldi(self, d):
        self.fiyatlar.update(d)
        self.son_fiyat_zamani = time.time()
        self.btn_fiyat.setEnabled(True)
        self.btn_fiyat.setText("Güncel Fiyatları Çek")
        self.yukle()
        self.bulut_gonder_baslat(sessiz=True)
        self.msg(f"Fiyatlar güncellendi ({datetime.now().strftime('%H:%M:%S')}).")
        self.alarmlari_kontrol_et()

    def hisse_ekle(self):
        k = self.t_his.text().strip().upper()
        if not k:
            return self.msg("Hisse kodu girin.")
        if not self.motor.hisse_ekle(k):
            return self.msg("Bu hisse zaten listede var.")
        self.t_his.clear()
        self.yukle()
        self.bulut_gonder_baslat(sessiz=True)
        self.msg(f"{k} takip listesine eklendi.")

    def hisse_sil(self):
        k = self.t_his.text().strip().upper() or self.cmb.currentText().strip().upper()
        if not k:
            return self.msg("Silinecek hisse seçili değil.")
        if self._cache_portfoy.get(k, {}).get("adet", 0) > 0:
            return self.msg("Portföyde adedi bulunan hisse silinemez.")

        onay = QMessageBox.question(
            self, "Hisse Silme Onayı",
            f"'{k}' hissesini takip listesinden silmek istediğinize emin misiniz?",
            QMessageBox.Yes | QMessageBox.No
        )
        if onay != QMessageBox.Yes:
            return

        self.motor.hisse_sil(k)
        self.t_his.clear()
        self.yukle()
        self.bulut_gonder_baslat(sessiz=True)
        self.msg(f"{k} listeden çıkarıldı.")

    def kasa_isl(self, tip):
        t = self.num(self.t_kasa.text())
        if not t or t <= 0:
            return self.msg("Geçerli bir tutar girin.")
        if tip == "KC" and t > self._cache_bakiye:
            return self.msg("Yetersiz kasa bakiyesi.")
        self.motor.kasa_ekle(tip, t, QDate.currentDate().toString("dd-MM-yyyy"))
        self.t_kasa.clear()
        self.yukle()
        self.bulut_gonder_baslat(sessiz=True)
        self.msg("Kasa bakiyesi güncellendi.")

    def islem_ekle(self):
        h = self.cmb.currentText().strip().upper()
        al = self.num(self.t_al.text()) if self.t_al.text().strip() else 0.0
        sat = self.num(self.t_sat.text()) if self.t_sat.text().strip() else 0.0
        ad = self.num(self.t_ad.text(), int)
        kom = self.num(self.t_kom.text()) if self.t_kom.text().strip() else 0.0

        if not h or None in (al, sat, ad, kom) or ad <= 0 or (al == 0 and sat == 0) or (al > 0 and sat > 0):
            return self.msg("Alanları kontrol edin (Alış veya Satıştan yalnızca biri dolu olmalı).")

        self.komisyon_orani_kaydet()
        tar = self.dt_isl.date().toString("dd-MM-yyyy")
        if al > 0:
            if (al * ad) + kom > self._cache_bakiye:
                return self.msg("Kasada yeterli bakiye yok.")
            self.motor.islem_ekle("A", h, al, ad, kom, tar)
        else:
            if ad > self._cache_portfoy.get(h, {}).get("adet", 0):
                return self.msg("Portföyde yeterli hisse adedi yok.")
            self.motor.islem_ekle("S", h, sat, ad, kom, tar)

        for x in (self.t_al, self.t_sat, self.t_ad, self.t_kom):
            x.clear()
        self.yukle()
        self.bulut_gonder_baslat(sessiz=True)
        self.msg("İşlem başarıyla kaydedildi.")

    def yukle(self):
        self._cache_bakiye, self._cache_portfoy, islemler, kasalar, veri_uyarilari = self.motor.hesapla()
        koyu = (self.tema == "dark")

        c_hisse = QColor("#00d2ff" if koyu else "#0f4c81")
        c_kar = "#2ecc71" if koyu else "#15803d"
        c_zarar = "#ff4d4d" if koyu else "#dc2626"
        c_alim = QColor("#7be382" if koyu else "#15803d")
        c_satim = QColor("#ff9f43" if koyu else "#c2410c")
        c_bedelsiz = QColor("#c084fc" if koyu else "#7c3aed")
        c_kasa_l = QColor("#00d2ff" if koyu else "#0369a1")

        sec = self.cmb.currentText()
        self.cmb.clear()
        hs = self.motor.hisseleri_oku()
        self.cmb.addItems(hs)
        if sec in hs:
            self.cmb.setCurrentText(sec)

        self.lbl_kasa.setText(f"{tr_para(self._cache_bakiye)} TL")
        aktif = {k: v for k, v in self._cache_portfoy.items() if v["adet"] > 0}

        self.tablo.setUpdatesEnabled(False)
        self.tablo.setRowCount(len(aktif))
        tm, td = 0.0, 0.0
        fiyat_var = False
        pasta_verisi = {}

        for i, (h, v) in enumerate(aktif.items()):
            tm += v["mal"]
            gf = self.fiyatlar.get(h)
            if gf is not None:
                fiyat_var = True
            deg = gf * v["adet"] if gf is not None else v["mal"]
            kz = deg - v["mal"] if gf is not None else 0.0
            yuzde = (kz / v["mal"]) * 100.0 if (gf is not None and v["mal"] > 0) else 0.0
            td += deg
            pasta_verisi[h] = deg

            alarm_bilgi = self.alarmlar.get(h)
            gosterim_hisse = f"🔔 {h}" if alarm_bilgi else h
            it_h = QTableWidgetItem(gosterim_hisse)
            it_h.setData(Qt.UserRole, h)
            if alarm_bilgi:
                it_h.setToolTip(f"Hedef: {tr_para(alarm_bilgi['hedef'])} TL | Stop: {tr_para(alarm_bilgi['stop'])} TL")

            it_ad = QTableWidgetItem(tr_sayi(v["adet"]))
            it_ort = QTableWidgetItem(f"{tr_para(v['ort'])} TL")
            it_gf = QTableWidgetItem(f"{tr_para(gf)} TL" if gf is not None else "Bekleniyor")
            it_deg = QTableWidgetItem(f"{tr_para(deg)} TL" if gf is not None else "-")
            it_kz = QTableWidgetItem(f"{tr_para(kz, isaretli=True)} TL" if gf is not None else "-")
            it_yz = QTableWidgetItem(f"%{tr_para(yuzde, isaretli=True)}" if gf is not None else "-")

            it_h.setForeground(c_hisse)
            for it in (it_ad, it_ort, it_gf, it_deg, it_kz, it_yz):
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            if gf is not None:
                renk_kz = QColor(c_kar if kz >= 0 else c_zarar)
                it_kz.setForeground(renk_kz)
                it_yz.setForeground(renk_kz)

            self.tablo.setItem(i, 0, it_h)
            self.tablo.setItem(i, 1, it_ad)
            self.tablo.setItem(i, 2, it_ort)
            self.tablo.setItem(i, 3, it_gf)
            self.tablo.setItem(i, 4, it_deg)
            self.tablo.setItem(i, 5, it_kz)
            self.tablo.setItem(i, 6, it_yz)

        self.tablo.resizeColumnsToContents()
        for col in range(self.tablo.columnCount()):
            genislik = self.tablo.columnWidth(col)
            self.tablo.setColumnWidth(col, max(genislik + 16, 85))
        self.tablo.setUpdatesEnabled(True)

        self.pasta_grafik.guncelle(pasta_verisi)

        self.lbl_mal.setText(f"{tr_para(tm)} TL")
        self.lbl_deg.setText(f"{tr_para(td)} TL" if fiyat_var else "-")

        if fiyat_var:
            toplam_kz = td - tm
            toplam_yz = (toplam_kz / tm) * 100.0 if tm > 0 else 0.0
            self.lbl_kz.setText(f"{tr_para(toplam_kz, isaretli=True)} TL (%{tr_para(toplam_yz, isaretli=True)})")
            self.lbl_kz.setStyleSheet(f"font-weight:bold; font-size:15px; font-family:'Consolas', monospace; color:{c_kar if toplam_kz>=0 else c_zarar};")
        else:
            self.lbl_kz.setText("-")
            self.lbl_kz.setStyleSheet(f"font-weight:bold; font-size:15px; font-family:'Consolas', monospace; color:{'#ffaa00' if koyu else '#0f4c81'};")

        self.liste.setUpdatesEnabled(False)
        self.liste.clear()
        bugun = QDate.currentDate().toString("dd-MM-yyyy")
        ba, bs = 0.0, 0.0
        zaman_tuneli = []

        for x in islemler:
            if x["tip"] == "B":
                metin = f"[{x['tarih']}] BEDELSİZ | {x['hisse']:<6} | +{tr_sayi(x['adet'])} Lot (Sıfır Maliyet)"
                renk = c_bedelsiz
            else:
                metin = f"[{x['tarih']}] {'ALIM ' if x['tip']=='A' else 'SATIM'} | {x['hisse']:<6} | {tr_sayi(x['adet'])} Lot x {tr_para(x['fiyat'])} TL (Kom: {tr_para(x['kom'])} TL)"
                renk = c_alim if x["tip"] == "A" else c_satim
            zaman_tuneli.append((x["tarih_dt"] or datetime.min.date(), x["ref_id"], x["idx"], "ISLEM", metin, renk))
            if x["tarih"] == bugun:
                if x["tip"] == "A": ba += (x["fiyat"] * x["adet"]) + x["kom"]
                elif x["tip"] == "S": bs += (x["fiyat"] * x["adet"]) - x["kom"]

        for k in kasalar:
            if k["tip"] in ("KE", "KC"):
                metin = f"[{k['tarih']}] {'KASA GİRİŞ (+)' if k['tip']=='KE' else 'KASA ÇIKIŞ (-)'} | {tr_para(k['tutar'])} TL"
                zaman_tuneli.append((k["tarih_dt"] or datetime.min.date(), k["ref_id"], k["idx"], "KASA", metin, c_kasa_l))
            elif k["tip"] == "TEMETTU":
                h_ad = k["detay"] or "GENEL"
                metin = f"[{k['tarih']}] TEMETTÜ (+) | {h_ad:<6} | +{tr_para(k['tutar'])} TL"
                zaman_tuneli.append((k["tarih_dt"] or datetime.min.date(), k["ref_id"], k["idx"], "KASA", metin, c_bedelsiz))

        zaman_tuneli.sort(key=lambda r: (r[0], r[1], r[2]), reverse=True)

        for _, ref_id, _, kaynak, metin, renk in zaman_tuneli:
            item = QListWidgetItem(metin)
            item.setData(Qt.UserRole, (kaynak, ref_id, metin))
            item.setForeground(renk)
            self.liste.addItem(item)

        self.liste.setUpdatesEnabled(True)
        self.lbl_bal.setText(f"{tr_para(ba)} TL")
        self.lbl_bsat.setText(f"{tr_para(bs)} TL")

        if veri_uyarilari:
            ozet_uyari = veri_uyarilari[-1]
            if ozet_uyari != self._gosterilen_veri_uyari:
                self._gosterilen_veri_uyari = ozet_uyari
                self.msg(f"Veri Tutarsızlığı Uyarısı: {ozet_uyari}")

    def rapor_goster(self, tur):
        d1 = self.dt1.date().toPyDate()
        d2 = self.dt2.date().toPyDate()
        sonuc = self.motor.rapor_hesapla(tur, d1, d2)
        if tur == "kom":
            self.lbl_rap.setText(f"Toplam Komisyon: {tr_para(sonuc)} TL")
        elif tur == "kz":
            self.lbl_rap.setText(f"Realize K/Z: {tr_para(sonuc, isaretli=True)} TL")
        elif tur == "cek":
            self.lbl_rap.setText(f"Kasadan Çekilen: {tr_para(sonuc)} TL")

    def excel_aktar(self):
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.chart import BarChart, PieChart, Reference

        aktif = {k: v for k, v in self._cache_portfoy.items() if v["adet"] > 0}
        if not aktif:
            return self.msg("Excel raporu için portföyde aktif hisse olmalı.")

        eksikler = [h for h in aktif if self.fiyatlar.get(h) is None]
        if eksikler:
            onay = QMessageBox.question(
                self, "Güncel Fiyat Eksik",
                f"Şu hisselerin güncel fiyatı henüz çekilmemiş: {', '.join(eksikler)}\n\n"
                "Bu hisselerin güncel değer ve kâr/zarar hücreleri boş bırakılarak rapor oluşturulsun mu?",
                QMessageBox.Yes | QMessageBox.No
            )
            if onay != QMessageBox.Yes:
                return

        yol, _ = QFileDialog.getSaveFileName(self, "Excel Kaydet", "DODNI_Portfoy_Rapor.xlsx", "Excel (*.xlsx)")
        if not yol:
            return

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Portfoy_Raporu"

        basliklar = ("Hisse", "Adet", "Ort. Maliyet", "Toplam Maliyet", "Güncel Fiyat", "Güncel Değer", "Kar/Zarar", "Getiri (%)")
        ws.append(basliklar)

        baslik_dolgu = PatternFill(start_color="0D1B2A", end_color="0D1B2A", fill_type="solid")
        baslik_font = Font(name="Segoe UI", size=11, bold=True, color="00D2FF")
        ince_kenar = Border(
            left=Side(style='thin', color='444444'), right=Side(style='thin', color='444444'),
            top=Side(style='thin', color='444444'), bottom=Side(style='thin', color='444444')
        )

        for col_num in range(1, len(basliklar) + 1):
            hucre = ws.cell(row=1, column=col_num)
            hucre.fill = baslik_dolgu
            hucre.font = baslik_font
            hucre.alignment = Alignment(horizontal="center", vertical="center")

        satir_no = 2
        for h, v in aktif.items():
            gf = self.fiyatlar.get(h)
            if gf is not None:
                deg = round(gf * v["adet"], 2)
                kz = round(deg - v["mal"], 2)
                yz = round((kz / v["mal"]), 4) if v["mal"] > 0 else 0.0
                ws.append((h, v["adet"], round(v["ort"], 2), round(v["mal"], 2), round(gf, 2), deg, kz, yz))
                renk_kod = "1E8449" if kz >= 0 else "C0392B"
                ws.cell(row=satir_no, column=7).font = Font(bold=True, color=renk_kod)
                ws.cell(row=satir_no, column=8).font = Font(bold=True, color=renk_kod)
            else:
                ws.append((h, v["adet"], round(v["ort"], 2), round(v["mal"], 2), None, None, None, None))

            ws.cell(row=satir_no, column=2).number_format = '#,##0'
            for c in (3, 4, 5, 6, 7):
                ws.cell(row=satir_no, column=c).number_format = '#,##0.00 "TL"'
            ws.cell(row=satir_no, column=8).number_format = '0.00%'

            for c in range(1, 9):
                ws.cell(row=satir_no, column=c).border = ince_kenar

            satir_no += 1

        son_satir = satir_no - 1
        alt_satir = satir_no + 1

        if eksikler:
            if len(eksikler) < len(aktif):
                grafik_notu = (
                    f"Grafik Notu: Güncel fiyatı çekilmemiş hisseler ({', '.join(eksikler)}) "
                    "tabloda boş bırakılmış olup Güncel Değer ve Pasta Grafiğine dahil edilmemiştir."
                )
            else:
                grafik_notu = (
                    "Grafik Notu: Hisselerin güncel fiyatları çekilmediği için Pasta Grafiği "
                    "Toplam Maliyet değerleri üzerinden oluşturulmuştur."
                )
            ws.merge_cells(start_row=alt_satir, start_column=1, end_row=alt_satir, end_column=8)
            n_cell = ws.cell(row=alt_satir, column=1, value=grafik_notu)
            n_cell.font = Font(name="Segoe UI", size=9, bold=True, color="92400E")
            n_cell.alignment = Alignment(wrap_text=True, vertical="center")
            ws.row_dimensions[alt_satir].height = 28
            alt_satir += 1

        ws.merge_cells(start_row=alt_satir, start_column=1, end_row=alt_satir, end_column=8)
        u_cell = ws.cell(row=alt_satir, column=1, value=YASAL_UYARI)
        u_cell.font = Font(name="Segoe UI", size=9, italic=True, color="555555")
        u_cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.row_dimensions[alt_satir].height = 38

        for col in ws.columns:
            col_letter = col[0].column_letter
            max_len = max(len(str(cell.value or "")) for cell in col[:son_satir])
            ws.column_dimensions[col_letter].width = max(max_len + 5, 14)

        bar = BarChart()
        bar.type = "col"
        bar.style = 10
        bar.title = "Hisse Bazlı Maliyet ve Güncel Değer (TL)"
        bar.y_axis.title = "Tutar (TL)"
        bar.x_axis.title = "Hisseler"

        kategoriler = Reference(ws, min_col=1, min_row=2, max_row=son_satir)
        veriler_mal = Reference(ws, min_col=4, min_row=1, max_row=son_satir)
        veriler_deg = Reference(ws, min_col=6, min_row=1, max_row=son_satir)

        bar.add_data(veriler_mal, titles_from_data=True)
        bar.add_data(veriler_deg, titles_from_data=True)
        bar.set_categories(kategoriler)
        bar.width = 16
        bar.height = 10
        ws.add_chart(bar, "J2")

        pie = PieChart()
        pie.title = "Portföy Değer Dağılımı" if len(eksikler) < len(aktif) else "Portföy Maliyet Dağılımı"
        pie.add_data(veriler_deg if len(eksikler) < len(aktif) else veriler_mal, titles_from_data=True)
        pie.set_categories(kategoriler)
        pie.width = 16
        pie.height = 10
        ws.add_chart(pie, "J23")

        wb.save(yol)
        self.msg("Grafikli Excel raporu oluşturuldu.")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    try:
        win = DodniPortfoyApp()
        win.show()
        sys.exit(app.exec_())
    except Exception:
        QMessageBox.critical(None, "Hata", traceback.format_exc())