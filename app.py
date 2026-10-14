# -*- coding: utf-8 -*-
# Backend implementation: Berkay Seyman (2026)
# Copyright (c) 2026 Berkay Seyman. SPDX-License-Identifier: MIT
# MIT applies to Berkay Seyman contributions; see LICENSE and LICENSE-SCOPE.md.

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime, timedelta
import json
import os
import logging
from logging.handlers import RotatingFileHandler
from functools import wraps
import uuid
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
from flask_talisman import Talisman
import pytz

# Import database module
import database as db

app = Flask(__name__)

# Load environment variables from .env file
load_dotenv()

# Enable CORS
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Security Headers with Talisman
Talisman(app, 
    force_https=False,  # Set to True in production
    strict_transport_security=True,
    strict_transport_security_max_age=31536000,
    content_security_policy={
        'default-src': "'self'",
        'script-src': ["'self'", "'unsafe-inline'", "cdnjs.cloudflare.com", "cdn.jsdelivr.net"],
        'style-src': ["'self'", "'unsafe-inline'", "cdnjs.cloudflare.com", "fonts.googleapis.com"],
        'img-src': ["'self'", "data:", "https:"],
        'font-src': ["'self'", "fonts.gstatic.com"],
        'connect-src': "'self'"
    }
)

# Initialize Rate Limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Configure Logging
if not os.path.exists('logs'):
    os.makedirs('logs')

# Setup logger
logger = logging.getLogger('bungalow_app')
logger.setLevel(logging.DEBUG)

# File handler with rotation
file_handler = RotatingFileHandler('logs/app.log', maxBytes=10485760, backupCount=10, encoding='utf-8')  # 10MB per file
file_handler.setLevel(logging.DEBUG)

# Console handler with UTF-8 encoding
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
if hasattr(console_handler, 'stream'):
    import io
    console_handler.stream = io.TextIOWrapper(console_handler.stream.buffer, encoding='utf-8')

# Formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Add handlers
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Secret Key Configuration
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
if app.secret_key == 'dev-secret-key-change-in-production':
    logger.warning("SECRET_KEY .env dosyasında ayarlanmamış! Development ortamında çalışıyor.")

# Timezone Configuration
TIMEZONE_STR = os.environ.get('TIMEZONE', 'Europe/Istanbul')
try:
    APP_TIMEZONE = pytz.timezone(TIMEZONE_STR)
except pytz.exceptions.UnknownTimeZoneError:
    logger.warning(f"Bilinmeyen timezone: {TIMEZONE_STR}. UTC kullanılıyor.")
    APP_TIMEZONE = pytz.UTC

def get_local_datetime():
    """Get current datetime in app timezone"""
    return datetime.now(APP_TIMEZONE)

# Email Configuration
EMAIL_SENDER = os.environ.get('EMAIL_SENDER')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL')
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587

# Validate email configuration
if not EMAIL_SENDER or not EMAIL_PASSWORD or not ADMIN_EMAIL:
    logger.warning("EMAIL KONFİGÜRASYONU EKSIK!")
    logger.warning("Lütfen .env dosyasında EMAIL_SENDER, EMAIL_PASSWORD ve ADMIN_EMAIL ayarlayınız.")
    logger.warning("Örnek: EMAIL_SETUP.md dosyasına bakınız.")

RESERVATIONS_FILE = 'reservations.json'

# Admin credentials with password hashing
# In production, use environment variables for admin credentials
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD_HASH = generate_password_hash(os.environ.get('ADMIN_PASSWORD', 'admin123'))

# Store hashed passwords
ADMIN_CREDENTIALS = {
    ADMIN_USERNAME: ADMIN_PASSWORD_HASH
}

# Initialize database
db.init_db()
logger.info("SQLite veritabanı başlatıldı")

def load_reservations():
    """Load reservations from SQLite database"""
    return db.load_reservations()

def save_reservations(reservations):
    """Save reservations to SQLite database"""
    db.save_reservations(reservations)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def get_booked_dates():
    """Get all booked dates from approved reservations"""
    reservations = load_reservations()
    booked_dates = []
    
    for res in reservations:
        if res.get('status') == 'approved':
            check_in = datetime.strptime(res['checkIn'], '%Y-%m-%d')
            check_out = datetime.strptime(res['checkOut'], '%Y-%m-%d')
            
            current_date = check_in
            while current_date < check_out:
                booked_dates.append(current_date.strftime('%Y-%m-%d'))
                current_date += timedelta(days=1)
    
    return booked_dates

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not email or not isinstance(email, str):
        return False
    return bool(re.match(pattern, email.strip()))

def validate_phone(phone):
    """Validate phone format (Turkish or international)"""
    if not phone or not isinstance(phone, str):
        return False
    # Remove spaces and special characters
    cleaned = re.sub(r'[\s\-\(\)\+]', '', phone)
    # Check if it's a valid phone number (7-15 digits)
    return bool(re.match(r'^[\d]{7,15}$', cleaned))

def validate_name(name):
    """Validate person name"""
    if not name or not isinstance(name, str):
        return False
    # Name should be 2-100 characters, letters, spaces, hyphens, apostrophes
    cleaned = name.strip()
    if len(cleaned) < 2 or len(cleaned) > 100:
        return False
    pattern = r"^[a-zA-ZçğıöşüÇĞİÖŞÜ\s\-']+$"
    return bool(re.match(pattern, cleaned))

def validate_guests(guests):
    """Validate guest count"""
    try:
        guest_count = int(guests)
        return 1 <= guest_count <= 20  # 1-20 guests
    except (ValueError, TypeError):
        return False

def validate_date(date_str):
    """Validate date format and not in the past"""
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        # Check if date is not in the past (using local timezone)
        today = get_local_datetime().date()
        return date_obj.date() >= today
    except ValueError:
        return False

def validate_date_range(check_in_str, check_out_str):
    """Validate date range"""
    try:
        check_in = datetime.strptime(check_in_str, '%Y-%m-%d')
        check_out = datetime.strptime(check_out_str, '%Y-%m-%d')
        # Checkout must be after check-in, max 90 days
        return check_out > check_in and (check_out - check_in).days <= 90
    except ValueError:
        return False

def validate_bungalow(bungalow):
    """Validate bungalow name"""
    if not bungalow or not isinstance(bungalow, str):
        return False
    cleaned = bungalow.strip()
    # Valid bungalow names: 2-50 characters
    return 2 <= len(cleaned) <= 50

def validate_notes(notes):
    """Validate reservation notes"""
    if notes is None:
        return True
    if not isinstance(notes, str):
        return False
    # Max 500 characters
    return len(notes) <= 500

def check_date_conflict(check_in, check_out, bungalow, exclude_id=None):
    """Check if dates conflict with approved reservations for the same bungalow"""
    reservations = load_reservations()
    check_in_date = datetime.strptime(check_in, '%Y-%m-%d')
    check_out_date = datetime.strptime(check_out, '%Y-%m-%d')
    
    for res in reservations:
        # Skip if it's the same reservation being updated
        if exclude_id and res.get('id') == exclude_id:
            continue
        
        # Only check approved reservations for the same bungalow
        if res.get('status') == 'approved' and res.get('bungalow') == bungalow:
            res_check_in = datetime.strptime(res['checkIn'], '%Y-%m-%d')
            res_check_out = datetime.strptime(res['checkOut'], '%Y-%m-%d')
            
            # Check for overlap
            if check_in_date < res_check_out and check_out_date > res_check_in:
                return True
    
    return False

def send_email(to_email, subject, html_body):
    """Send email using Gmail SMTP"""
    try:
        # Validate configuration
        if not EMAIL_SENDER or not EMAIL_PASSWORD:
            logger.error("Email konfigürasyonu eksik: EMAIL_SENDER veya EMAIL_PASSWORD ayarlanmamış")
            return False
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = EMAIL_SENDER
        msg['To'] = to_email
        
        # Attach HTML content
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        # Connect and send
        logger.info(f"Email gönderiliyor: {to_email} -> {subject}")
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"Email başarıyla gönderildi: {to_email}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"Email Gönderme Hatası: Kimlik doğrulaması başarısız - {str(e)}")
        logger.error(f"Kontrol et: EMAIL_SENDER={EMAIL_SENDER}")
        logger.error(f"Gmail'de 2FA açık mı? App Password kullanıyor musun?")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"Email Gönderme Hatası (SMTP): {str(e)}")
        return False
    except Exception as e:
        logger.exception(f"Email Gönderme Hatası: {str(e)}")
        return False

def send_admin_reservation_notification(reservation):
    """Send email to admin when new reservation arrives"""
    check_in = datetime.strptime(reservation['checkIn'], '%Y-%m-%d').strftime('%d.%m.%Y')
    check_out = datetime.strptime(reservation['checkOut'], '%Y-%m-%d').strftime('%d.%m.%Y')
    nights = (datetime.strptime(reservation['checkOut'], '%Y-%m-%d') - 
              datetime.strptime(reservation['checkIn'], '%Y-%m-%d')).days
    
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; direction: ltr;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #f5f5f5; padding: 20px; border-radius: 8px;">
                <h2 style="color: #0C4848; border-bottom: 3px solid #0C4848; padding-bottom: 10px;">
                    🔔 YENİ REZERVASYON GELDİ
                </h2>
                
                <div style="background-color: white; padding: 20px; border-radius: 5px; margin: 15px 0;">
                    <h3 style="color: #333; margin-top: 0;">Misafir Bilgileri:</h3>
                    <p><strong>Ad Soyad:</strong> {reservation['name']}</p>
                    <p><strong>Email:</strong> {reservation['email']}</p>
                    <p><strong>Telefon:</strong> {reservation['phone']}</p>
                    <p><strong>Misafir Sayısı:</strong> {reservation['guests']} kişi</p>
                    
                    <h3 style="color: #333;">Rezervasyon Detayları:</h3>
                    <p><strong>Bungalov:</strong> {reservation['bungalow']}</p>
                    <p><strong>Giriş Tarihi:</strong> {check_in}</p>
                    <p><strong>Çıkış Tarihi:</strong> {check_out}</p>
                    <p><strong>Gece Sayısı:</strong> {nights} gece</p>
                    
                    {f"<p><strong>Notlar:</strong> {reservation['notes']}</p>" if reservation.get('notes') else ""}
                </div>
                
                <div style="background-color: #e8f4f8; padding: 15px; border-radius: 5px; margin: 15px 0;">
                    <p style="margin: 0; color: #0C4848;">
                        <strong>⏳ Bu rezervasyon onay bekleniyor.</strong><br>
                        Admin paneline giderek onaylamak veya reddetmek için <a href="http://localhost:5000/admin" style="color: #667eea; text-decoration: none;">tıklayınız</a>
                    </p>
                </div>
                
                <hr style="border: 1px solid #ddd; margin: 20px 0;">
                <p style="color: #999; font-size: 12px; text-align: center;">
                    Bu email otomatik olarak gönderilmiştir. Lütfen cevaplamayınız.
                </p>
            </div>
        </body>
    </html>
    """
    
    return send_email(ADMIN_EMAIL, f"🔔 Yeni Rezervasyon: {reservation['name']}", html_body)

def send_customer_confirmation_email(reservation, approved=True):
    """Send confirmation or rejection email to customer"""
    check_in = datetime.strptime(reservation['checkIn'], '%Y-%m-%d').strftime('%d.%m.%Y')
    check_out = datetime.strptime(reservation['checkOut'], '%Y-%m-%d').strftime('%d.%m.%Y')
    
    if approved:
        subject = "✅ Rezervasyonunuz Onaylandı!"
        status_color = "#28a745"
        status_text = "ONAYLANDI"
        message = "Rezervasyonunuz başarıyla onaylanmıştır. Belirtilen tarihte sizi misafir etmekten mutluluk duyacağız."
    else:
        subject = "❌ Rezervasyonunuz Reddedildi"
        status_color = "#dc3545"
        status_text = "RESİRED"
        message = "Maalesef, seçtiğiniz tarihler için rezervasyonunuz reddedilmiştir. Lütfen farklı tarihler seçerek yeniden deneyiniz."
    
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; direction: ltr;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #f5f5f5; padding: 20px; border-radius: 8px;">
                <h2 style="color: {status_color}; border-bottom: 3px solid {status_color}; padding-bottom: 10px;">
                    {subject}
                </h2>
                
                <div style="background-color: white; padding: 20px; border-radius: 5px; margin: 15px 0;">
                    <p style="font-size: 16px; color: #333;">{message}</p>
                    
                    <div style="background-color: {status_color}; color: white; padding: 15px; border-radius: 5px; margin: 15px 0; text-align: center;">
                        <p style="margin: 0; font-size: 18px; font-weight: bold;">{status_text}</p>
                    </div>
                    
                    <h3 style="color: #333; margin-top: 20px;">Rezervasyon Detayları:</h3>
                    <p><strong>Bungalov:</strong> {reservation['bungalow']}</p>
                    <p><strong>Giriş Tarihi:</strong> {check_in}</p>
                    <p><strong>Çıkış Tarihi:</strong> {check_out}</p>
                    <p><strong>Misafir Sayısı:</strong> {reservation['guests']} kişi</p>
                </div>
                
                <div style="background-color: #f0f0f0; padding: 15px; border-radius: 5px; margin: 15px 0;">
                    <p style="margin: 0; color: #666; font-size: 14px;">
                        <strong>Sorularınız var mı?</strong><br>
                        Bize <a href="mailto:admin@bungalow.com" style="color: #667eea; text-decoration: none;">admin@bungalow.com</a> 
                        adresinden ulaşabilirsiniz.
                    </p>
                </div>
                
                <hr style="border: 1px solid #ddd; margin: 20px 0;">
                <p style="color: #999; font-size: 12px; text-align: center;">
                    © 2024 Bungalow Rezervasyon Sistemi. Tüm hakları saklıdır.
                </p>
            </div>
        </body>
    </html>
    """
    
    return send_email(reservation['email'], subject, html_body)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/admin/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")  # 5 login attempts per minute
def admin_login():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if username in ADMIN_CREDENTIALS and check_password_hash(ADMIN_CREDENTIALS[username], password):
            session['admin_logged_in'] = True
            logger.info(f"Admin giriş başarılı: {username}")
            return jsonify({'success': True}), 200
        else:
            logger.warning(f"Admin giriş başarısız: {username} - IP: {get_remote_address()}")
            return jsonify({'success': False, 'message': 'Geçersiz kullanıcı adı veya şifre'}), 401
    
    return render_template('admin_login.html')

@app.route('/admin', methods=['GET'])
@login_required
def admin_panel():
    return render_template('admin_panel.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/reservation')
def reservation():
    return render_template('reservation.html')

@app.route('/bungalows')
def bungalows():
    return render_template('bungalows.html')

@app.route('/gallery')
def gallery():
    return render_template('gallery.html')

@app.route('/api/reservation', methods=['POST'])
@limiter.limit("10 per hour")  # 10 new reservations per hour per IP
def create_reservation():
    try:
        data = request.get_json()
        
        required_fields = ['name', 'email', 'phone', 'checkIn', 'checkOut', 'guests', 'bungalow']
        if not all(field in data for field in required_fields):
            logger.warning("Eksik alanlar ile rezervasyon isteği")
            return jsonify({'message': 'Tüm gerekli alanlar doldurulmalıdır.'}), 400
        
        # Validate name
        if not validate_name(data['name']):
            logger.warning(f"Geçersiz ad soyad: {data.get('name')}")
            return jsonify({'message': 'Lütfen geçerli bir ad soyad giriniz (2-100 karakter).'}), 400
        
        # Validate email
        if not validate_email(data['email']):
            logger.warning(f"Geçersiz email: {data['email']}")
            return jsonify({'message': 'Lütfen geçerli bir e-mail adresi giriniz.'}), 400
        
        # Validate phone
        if not validate_phone(data['phone']):
            logger.warning(f"Geçersiz telefon: {data['phone']}")
            return jsonify({'message': 'Lütfen geçerli bir telefon numarası giriniz.'}), 400
        
        # Validate guests
        if not validate_guests(data['guests']):
            logger.warning(f"Geçersiz misafir sayısı: {data['guests']}")
            return jsonify({'message': 'Lütfen 1-20 arasında misafir sayısı giriniz.'}), 400
        
        # Validate bungalow
        if not validate_bungalow(data['bungalow']):
            logger.warning(f"Geçersiz bungalov adı: {data['bungalow']}")
            return jsonify({'message': 'Lütfen geçerli bir bungalov adı seçiniz.'}), 400
        
        # Validate notes
        if not validate_notes(data.get('notes')):
            logger.warning(f"Geçersiz notlar: çok uzun")
            return jsonify({'message': 'Notlar 500 karakterden fazla olamaz.'}), 400
        
        # Validate date format and range
        if not validate_date(data['checkIn']):
            logger.warning(f"Geçersiz giriş tarihi: {data['checkIn']}")
            return jsonify({'message': 'Giriş tarihi bugünden sonra olmalıdır.'}), 400
        
        if not validate_date(data['checkOut']):
            logger.warning(f"Geçersiz çıkış tarihi: {data['checkOut']}")
            return jsonify({'message': 'Çıkış tarihi bugünden sonra olmalıdır.'}), 400
        
        if not validate_date_range(data['checkIn'], data['checkOut']):
            logger.warning(f"Geçersiz tarih aralığı: {data['checkIn']} - {data['checkOut']}")
            return jsonify({'message': 'Çıkış tarihi giriş tarihinden sonra olmalı ve 90 günü aşmamalıdır.'}), 400
        
        # Check for date conflicts
        if check_date_conflict(data['checkIn'], data['checkOut'], data['bungalow']):
            logger.info(f"Tarih çakışması: {data['bungalow']} - {data['checkIn']} - {data['checkOut']}")
            return jsonify({'message': 'Seçilen tarihler bu bungalov için uygun değildir. Lütfen başka tarihler seçiniz.'}), 409
        
        data['id'] = str(uuid.uuid4())  # Add unique ID
        data['timestamp'] = get_local_datetime().isoformat()
        data['status'] = 'pending'  # New reservations are pending approval
        
        # Save to database using database module
        db.save_reservation(data)
        
        logger.info(f"Yeni rezervasyon: ID={data['id']}, {data['name']}, {data['bungalow']}, {data['checkIn']}-{data['checkOut']}")
        
        # Send email to admin
        send_admin_reservation_notification(data)
        
        return jsonify({
            'message': 'Rezervasyon başarıyla kaydedildi! Admin onayı bekleniyor.',
            'reservation_id': data['id']
        }), 201
        
    except Exception as e:
        logger.exception(f"Rezervasyon oluşturma hatası: {str(e)}")
        return jsonify({'message': 'Bir hata oluştu. Lütfen tekrar deneyiniz.'}), 500

@app.route('/api/reservations', methods=['GET'])
@login_required
def get_reservations():
    try:
        reservations = load_reservations()
        logger.info(f"Tüm rezervasyonlar getiriliyor: {len(reservations)} kayıt")
        return jsonify(reservations), 200
    except Exception as e:
        logger.exception(f"Rezervasyonları getirme hatası: {str(e)}")
        return jsonify({'message': 'Bir hata oluştu.'}), 500

@app.route('/api/reservations/pending', methods=['GET'])
@login_required
def get_pending_reservations():
    """Get only pending reservations for admin approval"""
    try:
        reservations = load_reservations()
        pending = [res for res in reservations if res.get('status') == 'pending']
        logger.info(f"Beklemede rezervasyonlar getiriliyor: {len(pending)} kayıt")
        return jsonify(pending), 200
    except Exception as e:
        logger.exception(f"Beklemede rezervasyonları getirme hatası: {str(e)}")
        return jsonify({'message': 'Bir hata oluştu.'}), 500

@app.route('/api/reservations/<reservation_id>/approve', methods=['POST'])
@login_required
def approve_reservation(reservation_id):
    """Approve a pending reservation"""
    try:
        reservations = load_reservations()
        
        # Find reservation by ID instead of index
        res_index = None
        for idx, res in enumerate(reservations):
            if res.get('id') == reservation_id:
                res_index = idx
                break
        
        if res_index is None:
            logger.warning(f"Onaylama hatası: Rezervasyon bulunamadı - ID={reservation_id}")
            return jsonify({'message': 'Rezervasyon bulunamadı.'}), 404
        
        reservations[res_index]['status'] = 'approved'
        reservations[res_index]['approved_date'] = get_local_datetime().isoformat()
        
        save_reservations(reservations)
        
        logger.info(f"Rezervasyon onaylandı: ID={reservation_id}, Müşteri={reservations[res_index].get('name')}")
        
        # Send confirmation email to customer
        send_customer_confirmation_email(reservations[res_index], approved=True)
        
        return jsonify({
            'message': 'Rezervasyon onaylandı!',
            'reservation': reservations[res_index]
        }), 200
    except Exception as e:
        logger.exception(f"Rezervasyon onaylama hatası: {str(e)}")
        return jsonify({'message': 'Bir hata oluştu.'}), 500

@app.route('/api/reservations/<reservation_id>/reject', methods=['POST'])
@login_required
def reject_reservation(reservation_id):
    """Reject a pending reservation"""
    try:
        reservations = load_reservations()
        
        # Find reservation by ID instead of index
        res_index = None
        for idx, res in enumerate(reservations):
            if res.get('id') == reservation_id:
                res_index = idx
                break
        
        if res_index is None:
            logger.warning(f"Red etme hatası: Rezervasyon bulunamadı - ID={reservation_id}")
            return jsonify({'message': 'Rezervasyon bulunamadı.'}), 404
        
        reservations[res_index]['status'] = 'rejected'
        reservations[res_index]['rejected_date'] = get_local_datetime().isoformat()
        
        save_reservations(reservations)
        
        logger.info(f"Rezervasyon reddedildi: ID={reservation_id}, Müşteri={reservations[res_index].get('name')}")
        
        # Send rejection email to customer
        send_customer_confirmation_email(reservations[res_index], approved=False)
        
        return jsonify({'message': 'Rezervasyon reddedildi.'}), 200
    except Exception as e:
        logger.exception(f"Rezervasyon red etme hatası: {str(e)}")
        return jsonify({'message': 'Bir hata oluştu.'}), 500

@app.route('/api/booked-dates', methods=['GET'])
def get_booked_dates_api():
    """Get booked dates for a specific bungalow (for calendar display on frontend)"""
    try:
        bungalow = request.args.get('bungalow', '')
        
        if bungalow:
            # Get dates for specific bungalow
            booked_dates = []
            reservations = db.load_reservations()
            
            for res in reservations:
                if res.get('bungalow') == bungalow and res.get('status') != 'rejected':
                    # Add all dates between check-in and check-out
                    check_in = datetime.strptime(res['checkIn'], '%Y-%m-%d')
                    check_out = datetime.strptime(res['checkOut'], '%Y-%m-%d')
                    
                    current_date = check_in
                    while current_date < check_out:
                        booked_dates.append(current_date.strftime('%Y-%m-%d'))
                        current_date += timedelta(days=1)
            
            logger.info(f"Bungalov {bungalow} için dolu tarihler getiriliyor: {len(booked_dates)} gün")
            return jsonify({'booked_dates': list(set(booked_dates))}), 200
        else:
            # Get all booked dates if no specific bungalow
            booked_dates = get_booked_dates()
            logger.info(f"Dolu tarihler getiriliyor: {len(booked_dates)} gün")
            return jsonify({'booked_dates': booked_dates}), 200
    except Exception as e:
        logger.exception(f"Dolu tarihler getirme hatası: {str(e)}")
        return jsonify({'message': 'Bir hata oluştu.'}), 500

@app.route('/api/bungalow-dates/<bungalow>', methods=['GET'])
@login_required
def get_bungalow_dates(bungalow):
    """Get approved and pending dates for a specific bungalow with guest names"""
    try:
        reservations = load_reservations()
        date_info = {}  # {date: {status, guest_name}}
        
        for res in reservations:
            if res.get('bungalow') == bungalow:
                check_in = datetime.strptime(res['checkIn'], '%Y-%m-%d')
                check_out = datetime.strptime(res['checkOut'], '%Y-%m-%d')
                guest_name = res.get('name', 'Misafir')
                
                current_date = check_in
                while current_date < check_out:
                    date_str = current_date.strftime('%Y-%m-%d')
                    if res.get('status') in ['approved', 'pending']:
                        if date_str not in date_info:
                            date_info[date_str] = {
                                'status': res.get('status'),
                                'guest_name': guest_name
                            }
                    current_date += timedelta(days=1)
        
        logger.info(f"Bungalov tarihleri getiriliyor: {bungalow} - {len(date_info)} gün")
        return jsonify({
            'bungalow': bungalow,
            'date_info': date_info
        }), 200
    except Exception as e:
        logger.exception(f"Bungalov tarihlerini getirme hatası: {str(e)}")
        return jsonify({'message': 'Bir hata oluştu.'}), 500

if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("Bungalow Rezervasyon Sistemi başlatılıyor...")
    logger.info("=" * 50)
    
    # Migrate from JSON if exists
    if os.path.exists('reservations.json'):
        logger.info("JSON dosyasından SQLite'ye veri taşınıyor...")
        db.migrate_from_json()
    
    app.run(debug=True)


