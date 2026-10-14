# Bungalow Rezervasyon Sistemi

Flask ve SQLite ile geliştirilmiş bungalov rezervasyon uygulaması. Müşteriler rezervasyon talebi oluşturabilir; yöneticiler talepleri inceleyip onaylayabilir veya reddedebilir.

Bu depo, [CGhost1908/bungalow-reservation-system](https://github.com/CGhost1908/bungalow-reservation-system) projesinin fork'udur. Frontend kökeni ve katkı sahiplerinin hakları korunur; backend ve yönetim panelindeki Berkay Seyman katkıları aşağıda açıklanmıştır.

## Özellikler

- Bungalov seçimi, giriş/çıkış tarihleri ve misafir bilgileriyle rezervasyon talebi.
- Yönetici girişi, rezervasyon listesi ve onay/red işlemleri.
- FullCalendar tabanlı yönetici takvimi.
- E-posta, telefon, tarih aralığı ve misafir sayısı kontrolleri.
- Bungalov başına onaylanmış rezervasyonlarla tarih çakışması kontrolü.
- Gmail SMTP üzerinden yönetici ve müşteri bildirimleri.
- SQLite saklama, eski JSON kayıtları için taşıma yardımcıları ve loglama.

> Yerel geliştirme projesidir. Oturum açma tek başına CSRF koruması sağlamaz; mevcut uygulamada CSRF token doğrulaması bulunmaz.

## Kurulum

Python 3.10 ve Git ile yerel çalışma için:

```bash
git clone https://github.com/symNistaken/bungalow-reservation-system.git
cd bungalow-reservation-system
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Linux/macOS:

```bash
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

`.env` dosyasına yönetici ve oturum ayarlarını ekle; e-posta şablonundaki yer tutucuları kendi bilgilerinle değiştir:

```dotenv
SECRET_KEY=YOUR_RANDOM_SECRET_KEY
ADMIN_USERNAME=YOUR_ADMIN_USERNAME
ADMIN_PASSWORD=YOUR_STRONG_ADMIN_PASSWORD
TIMEZONE=Europe/Istanbul
EMAIL_SENDER=YOUR_GMAIL_ADDRESS
EMAIL_PASSWORD=YOUR_GMAIL_APP_PASSWORD
ADMIN_EMAIL=YOUR_NOTIFICATION_EMAIL
```

Rastgele oturum anahtarı üretmek için:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Gmail için [iki aşamalı doğrulama](https://support.google.com/accounts/answer/185839) ve [uygulama şifresi](https://myaccount.google.com/apppasswords) kullan. Normal hesap şifreni paylaşma. E-posta ayarları eksikse bildirimler çalışmaz; uygulama terminalde uyarı verir. SMTP sunucusu mevcut kodda `smtp.gmail.com:587` olarak sabittir; `.env.example` içindeki isteğe bağlı SMTP ayarları kod tarafından okunmaz.

Windows:

```powershell
.\.venv\Scripts\python.exe app.py
```

Linux/macOS:

```bash
.venv/bin/python app.py
```

[http://localhost:5000](http://localhost:5000) adresini aç. Komutları depo kökünde çalıştır; SQLite dosyası ve loglar çalışma dizininde oluşur.

## Kullanım

**Müşteri:** `/reservation` sayfasında ad, e-posta, telefon, bungalov, misafir sayısı ve tarihleri doldur. Talep `pending` durumunda kaydedilir; yönetici kararı sonrasında bildirim gönderilmeye çalışılır.

**Yönetici:** `/admin/login` üzerinden `.env` içinde belirlediğin bilgilerle giriş yap. `/admin` sayfasında talepleri listele, takvimi incele ve onay/red işlemlerini yap.

Yönetici bilgileri verilmezse kod `admin` / `admin123` varsayılanlarını kullanır. Gerçek kullanım öncesinde bunları ve varsayılan oturum anahtarını mutlaka değiştir.

## Sayfalar ve API

| Yol | Yöntem | Erişim / amaç |
| --- | --- | --- |
| `/`, `/bungalows`, `/gallery` | GET | Genel sayfalar |
| `/reservation` | GET | Rezervasyon formu |
| `/admin/login` | GET, POST | Yönetici girişi |
| `/admin`, `/admin/logout` | GET | Yönetici paneli / çıkış |
| `/api/reservation` | POST | Herkese açık talep oluşturma |
| `/api/reservations` | GET | Yönetici oturumu; tüm kayıtlar |
| `/api/reservations/pending` | GET | Yönetici oturumu; bekleyen kayıtlar |
| `/api/reservations/<id>/approve` | POST | Yönetici oturumu; onay |
| `/api/reservations/<id>/reject` | POST | Yönetici oturumu; red |
| `/api/booked-dates` | GET | Genel doluluk bilgisi; isteğe bağlı `bungalow` query alanı |
| `/api/bungalow-dates/<bungalow>` | GET | Yönetici oturumu; durum ve misafir adları |

Yönetici oturumu gerektiren uç noktalar giriş yapılmamışsa `/admin/login` adresine yönlendirir. `/api/reservation` JSON gövdesinde şu alanları bekler:

```json
{
  "name": "Örnek Misafir",
  "email": "guest@example.com",
  "phone": "05301234567",
  "checkIn": "YYYY-MM-DD",
  "checkOut": "YYYY-MM-DD",
  "guests": 2,
  "bungalow": "Bungalow 1",
  "notes": "İsteğe bağlı not"
}
```

Tarihleri gelecekteki gerçek tarihlerle, bungalov değerini arayüzdeki seçenekle değiştir. Giriş ve çıkış bugünden sonra olmalı; çıkış girişten sonra ve konaklama en fazla 90 gün olmalıdır. Misafir sayısı `1–20` aralığındadır. Doğrulama hataları `400`, onaylı rezervasyon çakışması `409` döndürür.

## Veritabanı ve dosyalar

```text
app.py                 Flask, doğrulama, yönetici oturumu ve bildirimler
database.py            SQLite işlemleri ve JSON taşıma
templates/             Müşteri ve yönetici sayfaları
static/                CSS ve JavaScript
.env.example           E-posta ortam şablonu
requirements.txt       Python paketleri
test_app.py            Doğrulama, veritabanı ve API testleri
test_email.py          Gerçek SMTP bağlantı/bildirim testi
inspect_db.py          Yerel veritabanını inceleme
```

Asıl saklama dosyası **`reservations.db`**; `reservations.json` eski taşıma girdisidir. Veritabanı tabloları başlangıçta oluşturulur. `.env`, veritabanı ve loglar Git dışında tutulur. Rezervasyonlarda müşteri iletişim bilgileri bulunur; paylaşmadan önce veriyi temizle ve yedek al.

`static/images/` ve `static/videos/` Git tarafından yok sayılır; yerel görsel dosyaları klonda bulunmayabilir. Kullanacağın görselleri ilgili yollarına kendin yerleştir. Veritabanı dosyasını veya müşteri kayıtlarını hata raporuna yükleme.

## Kontroller

Paketler kurulduktan sonra, sanal ortamın Python'u ile depo kökünde:

```bash
python -m unittest test_app -v
```

Bu testler doğrulama, SQLite işlemleri ve API davranışlarını kapsar. Test içe aktarması yerel veritabanı/log dosyaları oluşturabilir; canlı veritabanının bulunduğu dizinde çalıştırma. E-posta testini yalnızca kendi hesabın ve alıcılarınla çalıştır:

```bash
python test_email.py
```

E-posta testi SMTP'ye bağlanır ve yapılandırılmış adreslere bildirim gönderebilir; çevrimdışı test değildir.

## Güvenlik ve mevcut sınırlar

- Yönetici listeleri, onay/red uç noktaları ve misafir isimli takvim, yönetici oturumu gerektirir.
- Şifreler Werkzeug ile hash'lenir; rate limiting ve güvenlik başlığı bileşenleri bulunur.
- CSRF token doğrulaması henüz uygulanmaz. Oturum kontrolü bu açığı tek başına çözmez.
- Kod geliştirme sunucusunu `debug=True` ile başlatır; üretim için debug kapatılmalı, uygun WSGI sunucusu ve HTTPS kullanılmalıdır.
- CORS API için geniş tanımlıdır; üretimde izinli origin'lere sınırlandırılmalıdır.
- Tarih kontrolü onaylı kayıtları esas alır; bekleyen talepler aynı tarihlere gelebilir. Onay sırasında çakışma/concurrency güvenliği ayrıca güçlendirilmelidir.

## Sorun giderme

- **E-posta gitmiyor:** `.env`, Gmail uygulama şifresi, alıcı adresi ve terminal loglarını kontrol et.
- **Yönetici girişi başarısız:** `.env` değerlerini değiştirince sunucuyu yeniden başlat.
- **Görsel eksik:** Şablonun beklediği `static/images/` yolunda dosya bulunduğunu kontrol et.
- **Veri görünmüyor:** Komutları aynı depo kökünden çalıştır; `reservations.db` çalışma dizinine bağlıdır.

## Katkılar ve kullanım koşulları

Frontend kökeni [CGhost1908/bungalow](https://github.com/CGhost1908/bungalow) projesidir. Rezervasyon backend'i, SQLite entegrasyonu ve yönetim paneli **Berkay Seyman** tarafından geliştirilmiştir.

© 2026 Berkay Seyman. Berkay Seyman'a ait backend ve yönetim paneli katkılarının tüm hakları saklıdır. GitHub'da görüntülenebilir olmaları genel veya ticari kullanım izni vermez; kullanım için önceden yazılı izin alınmalıdır. Frontend ve diğer katkıların hakları kendi sahiplerine aittir. GitHub hizmet koşulları ve yürürlükteki hukuk kapsamındaki haklar saklıdır.

## İletişim ve ek belgeler

- Berkay Seyman: berkayseyman@gmail.com
- Bilal Berke Ceylan: bilalberkeceylan@gmail.com
- Eren Batı Altunkapak: erenbatialtunkapak@gmail.com

[E-posta kurulumu](EMAIL_SETUP.md), [yönetici kurulumu](ADMIN_SETUP.md) ve [veritabanı inceleme](DATABASE_INSPECTION.md) belgeleri ek geliştirme notlarıdır. Tarihsel notlardaki güvenlik ve üretime hazır olma iddialarını bu README'deki mevcut sınırlarla birlikte değerlendir.
