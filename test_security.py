import os
os.environ.setdefault('ADMIN_PASSWORD','test-only-strong-password')
os.environ.setdefault('SECRET_KEY','test-only-secret-key-with-32-characters')
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch
from app import app, send_admin_reservation_notification
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
