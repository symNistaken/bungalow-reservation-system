# Backend utility: Berkay Seyman (2026)
# Copyright (c) 2026 Berkay Seyman. All rights reserved.

"""
SQLite Database Inspector
Reservation database'ini incelemek için basit araç
"""

import sqlite3
import json
try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False

DATABASE_FILE = 'reservations.db'

def inspect_database():
    """Database'i inceleme"""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Tablolar
        print("=" * 80)
        print("📊 DATABASE ÖZETİ")
        print("=" * 80)
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        if not tables:
            print("❌ Hiç tablo bulunamadı!")
            return
        
        print(f"\n✅ Tablolar ({len(tables)}):")
        for table in tables:
            table_name = table['name']
            cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            count = cursor.fetchone()['count']
            print(f"   - {table_name}: {count} satır")
        
        # Detaylı rezervasyon bilgileri
        print("\n" + "=" * 80)
        print("📋 REZERVASYONLAR")
        print("=" * 80)
        
        cursor.execute('''
            SELECT 
                id, name, email, bungalow, checkIn, checkOut, 
                guests, status, timestamp
            FROM reservations
            ORDER BY timestamp DESC
        ''')
        
        reservations = cursor.fetchall()
        
        if not reservations:
            print("\n❌ Hiç rezervasyon yok!")
            return
        
        print(f"\n✅ Toplam Rezervasyon: {len(reservations)}\n")
        
        # Tabloyu göster
        data = []
        for res in reservations:
            data.append([
                res['name'][:20],
                res['email'][:20],
                res['bungalow'],
                res['checkIn'],
                res['checkOut'],
                res['guests'],
                res['status'].upper(),
                res['timestamp'][:10]
            ])
        
        headers = ['İsim', 'Email', 'Bungalov', 'Giriş', 'Çıkış', 'Misafir', 'Durum', 'Tarih']
        
        if HAS_TABULATE:
            print(tabulate(data, headers=headers, tablefmt='grid'))
        else:
            # Tabulate yoksa basit şekilde göster
            print("\t".join(headers))
            print("-" * 120)
            for row in data:
                print("\t".join(str(cell) for cell in row))
        
        # İstatistikler
        print("\n" + "=" * 80)
        print("📈 İSTATİSTİKLER")
        print("=" * 80)
        
        cursor.execute('SELECT status, COUNT(*) as count FROM reservations GROUP BY status')
        stats = cursor.fetchall()
        
        for stat in stats:
            print(f"   {stat['status'].upper()}: {stat['count']}")
        
        # Bungalov başına
        print("\n   Bungalov başına:")
        cursor.execute('SELECT bungalow, COUNT(*) as count FROM reservations GROUP BY bungalow ORDER BY count DESC')
        bungalow_stats = cursor.fetchall()
        
        for bstat in bungalow_stats:
            print(f"      {bstat['bungalow']}: {bstat['count']}")
        
        # Detaylı görünüm
        print("\n" + "=" * 80)
        print("🔍 DETAYLI GÖRÜNÜM")
        print("=" * 80)
        
        for i, res in enumerate(reservations[:3], 1):  # İlk 3'ü göster
            print(f"\n📌 Rezervasyon #{i}:")
            print(f"   ID: {res['id']}")
            print(f"   İsim: {res['name']}")
            print(f"   Email: {res['email']}")
            print(f"   Telefon: {res.get('phone', 'N/A')}")
            print(f"   Bungalov: {res['bungalow']}")
            print(f"   Tarih: {res['checkIn']} → {res['checkOut']}")
            print(f"   Misafir: {res['guests']}")
            print(f"   Durum: {res['status']}")
            print(f"   Kaydedilme: {res['timestamp']}")
            if res.get('approved_date'):
                print(f"   Onay Tarihi: {res['approved_date']}")
            if res.get('rejected_date'):
                print(f"   Red Tarihi: {res['rejected_date']}")
        
        if len(reservations) > 3:
            print(f"\n   ... ve {len(reservations) - 3} tane daha")
        
        print("\n" + "=" * 80)
        
        conn.close()
        
    except FileNotFoundError:
        print(f"❌ Database dosyası bulunamadı: {DATABASE_FILE}")
        print("   Lütfen önce uygulamayı çalıştırın: python app.py")
    except Exception as e:
        print(f"❌ Hata: {str(e)}")

if __name__ == '__main__':
    inspect_database()
