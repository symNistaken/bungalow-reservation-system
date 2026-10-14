# -*- coding: utf-8 -*-
# Backend/database implementation: Berkay Seyman (2026)
# Copyright (c) 2026 Berkay Seyman. SPDX-License-Identifier: MIT
# MIT applies to Berkay Seyman contributions; see LICENSE and LICENSE-SCOPE.md.

"""
Database module for Bungalow Reservation System
Handles SQLite operations for reservations
"""

import sqlite3
import json
import os
import uuid
from datetime import datetime
from contextlib import contextmanager

DATABASE_FILE = 'reservations.db'

def init_db():
    """Initialize database with tables"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Create reservations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reservations (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                checkIn TEXT NOT NULL,
                checkOut TEXT NOT NULL,
                guests INTEGER NOT NULL,
                bungalow TEXT NOT NULL,
                notes TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                timestamp TEXT NOT NULL,
                approved_date TEXT,
                rejected_date TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create index for faster queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_status ON reservations(status)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_bungalow ON reservations(bungalow)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_email ON reservations(email)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_checkIn_checkOut ON reservations(checkIn, checkOut)
        ''')
        
        conn.commit()

@contextmanager
def get_db():
    """Get database connection with context manager"""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    try:
        yield conn
    finally:
        conn.close()

def dict_from_row(row):
    """Convert sqlite3.Row to dictionary"""
    if row is None:
        return None
    return dict(row)

# Reservation operations

def load_reservations():
    """Load all reservations from database"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM reservations ORDER BY timestamp DESC')
        rows = cursor.fetchall()
        return [dict_from_row(row) for row in rows]

def load_reservations_by_status(status):
    """Load reservations by status"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM reservations WHERE status = ? ORDER BY timestamp DESC', (status,))
        rows = cursor.fetchall()
        return [dict_from_row(row) for row in rows]

def get_reservation_by_id(reservation_id):
    """Get a single reservation by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM reservations WHERE id = ?', (reservation_id,))
        row = cursor.fetchone()
        return dict_from_row(row)

def _write_reservation(conn, reservation):
    """Upsert one row on the caller's transaction without replacing other rows."""
    columns = ('id', 'name', 'email', 'phone', 'checkIn', 'checkOut', 'guests',
               'bungalow', 'notes', 'status', 'timestamp', 'approved_date', 'rejected_date')
    values = dict(reservation)
    values.setdefault('notes', '')
    values.setdefault('status', 'pending')
    values.setdefault('timestamp', datetime.now().isoformat())
    update = ', '.join(f'{column}=excluded.{column}' for column in columns[1:])
    conn.execute(
        f"INSERT INTO reservations ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)}) "
        f"ON CONFLICT(id) DO UPDATE SET {update}, updated_at=CURRENT_TIMESTAMP",
        [values.get(column) for column in columns],
    )


def save_reservation(reservation):
    """Save or update a single reservation."""
    with get_db() as conn:
        _write_reservation(conn, reservation)
        conn.commit()


def _has_conflict(conn, reservation):
    return conn.execute(
        "SELECT 1 FROM reservations WHERE bungalow=? AND status='approved' "
        "AND id != ? AND checkIn < ? AND checkOut > ? LIMIT 1",
        (reservation['bungalow'], reservation['id'], reservation['checkOut'], reservation['checkIn']),
    ).fetchone() is not None


def create_pending_reservation(reservation):
    """Serialize the conflict check and insert against simultaneous approvals."""
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if _has_conflict(conn, reservation):
            raise ValueError('Reservation dates conflict')
        pending = dict(reservation, status='pending')
        _write_reservation(conn, pending)
        conn.commit()


def transition_reservation(reservation_id, status):
    """Atomically decide a pending request and reject overlapping approvals."""
    if status not in ('approved', 'rejected'):
        raise ValueError('Unsupported status transition')
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM reservations WHERE id=?', (reservation_id,)).fetchone()
        if row is None:
            return None
        reservation = dict(row)
        if reservation['status'] != 'pending':
            raise ValueError('Reservation already decided')
        if status == 'approved' and _has_conflict(conn, reservation):
            raise ValueError('Reservation dates conflict')
        date_column = 'approved_date' if status == 'approved' else 'rejected_date'
        timestamp = datetime.now().isoformat()
        conn.execute(f'UPDATE reservations SET status=?, {date_column}=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
                     (status, timestamp, reservation_id))
        conn.commit()
        reservation.update(status=status, **{date_column: timestamp})
        return reservation


def save_reservations(reservations):
    """Save multiple reservations (for batch operations)"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Clear existing data
        cursor.execute('DELETE FROM reservations')
        
        # Insert new data
        for res in reservations:
            cursor.execute('''
                INSERT INTO reservations 
                (id, name, email, phone, checkIn, checkOut, guests, bungalow, notes, status, timestamp, approved_date, rejected_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                res['id'],
                res['name'],
                res['email'],
                res['phone'],
                res['checkIn'],
                res['checkOut'],
                res['guests'],
                res['bungalow'],
                res.get('notes', ''),
                res.get('status', 'pending'),
                res.get('timestamp', datetime.now().isoformat()),
                res.get('approved_date'),
                res.get('rejected_date')
            ))
        
        conn.commit()

def update_reservation_status(reservation_id, status):
    """Use the same conflict-safe transition for all admin status changes."""
    return transition_reservation(reservation_id, status)


def get_reservations_by_bungalow(bungalow):
    """Get all reservations for a specific bungalow"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM reservations WHERE bungalow = ? ORDER BY checkIn', (bungalow,))
        rows = cursor.fetchall()
        return [dict_from_row(row) for row in rows]

def get_approved_reservations():
    """Get all approved reservations"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM reservations WHERE status = "approved" ORDER BY checkIn')
        rows = cursor.fetchall()
        return [dict_from_row(row) for row in rows]

def delete_reservation(reservation_id):
    """Delete a reservation"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM reservations WHERE id = ?', (reservation_id,))
        conn.commit()

def migrate_from_json():
    """Migrate data from JSON file to SQLite database"""
    json_file = 'reservations.json'
    
    if not os.path.exists(json_file):
        print(f"JSON file '{json_file}' not found. Starting with empty database.")
        return
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            reservations = json.load(f)
        
        if not reservations:
            print("JSON file is empty. Starting with empty database.")
            return
        
        # Add UUID to records that don't have 'id'
        for res in reservations:
            if 'id' not in res or not res['id']:
                res['id'] = str(uuid.uuid4())
        
        # Preserve the source backup before committing the import transaction.
        backup_file = 'reservations.json.backup'
        if os.path.exists(backup_file):
            raise FileExistsError('Migration backup already exists; inspect it before retrying.')
        with get_db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            for reservation in reservations:
                if conn.execute('SELECT 1 FROM reservations WHERE id=?', (reservation['id'],)).fetchone() is None:
                    _write_reservation(conn, reservation)
            os.rename(json_file, backup_file)
            conn.commit()
        
        print(f"✅ Successfully migrated {len(reservations)} reservations from JSON to SQLite")
        print(f"   Original file backed up as: {backup_file}")
        return len(reservations)
    
    except json.JSONDecodeError as e:
        print(f"❌ Error reading JSON file: {str(e)}")
        return 0
    except Exception as e:
        print(f"❌ Migration error: {str(e)}")
        return 0

# Statistics

def get_reservation_stats():
    """Get reservation statistics"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        stats = {}
        
        # Total reservations
        cursor.execute('SELECT COUNT(*) as count FROM reservations')
        stats['total'] = cursor.fetchone()['count']
        
        # By status
        cursor.execute('SELECT status, COUNT(*) as count FROM reservations GROUP BY status')
        for row in cursor.fetchall():
            stats[row['status']] = row['count']
        
        # By bungalow
        cursor.execute('SELECT bungalow, COUNT(*) as count FROM reservations GROUP BY bungalow ORDER BY count DESC')
        stats['by_bungalow'] = {row['bungalow']: row['count'] for row in cursor.fetchall()}
        
        return stats
