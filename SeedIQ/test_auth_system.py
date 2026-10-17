import unittest
import json
import os
import sys
import sqlite3
import datetime
from werkzeug.security import check_password_hash

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Ensure test environment variables are loaded
os.environ["SEEDIQ_ADMIN_EMAIL"] = "admin@seediq.ai"
os.environ["SEEDIQ_RESEARCHER_EMAIL"] = "researcher@quantum.org"
os.environ["FLASK_SECRET_KEY"] = "test_secret_key_quantum_123"
os.environ["GMAIL_SENDER_EMAIL"] = ""
os.environ["GMAIL_APP_PASSWORD"] = ""

from app import app, get_db, init_db, initialize_seediq_accounts

class SeedIQProfessionalAuthTests(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        init_db()
        initialize_seediq_accounts()
        with get_db() as conn:
            admin_email = os.environ.get("SEEDIQ_ADMIN_EMAIL", "admin@seediq.ai")
            researcher_email = os.environ.get("SEEDIQ_RESEARCHER_EMAIL", "researcher@quantum.org")
            conn.execute('DELETE FROM users WHERE email NOT IN (?, ?)', (admin_email, researcher_email))
            conn.execute('DELETE FROM otp_codes')
            conn.commit()

    def test_01_google_auth_removed(self):
        """1. Verify Google Auth endpoint is removed completely (404)."""
        res = self.client.post('/api/google-auth', json={"email": "test@gmail.com"})
        self.assertEqual(res.status_code, 404)

    def test_02_registration_weak_password_rejected(self):
        """2. Verify weak passwords fail complexity requirements."""
        # Less than 8 chars
        res1 = self.client.post('/api/register/request-otp', json={
            "name": "Test User", "email": "weak1@gmail.com", "password": "Ab1!"
        })
        self.assertEqual(res1.status_code, 400)

        # No uppercase
        res2 = self.client.post('/api/register/request-otp', json={
            "name": "Test User", "email": "weak2@gmail.com", "password": "password123!"
        })
        self.assertEqual(res2.status_code, 400)

        # No number
        res3 = self.client.post('/api/register/request-otp', json={
            "name": "Test User", "email": "weak3@gmail.com", "password": "Password!"
        })
        self.assertEqual(res3.status_code, 400)

        # No special char
        res4 = self.client.post('/api/register/request-otp', json={
            "name": "Test User", "email": "weak4@gmail.com", "password": "Password123"
        })
        self.assertEqual(res4.status_code, 400)

    def test_03_registration_request_otp(self):
        """3. Verify registration OTP generation for valid Gmail."""
        res = self.client.post('/api/register/request-otp', json={
            "name": "Sumith Farmer",
            "email": "sumith.farmer@gmail.com",
            "password": "StrongPassword123!"
        })
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(data["status"], "success")
        self.assertNotIn("otp", data)  # Secure: OTP never exposed in response

        with get_db() as conn:
            rec = conn.execute('SELECT * FROM otp_codes WHERE email = ? AND purpose = "registration"', ("sumith.farmer@gmail.com",)).fetchone()
            self.assertIsNotNone(rec)
            self.assertEqual(len(rec['otp']), 6)
            self.assertEqual(rec['name'], "Sumith Farmer")

    def test_04_registration_duplicate_email_rejected(self):
        """4. Verify duplicate registration with existing email is rejected (409)."""
        # Register first
        email = "dup.test@gmail.com"
        self.client.post('/api/register/request-otp', json={
            "name": "First User", "email": email, "password": "ValidPassword123!"
        })
        with get_db() as conn:
            otp = conn.execute('SELECT otp FROM otp_codes WHERE email = ?', (email,)).fetchone()['otp']
        self.client.post('/api/register/verify-otp', json={"email": email, "otp": otp})

        # Try to register again with same email
        res = self.client.post('/api/register/request-otp', json={
            "name": "Second User", "email": email, "password": "ValidPassword123!"
        })
        self.assertEqual(res.status_code, 409)

    def test_05_registration_incorrect_otp(self):
        """5. Verify incorrect registration OTP fails and increments attempt count."""
        email = "wrong_otp@gmail.com"
        self.client.post('/api/register/request-otp', json={
            "name": "Wrong OTP User", "email": email, "password": "ValidPassword123!"
        })

        res = self.client.post('/api/register/verify-otp', json={"email": email, "otp": "000000"})
        self.assertEqual(res.status_code, 400)
        data = json.loads(res.data)
        self.assertEqual(data["message"], "Verification code is incorrect.")

    def test_06_registration_max_attempts_lockout(self):
        """6. Verify exceeding 5 attempts deletes the OTP."""
        email = "max_attempts@gmail.com"
        self.client.post('/api/register/request-otp', json={
            "name": "Max Attempts User", "email": email, "password": "ValidPassword123!"
        })

        with get_db() as conn:
            conn.execute('UPDATE otp_codes SET attempts = 5 WHERE email = ?', (email,))
            conn.commit()

        res = self.client.post('/api/register/verify-otp', json={"email": email, "otp": "111111"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Too many attempts", json.loads(res.data)["message"])

        # Record should be wiped
        with get_db() as conn:
            rec = conn.execute('SELECT id FROM otp_codes WHERE email = ?', (email,)).fetchone()
            self.assertIsNone(rec)

    def test_07_registration_expired_otp(self):
        """7. Verify expired registration OTP is rejected."""
        email = "expired_reg@gmail.com"
        self.client.post('/api/register/request-otp', json={
            "name": "Expired User", "email": email, "password": "ValidPassword123!"
        })

        with get_db() as conn:
            past = (datetime.datetime.now() - datetime.timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
            conn.execute('UPDATE otp_codes SET expires_at = ? WHERE email = ?', (past, email))
            conn.commit()
            actual_otp = conn.execute('SELECT otp FROM otp_codes WHERE email = ?', (email,)).fetchone()['otp']

        res = self.client.post('/api/register/verify-otp', json={"email": email, "otp": actual_otp})
        self.assertEqual(res.status_code, 400)
        self.assertIn("expired", json.loads(res.data)["message"].lower())

    def test_08_successful_registration_and_farmer_role(self):
        """8. Verify successful registration assigns Farmer role and establishes session."""
        email = "new_farmer@gmail.com"
        self.client.post('/api/register/request-otp', json={
            "name": "New Farmer", "email": email, "password": "ValidPassword123!"
        })

        with get_db() as conn:
            otp = conn.execute('SELECT otp FROM otp_codes WHERE email = ?', (email,)).fetchone()['otp']

        res = self.client.post('/api/register/verify-otp', json={"email": email, "otp": otp})
        self.assertEqual(res.status_code, 201)
        user = json.loads(res.data)["user"]

        self.assertEqual(user["role"], "Farmer")
        self.assertEqual(user["display_name"], "New Farmer")
        self.assertEqual(user["email"], email)

        # Check password hashing in database
        with get_db() as conn:
            db_user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
            self.assertNotEqual(db_user['password'], "ValidPassword123!")
            self.assertTrue(check_password_hash(db_user['password'], "ValidPassword123!"))

    def test_09_normal_login_correct_password(self):
        """9. Verify normal sign-in with Gmail + Password."""
        # Create user
        email = "login_test@gmail.com"
        self.client.post('/api/register/request-otp', json={
            "name": "Login Tester", "email": email, "password": "ValidPassword123!"
        })
        with get_db() as conn:
            otp = conn.execute('SELECT otp FROM otp_codes WHERE email = ?', (email,)).fetchone()['otp']
        self.client.post('/api/register/verify-otp', json={"email": email, "otp": otp})

        # Login
        res = self.client.post('/api/login', json={
            "email": email,
            "password": "ValidPassword123!"
        })
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(data["user"]["email"], email)
        self.assertEqual(data["user"]["role"], "Farmer")
        self.assertEqual(data["user"]["display_name"], "Login Tester")

    def test_10_normal_login_incorrect_password(self):
        """10. Verify login fails with incorrect password (401)."""
        email = "login_fail@gmail.com"
        self.client.post('/api/register/request-otp', json={
            "name": "Login Fail", "email": email, "password": "ValidPassword123!"
        })
        with get_db() as conn:
            otp = conn.execute('SELECT otp FROM otp_codes WHERE email = ?', (email,)).fetchone()['otp']
        self.client.post('/api/register/verify-otp', json={"email": email, "otp": otp})

        res = self.client.post('/api/login', json={
            "email": email,
            "password": "WrongPassword123!"
        })
        self.assertEqual(res.status_code, 401)
        self.assertEqual(json.loads(res.data)["message"], "Invalid email or password.")

    def test_11_forgot_password_flow(self):
        """11. Verify complete forgot password flow with OTP and new password."""
        email = "reset_user@gmail.com"
        # 1. Create account
        self.client.post('/api/register/request-otp', json={
            "name": "Reset User", "email": email, "password": "OldPassword123!"
        })
        with get_db() as conn:
            otp = conn.execute('SELECT otp FROM otp_codes WHERE email = ?', (email,)).fetchone()['otp']
        self.client.post('/api/register/verify-otp', json={"email": email, "otp": otp})

        # 2. Request forgot password OTP
        req_res = self.client.post('/api/forgot-password/request-otp', json={"email": email})
        self.assertEqual(req_res.status_code, 200)

        with get_db() as conn:
            reset_otp = conn.execute('SELECT otp FROM otp_codes WHERE email = ? AND purpose = "password_reset"', (email,)).fetchone()['otp']

        # 3. Verify OTP
        verify_res = self.client.post('/api/forgot-password/verify-otp', json={"email": email, "otp": reset_otp})
        self.assertEqual(verify_res.status_code, 200)

        # 4. Reset password
        reset_res = self.client.post('/api/forgot-password/reset-password', json={
            "email": email,
            "otp": reset_otp,
            "new_password": "NewSecurePassword456!"
        })
        self.assertEqual(reset_res.status_code, 200)

        # 5. Old password fails
        old_login = self.client.post('/api/login', json={"email": email, "password": "OldPassword123!"})
        self.assertEqual(old_login.status_code, 401)

        # 6. New password succeeds
        new_login = self.client.post('/api/login', json={"email": email, "password": "NewSecurePassword456!"})
        self.assertEqual(new_login.status_code, 200)

    def test_12_admin_role_resolution(self):
        """12. Verify logging in with SEEDIQ_ADMIN_EMAIL resolves to Admin role."""
        admin_email = "admin@seediq.ai"
        res = self.client.post('/api/login', json={
            "email": admin_email,
            "password": "admin123"
        })
        self.assertEqual(res.status_code, 200)
        user = json.loads(res.data)["user"]
        self.assertEqual(user["role"], "Admin")

    def test_13_researcher_role_resolution(self):
        """13. Verify logging in with SEEDIQ_RESEARCHER_EMAIL resolves to Researcher role."""
        res_email = "researcher@quantum.org"
        res = self.client.post('/api/login', json={
            "email": res_email,
            "password": "research123"
        })
        self.assertEqual(res.status_code, 200)
        user = json.loads(res.data)["user"]
        self.assertEqual(user["role"], "Researcher")

    def test_14_guest_login_and_restrictions(self):
        """14. Verify Guest login and access restrictions on admin endpoints."""
        res = self.client.post('/api/guest-login')
        self.assertEqual(res.status_code, 200)
        user = json.loads(res.data)["user"]
        self.assertEqual(user["role"], "Guest")
        self.assertTrue(user["isGuest"])

        # Attempt retraining as guest -> 403 Forbidden
        with self.client.session_transaction() as sess:
            sess['user_id'] = 999999
            sess['role'] = 'Guest'

        retrain_res = self.client.post('/api/retrain')
        self.assertEqual(retrain_res.status_code, 403)

    def test_15_logout_session_destruction(self):
        """15. Verify logout clears session and /api/me returns unauthenticated."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 10
            sess['role'] = 'Farmer'

        logout_res = self.client.post('/api/logout')
        self.assertEqual(logout_res.status_code, 200)

        me_res = self.client.get('/api/me')
        self.assertFalse(json.loads(me_res.data)["authenticated"])

    def test_16_purpose_separation_otp(self):
        """16. Verify registration OTP cannot be used for password reset."""
        email = "purpose_test@gmail.com"
        self.client.post('/api/register/request-otp', json={
            "name": "Purpose Test", "email": email, "password": "ValidPassword123!"
        })
        with get_db() as conn:
            reg_otp = conn.execute('SELECT otp FROM otp_codes WHERE email = ? AND purpose = "registration"', (email,)).fetchone()['otp']

        # Attempt to verify registration OTP on forgot password endpoint
        res = self.client.post('/api/forgot-password/verify-otp', json={"email": email, "otp": reg_otp})
        self.assertEqual(res.status_code, 400)

if __name__ == '__main__':
    unittest.main()
