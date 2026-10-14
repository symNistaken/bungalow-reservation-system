# -*- coding: utf-8 -*-
"""
Unit tests for Bungalow Reservation System
"""

import unittest
import json
import os
from datetime import datetime, timedelta
from app import (
    app, validate_email, validate_phone, validate_name, validate_guests,
    validate_bungalow, validate_date, validate_date_range, validate_notes,
    check_date_conflict
)
import database as db


class ValidationTestCase(unittest.TestCase):
    """Test input validation functions"""
    
    def test_validate_email_valid(self):
        """Test valid email addresses"""
        self.assertTrue(validate_email('test@example.com'))
        self.assertTrue(validate_email('user.name@example.co.uk'))
        self.assertTrue(validate_email('test123@domain.org'))
    
    def test_validate_email_invalid(self):
        """Test invalid email addresses"""
        self.assertFalse(validate_email('invalid.email'))
        self.assertFalse(validate_email('test@'))
        self.assertFalse(validate_email('@example.com'))
        self.assertFalse(validate_email(''))
        self.assertFalse(validate_email(None))
    
    def test_validate_phone_valid(self):
        """Test valid phone numbers"""
        self.assertTrue(validate_phone('05301234567'))
        self.assertTrue(validate_phone('0530 123 4567'))
        self.assertTrue(validate_phone('+90 530 123 4567'))
        self.assertTrue(validate_phone('1234567'))
    
    def test_validate_phone_invalid(self):
        """Test invalid phone numbers"""
        self.assertFalse(validate_phone('123'))  # Too short
        self.assertFalse(validate_phone('abc'))  # Not digits
        self.assertFalse(validate_phone(''))
        self.assertFalse(validate_phone(None))
    
    def test_validate_name_valid(self):
        """Test valid names"""
        self.assertTrue(validate_name('Ahmet Yılmaz'))
        self.assertTrue(validate_name('Ali'))
        self.assertTrue(validate_name("Mary O'Brien"))
        self.assertTrue(validate_name('Jean-Paul'))
    
    def test_validate_name_invalid(self):
        """Test invalid names"""
        self.assertFalse(validate_name('A'))  # Too short
        self.assertFalse(validate_name(''))
        self.assertFalse(validate_name('123'))  # Numbers
        self.assertFalse(validate_name(None))
    
    def test_validate_guests_valid(self):
        """Test valid guest counts"""
        self.assertTrue(validate_guests(1))
        self.assertTrue(validate_guests(10))
        self.assertTrue(validate_guests(20))
        self.assertTrue(validate_guests('5'))
    
    def test_validate_guests_invalid(self):
        """Test invalid guest counts"""
        self.assertFalse(validate_guests(0))
        self.assertFalse(validate_guests(21))
        self.assertFalse(validate_guests('abc'))
        self.assertFalse(validate_guests(None))
    
    def test_validate_bungalow_valid(self):
        """Test valid bungalow names"""
        self.assertTrue(validate_bungalow('Bungalow 1'))
        self.assertTrue(validate_bungalow('Evi Komfort'))
        self.assertTrue(validate_bungalow('A1'))
    
    def test_validate_bungalow_invalid(self):
        """Test invalid bungalow names"""
        self.assertFalse(validate_bungalow('A'))  # Too short
        self.assertFalse(validate_bungalow(''))
        self.assertFalse(validate_bungalow(None))
    
    def test_validate_notes_valid(self):
        """Test valid notes"""
        self.assertTrue(validate_notes(None))
        self.assertTrue(validate_notes(''))
        self.assertTrue(validate_notes('Some special requests'))
        self.assertTrue(validate_notes('A' * 500))
    
    def test_validate_notes_invalid(self):
        """Test invalid notes"""
        self.assertFalse(validate_notes('A' * 501))  # Too long
    
    def test_validate_date_valid(self):
        """Test valid dates"""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        self.assertTrue(validate_date(tomorrow))
    
    def test_validate_date_invalid(self):
        """Test invalid dates"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        self.assertFalse(validate_date(yesterday))
        self.assertFalse(validate_date('2024-99-99'))
        self.assertFalse(validate_date(''))
    
    def test_validate_date_range_valid(self):
        """Test valid date ranges"""
        check_in = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        check_out = (datetime.now() + timedelta(days=10)).strftime('%Y-%m-%d')
        self.assertTrue(validate_date_range(check_in, check_out))
    
    def test_validate_date_range_invalid(self):
        """Test invalid date ranges"""
        check_in = (datetime.now() + timedelta(days=10)).strftime('%Y-%m-%d')
        check_out = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        # Reverse order
        self.assertFalse(validate_date_range(check_in, check_out))
        
        # Over 90 days
        check_in = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        check_out = (datetime.now() + timedelta(days=100)).strftime('%Y-%m-%d')
        self.assertFalse(validate_date_range(check_in, check_out))


class DatabaseTestCase(unittest.TestCase):
    """Test database operations"""
    
    @classmethod
    def setUpClass(cls):
        """Setup test database"""
        # Use a test database
        db.DATABASE_FILE = 'test_reservations.db'
        db.init_db()
    
    @classmethod
    def tearDownClass(cls):
        """Cleanup test database"""
        if os.path.exists('test_reservations.db'):
            os.remove('test_reservations.db')
    
    def setUp(self):
        """Clear database before each test"""
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM reservations')
            conn.commit()
    
    def test_save_and_load_reservation(self):
        """Test saving and loading a reservation"""
        reservation = {
            'id': 'test-id-123',
            'name': 'Ahmet Yılmaz',
            'email': 'ahmet@example.com',
            'phone': '05301234567',
            'checkIn': '2024-12-25',
            'checkOut': '2024-12-30',
            'guests': 4,
            'bungalow': 'Bungalow 1',
            'notes': 'Test reservation',
            'status': 'pending',
            'timestamp': datetime.now().isoformat()
        }
        
        db.save_reservation(reservation)
        loaded = db.get_reservation_by_id('test-id-123')
        
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded['name'], 'Ahmet Yılmaz')
        self.assertEqual(loaded['status'], 'pending')
    
    def test_update_reservation_status(self):
        """Test updating reservation status"""
        reservation = {
            'id': 'test-id-456',
            'name': 'Test User',
            'email': 'test@example.com',
            'phone': '05301234567',
            'checkIn': '2024-12-25',
            'checkOut': '2024-12-30',
            'guests': 2,
            'bungalow': 'Bungalow 1',
            'status': 'pending',
            'timestamp': datetime.now().isoformat()
        }
        
        db.save_reservation(reservation)
        db.update_reservation_status('test-id-456', 'approved')
        
        updated = db.get_reservation_by_id('test-id-456')
        self.assertEqual(updated['status'], 'approved')
        self.assertIsNotNone(updated['approved_date'])
    
    def test_get_reservations_by_status(self):
        """Test getting reservations by status"""
        # Create multiple reservations
        for i in range(3):
            db.save_reservation({
                'id': f'pending-{i}',
                'name': f'User {i}',
                'email': f'user{i}@example.com',
                'phone': '05301234567',
                'checkIn': '2024-12-25',
                'checkOut': '2024-12-30',
                'guests': 2,
                'bungalow': 'Bungalow 1',
                'status': 'pending',
                'timestamp': datetime.now().isoformat()
            })
        
        pending = db.load_reservations_by_status('pending')
        self.assertEqual(len(pending), 3)


class APITestCase(unittest.TestCase):
    """Test API endpoints"""

    def test_admin_endpoints_require_login(self):
        for method, path in [
            ('get', '/api/reservations'),
            ('get', '/api/reservations/pending'),
            ('post', '/api/reservations/example/approve'),
            ('post', '/api/reservations/example/reject'),
            ('get', '/api/bungalow-dates/Bungalow%201'),
        ]:
            with self.subTest(method=method, path=path):
                with app.test_client() as client:
                    response = getattr(client, method)(path)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.headers['Location'].endswith('/admin/login'))

    def test_logged_in_admin_can_list_reservations(self):
        with app.test_client() as client:
            with client.session_transaction() as session:
                session['admin_logged_in'] = True
            response = client.get('/api/reservations')
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.get_json(), list)
    
    @classmethod
    def setUpClass(cls):
        """Setup test client"""
        cls.app = app
        cls.app.config['TESTING'] = True
        cls.client = cls.app.test_client()
    
    def test_home_page(self):
        """Test home page loads"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
    
    def test_admin_login_page(self):
        """Test admin login page loads"""
        response = self.client.get('/admin/login')
        self.assertEqual(response.status_code, 200)
    
    def test_reservation_page(self):
        """Test reservation page loads"""
        response = self.client.get('/reservation')
        self.assertEqual(response.status_code, 200)
    
    def test_invalid_reservation_missing_fields(self):
        """Test reservation with missing fields"""
        response = self.client.post('/api/reservation', 
            json={'name': 'Test User'},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn('gerekli alanlar', data['message'].lower())
    
    def test_invalid_reservation_bad_email(self):
        """Test reservation with invalid email"""
        response = self.client.post('/api/reservation',
            json={
                'name': 'Test User',
                'email': 'invalid-email',
                'phone': '05301234567',
                'checkIn': '2024-12-25',
                'checkOut': '2024-12-30',
                'guests': 2,
                'bungalow': 'Bungalow 1'
            },
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertTrue('mail' in data['message'].lower())  # Check for "email" or "e-mail"


if __name__ == '__main__':
    unittest.main()
