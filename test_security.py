import os
os.environ.setdefault('ADMIN_PASSWORD','test-only-strong-password')
os.environ.setdefault('SECRET_KEY','test-only-secret-key-with-32-characters')
import json
from datetime import datetime, timedelta
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch
from app import app, send_admin_reservation_notification
import app as app_module
import database as db


class SecurityTests(unittest.TestCase):
    def test_csrf_token_is_bound_to_session(self):
        with app.test_client() as owner:
            page=owner.get('/reservation').get_data(as_text=True)
            token=re.search(r'name="csrf-token" content="([^"]+)"',page).group(1)
        with app.test_client() as other:
            response=other.post('/admin/login',json={'username':'admin','password':'test-only-strong-password'},headers={'X-CSRFToken':token})
        self.assertEqual(response.status_code,400)

    def test_authenticated_decision_still_requires_csrf(self):
        with app.test_client() as client:
            with client.session_transaction() as session: session['admin_logged_in']=True
            self.assertEqual(client.post('/api/reservations/example/approve').status_code,400)

    def test_login_refreshes_session_and_logout_uses_csrf(self):
        with app.test_client() as client:
            page=client.get('/reservation').get_data(as_text=True)
            token=re.search(r'name="csrf-token" content="([^"]+)"',page).group(1)
            with client.session_transaction() as session: session['untrusted_previous_value']=True
            response=client.post('/admin/login',json={'username':'admin','password':'test-only-strong-password'},headers={'X-CSRFToken':token})
            self.assertEqual(response.status_code,200)
            with client.session_transaction() as session:
                self.assertTrue(session['admin_logged_in'])
                self.assertNotIn('untrusted_previous_value',session)
            page=client.get('/admin').get_data(as_text=True)
            token=re.search(r'name="csrf-token" content="([^"]+)"',page).group(1)
            self.assertEqual(client.post('/admin/logout',data={'csrf_token':token}).status_code,302)
            with client.session_transaction() as session: self.assertNotIn('admin_logged_in',session)

    def test_email_markup_escapes_customer_supplied_values(self):
        reservation=dict(name='Test',email='test@example.com',phone='05301234567',bungalow='<img src=x onerror=alert(1)>',checkIn='2027-01-01',checkOut='2027-01-05',guests=2)
        with patch('app.send_email',return_value=True) as sending:
            send_admin_reservation_notification(reservation)
        body=sending.call_args.args[2]
        self.assertNotIn('<img src=x',body)
        self.assertIn('&lt;img',body)

    def test_production_refuses_missing_secret_and_default_password(self):
        environment=dict(os.environ, APP_ENV='production',ADMIN_PASSWORD='admin123')
        environment.pop('SECRET_KEY',None)
        result=subprocess.run([sys.executable,'-c','import app'],cwd=Path(__file__).parent,env=environment,capture_output=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b'non-default ADMIN_PASSWORD',result.stderr)


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.original=db.DATABASE_FILE
        db.DATABASE_FILE=str(Path(self.directory.name)/'reservations.db')
        db.init_db()

    def tearDown(self):
        db.DATABASE_FILE=self.original
        self.directory.cleanup()

    def sample(self,identifier,check_in='2027-01-01',check_out='2027-01-05'):
        return dict(id=identifier,name='Test',email='test@example.com',phone='05301234567',checkIn=check_in,checkOut=check_out,guests=2,bungalow='Bungalow 1',status='pending')

    def test_concurrent_overlapping_approvals_allow_only_one(self):
        for identifier in ('one','two'): db.create_pending_reservation(self.sample(identifier))
        def approve(identifier):
            try:
                db.transition_reservation(identifier,'approved')
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as workers:
            outcomes=list(workers.map(approve,('one','two')))
        self.assertEqual(outcomes.count(True),1)
        self.assertEqual(len(db.load_reservations()),2)
        self.assertEqual(len(db.get_approved_reservations()),1)

    def test_adjacent_booking_allowed_and_other_records_preserved(self):
        db.create_pending_reservation(self.sample('first'))
        db.transition_reservation('first','approved')
        db.create_pending_reservation(self.sample('adjacent','2027-01-05','2027-01-08'))
        db.transition_reservation('adjacent','approved')
        self.assertEqual(len(db.get_approved_reservations()),2)
        with self.assertRaises(ValueError): db.create_pending_reservation(self.sample('overlap'))

    def test_migration_preserves_existing_rows(self):
        db.save_reservation(self.sample('existing'))
        old_dir=os.getcwd()
        try:
            os.chdir(self.directory.name)
            Path('reservations.json').write_text(json.dumps([self.sample('imported')]),encoding='utf-8')
            self.assertEqual(db.migrate_from_json(),1)
            self.assertIsNotNone(db.get_reservation_by_id('existing'))
            self.assertIsNotNone(db.get_reservation_by_id('imported'))
        finally:
            os.chdir(old_dir)

    def test_failed_backup_does_not_commit_import(self):
        old_dir=os.getcwd()
        try:
            os.chdir(self.directory.name)
            Path('reservations.json').write_text(json.dumps([self.sample('imported')]),encoding='utf-8')
            with patch('database.os.rename',side_effect=PermissionError('backup blocked')):
                self.assertEqual(db.migrate_from_json(),0)
            self.assertIsNone(db.get_reservation_by_id('imported'))
            self.assertTrue(Path('reservations.json').is_file())
        finally:
            os.chdir(old_dir)

    def test_public_booked_dates_hide_pending_requests(self):
        future=(datetime.now()+timedelta(days=30)).strftime('%Y-%m-%d')
        later=(datetime.now()+timedelta(days=32)).strftime('%Y-%m-%d')
        db.save_reservation(dict(id='pending-only',name='Test',email='test@example.com',phone='05301234567',checkIn=future,checkOut=later,guests=2,bungalow='Akasya',status='pending'))
        try:
            with app.test_client() as client:
                dates=client.get('/api/booked-dates?bungalow=Akasya').get_json()['booked_dates']
            self.assertNotIn(future,dates)
        finally:
            db.delete_reservation('pending-only')

    def test_admin_email_link_uses_configured_base_url(self):
        reservation=dict(id='x',name='Test',email='test@example.com',phone='05301234567',checkIn='2030-01-01',checkOut='2030-01-03',guests=2,bungalow='Akasya')
        with patch('app.APP_BASE_URL','https://demo.example.com'), patch('app.send_email',return_value=True) as send:
            send_admin_reservation_notification(reservation)
        body=send.call_args.args[2]
        self.assertIn('https://demo.example.com/admin',body)
        self.assertNotIn('localhost:5000',body)


    def _quote(self, client, **overrides):
        app_module.limiter.reset()  # rate limit is tested separately; keep tests independent
        page = client.get('/kozalak').get_data(as_text=True)
        token = re.search(r'name="csrf-token" content="([^"]+)"', page).group(1)
        payload = dict(name='Test Kişi', business='Test Bungalov', phone='05301234567', package='site-rezervasyon', message='Merhaba')
        payload.update(overrides)
        return client.post('/api/quote', json=payload, headers={'X-CSRFToken': token})

    def test_sales_page_renders_contact_links(self):
        with app.test_client() as client:
            page = client.get('/kozalak').get_data(as_text=True)
        self.assertIn('https://wa.me/905340806421', page)
        self.assertIn('mailto:berkayseyman@gmail.com', page)
        self.assertIn('7.500 TL', page)

    def test_quote_requires_csrf(self):
        with app.test_client() as client:
            response = client.post('/api/quote', json=dict(name='Test Kişi', phone='05301234567', package='site'))
        self.assertEqual(response.status_code, 400)

    def test_quote_validation_and_delivery(self):
        with app.test_client() as client, patch('app.send_email', return_value=True) as send:
            self.assertEqual(self._quote(client, name='Ali\nBcc: x').status_code, 400)
            self.assertEqual(self._quote(client, business='A\nB').status_code, 400)
            self.assertEqual(self._quote(client, package='yok').status_code, 400)
            self.assertEqual(self._quote(client, phone='abc').status_code, 400)
            send.assert_not_called()
            self.assertEqual(self._quote(client, message='<script>x</script>').status_code, 201)
        to, subject, body = send.call_args.args
        self.assertEqual(to, 'berkayseyman@gmail.com')
        self.assertNotIn('<script>', body)

    def test_quote_reports_mail_failure(self):
        with app.test_client() as client, patch('app.send_email', return_value=False):
            self.assertEqual(self._quote(client).status_code, 503)

    def test_demo_mode_never_mails_visitors(self):
        reservation = dict(id='x', name='Test', email='visitor@example.com', phone='05301234567', checkIn='2030-01-01', checkOut='2030-01-03', guests=2, bungalow='Akasya')
        with patch('app.DEMO_MODE', True), patch('app.send_email', return_value=True) as send:
            self.assertFalse(send_admin_reservation_notification(reservation))
            self.assertFalse(app_module.send_customer_confirmation_email(reservation))
        send.assert_not_called()

    def test_demo_seed_populates_empty_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_dir = os.getcwd()
            os.chdir(tmp)
            try:
                db.init_db()
                app_module.seed_demo_data()
                statuses = {r['status'] for r in db.load_reservations()}
                self.assertEqual(statuses, {'approved', 'pending'})
                count = len(db.load_reservations())
                app_module.seed_demo_data()  # second call must not duplicate
                self.assertEqual(len(db.load_reservations()), count)
            finally:
                os.chdir(old_dir)
