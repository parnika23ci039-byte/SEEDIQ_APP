"""
SeedIQ Supabase Client & Persistence Bridge
Provides unified integration with Supabase Auth, PostgreSQL (PostgREST / Direct),
and Supabase Storage, with fallback and local legacy synchronization to SQLite.
"""

import os
import json
import logging
import requests
import datetime
from typing import Dict, Any, Optional, List, Tuple
from requests.adapters import HTTPAdapter

logger = logging.getLogger("seediq.supabase")

# ==============================================================================
# CONFIGURATION
# ==============================================================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://cqcdfvetexaqqcfogcds.supabase.co").strip().rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_ysdQ2JVY5i7PY-plyOmh3w_ORe-Wr1e").strip()
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY", "").strip()

DEFAULT_TIMEOUT = 8  # Fast 8-second timeout to prevent cloud gateway worker blocks


class SupabaseClient:
    def __init__(self, url: str = None, key: str = None, secret_key: str = None):
        self.url = (url or SUPABASE_URL).rstrip("/")
        self.key = key or SUPABASE_PUBLISHABLE_KEY
        self.secret_key = secret_key or SUPABASE_SECRET_KEY
        # High-performance persistent connection pooling
        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=25, max_retries=1)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self._verified_buckets = set()

        self.auth_headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json"
        }

    def _get_headers(self, token: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "apikey": self.key,
            "Content-Type": "application/json"
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif self.secret_key:
            headers["apikey"] = self.secret_key
            headers["Authorization"] = f"Bearer {self.secret_key}"
        else:
            headers["Authorization"] = f"Bearer {self.key}"
        return headers

    # --------------------------------------------------------------------------
    # 1. AUTHENTICATION (GoTrue)
    # --------------------------------------------------------------------------
    def sign_up(self, email: str, password: str, display_name: str = "", role: str = "Farmer") -> Tuple[bool, Dict[str, Any]]:
        """
        Creates a new user account in Supabase Auth and provisions a profile row.
        """
        endpoint = f"{self.url}/auth/v1/signup"
        payload = {
            "email": email.strip().lower(),
            "password": password,
            "data": {
                "display_name": display_name,
                "role": role
            }
        }
        try:
            resp = self.session.post(endpoint, json=payload, headers=self._get_headers(), timeout=DEFAULT_TIMEOUT)
            data = resp.json() if resp.text else {}
            if resp.status_code in [200, 201]:
                user_id = data.get("id") or (data.get("user") or {}).get("id")
                # Provision profile
                if user_id:
                    self.upsert_profile(user_id=user_id, email=email, display_name=display_name, role=role)
                return True, data
            else:
                msg = data.get("msg") or data.get("message") or data.get("error_description") or "Sign up failed"
                return False, {"error": msg, "statusCode": resp.status_code}
        except Exception as e:
            logger.error(f"Supabase sign_up exception: {e}")
            return False, {"error": str(e)}

    def sign_in(self, email: str, password: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Authenticates user with Supabase Auth via grant_type=password.
        """
        endpoint = f"{self.url}/auth/v1/token?grant_type=password"
        payload = {
            "email": email.strip().lower(),
            "password": password
        }
        try:
            resp = self.session.post(endpoint, json=payload, headers=self._get_headers(), timeout=DEFAULT_TIMEOUT)
            data = resp.json() if resp.text else {}
            if resp.status_code == 200 and "access_token" in data:
                user = data.get("user", {})
                user_id = user.get("id")
                profile = self.get_profile(user_id, token=data["access_token"])
                if not profile:
                    # Sync profile from user metadata if row missing
                    profile = self.upsert_profile(
                        user_id=user_id,
                        email=email,
                        display_name=user.get("user_metadata", {}).get("display_name", email.split("@")[0]),
                        role=user.get("user_metadata", {}).get("role", "Farmer")
                    )
                return True, {
                    "access_token": data["access_token"],
                    "refresh_token": data.get("refresh_token"),
                    "user": user,
                    "profile": profile
                }
            else:
                msg = data.get("msg") or data.get("message") or data.get("error_description") or "Invalid credentials"
                return False, {"error": msg, "statusCode": resp.status_code}
        except Exception as e:
            logger.error(f"Supabase sign_in exception: {e}")
            return False, {"error": str(e)}

    def update_password(self, access_token: str, new_password: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Updates user password using their authenticated session access token.
        """
        endpoint = f"{self.url}/auth/v1/user"
        payload = {"password": new_password}
        try:
            resp = self.session.put(endpoint, json=payload, headers=self._get_headers(token=access_token), timeout=DEFAULT_TIMEOUT)
            data = resp.json() if resp.text else {}
            if resp.status_code in [200, 204]:
                return True, data
            else:
                msg = data.get("msg") or data.get("message") or "Failed to update password"
                return False, {"error": msg}
        except Exception as e:
            logger.error(f"Supabase update_password exception: {e}")
            return False, {"error": str(e)}

    def recover_password(self, email: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Sends recovery email via Supabase Auth.
        """
        endpoint = f"{self.url}/auth/v1/recover"
        payload = {"email": email.strip().lower()}
        try:
            resp = self.session.post(endpoint, json=payload, headers=self._get_headers(), timeout=DEFAULT_TIMEOUT)
            data = resp.json() if resp.text else {}
            return (resp.status_code in [200, 204]), data
        except Exception as e:
            logger.error(f"Supabase recover_password exception: {e}")
            return False, {"error": str(e)}

    # --------------------------------------------------------------------------
    # 2. PROFILES & USER METADATA
    # --------------------------------------------------------------------------
    def get_profile(self, user_id: str, token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        endpoint = f"{self.url}/rest/v1/profiles?id=eq.{user_id}&select=*"
        try:
            resp = self.session.get(endpoint, headers=self._get_headers(token), timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                rows = resp.json()
                return rows[0] if rows else None
        except Exception as e:
            logger.warning(f"Failed to fetch profile from Supabase: {e}")
        return None

    def upsert_profile(self, user_id: str, email: str, display_name: str = "", role: str = "Farmer", token: Optional[str] = None) -> Dict[str, Any]:
        username = email.split("@")[0]
        profile_data = {
            "id": user_id,
            "email": email.strip().lower(),
            "username": username,
            "display_name": display_name or username,
            "role": role,
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        endpoint = f"{self.url}/rest/v1/profiles"
        headers = self._get_headers(token)
        headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        try:
            resp = self.session.post(endpoint, json=profile_data, headers=headers, timeout=DEFAULT_TIMEOUT)
            if resp.status_code in [200, 201]:
                res = resp.json()
                return res[0] if isinstance(res, list) and res else profile_data
        except Exception as e:
            logger.warning(f"Failed to upsert profile in Supabase: {e}")
        return profile_data

    # --------------------------------------------------------------------------
    # 3. SUPABASE STORAGE
    # --------------------------------------------------------------------------
    def ensure_bucket(self, bucket_name: str = "seediq-datasets", is_public: bool = False, token: Optional[str] = None) -> bool:
        """
        Checks if bucket exists; creates if missing. Caches verified buckets to avoid extra roundtrips.
        """
        if bucket_name in self._verified_buckets:
            return True

        endpoint = f"{self.url}/storage/v1/bucket"
        try:
            resp = self.session.get(endpoint, headers=self._get_headers(token), timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                buckets = resp.json()
                if any(b.get("id") == bucket_name or b.get("name") == bucket_name for b in buckets):
                    self._verified_buckets.add(bucket_name)
                    return True
            # Attempt to create
            create_resp = self.session.post(
                endpoint,
                json={"id": bucket_name, "name": bucket_name, "public": is_public},
                headers=self._get_headers(token),
                timeout=DEFAULT_TIMEOUT
            )
            if create_resp.status_code in [200, 201]:
                self._verified_buckets.add(bucket_name)
                return True
            return False
        except Exception as e:
            logger.error(f"ensure_bucket error: {e}")
            return False

    def upload_file(self, bucket_name: str, path_in_bucket: str, file_data: Any, content_type: str = "text/csv", token: Optional[str] = None) -> Tuple[bool, str]:
        """
        Uploads binary/text object to Supabase Storage.
        Supports in-memory bytes, open file streams, or file paths (streamed directly from disk for 4 GB scale).
        """
        clean_path = path_in_bucket.lstrip("/")
        endpoint = f"{self.url}/storage/v1/object/{bucket_name}/{clean_path}"
        headers = self._get_headers(token)
        headers["Content-Type"] = content_type
        headers["x-upsert"] = "true"

        MAX_STORAGE_UPLOAD_SIZE = 10 * 1024 * 1024
        if isinstance(file_data, str) and os.path.isfile(file_data):
            if os.path.getsize(file_data) > MAX_STORAGE_UPLOAD_SIZE:
                return False, "File size must be 10 MB or less."
        elif isinstance(file_data, (bytes, bytearray)):
            if len(file_data) > MAX_STORAGE_UPLOAD_SIZE:
                return False, "File size must be 10 MB or less."

        timeout_sec = 60
        try:
            if isinstance(file_data, str) and os.path.isfile(file_data):
                file_size = os.path.getsize(file_data)
                # Adaptive timeout: 60s base + 1s per 2MB
                timeout_sec = max(60, int(60 + (file_size / (2 * 1024 * 1024))))
                with open(file_data, 'rb') as stream:
                    resp = self.session.post(endpoint, data=stream, headers=headers, timeout=timeout_sec)
            else:
                resp = self.session.post(endpoint, data=file_data, headers=headers, timeout=timeout_sec)

            if resp.status_code in [200, 201]:
                return True, clean_path
            else:
                logger.error(f"Storage upload error ({resp.status_code}): {resp.text}")
                return False, resp.text
        except Exception as e:
            logger.error(f"Storage upload exception: {e}")
            return False, str(e)

    def download_file(self, bucket_name: str, path_in_bucket: str, token: Optional[str] = None) -> Optional[bytes]:
        clean_path = path_in_bucket.lstrip("/")
        endpoint = f"{self.url}/storage/v1/object/{bucket_name}/{clean_path}"
        try:
            resp = self.session.get(endpoint, headers=self._get_headers(token), timeout=12)
            if resp.status_code == 200:
                return resp.content
            return None
        except Exception as e:
            logger.error(f"Storage download exception: {e}")
            return None

    def create_signed_url(self, bucket_name: str, path_in_bucket: str, expires_in: int = 3600, token: Optional[str] = None) -> Optional[str]:
        clean_path = path_in_bucket.lstrip("/")
        endpoint = f"{self.url}/storage/v1/object/sign/{bucket_name}/{clean_path}"
        try:
            resp = self.session.post(endpoint, json={"expiresIn": expires_in}, headers=self._get_headers(token), timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                signed_path = data.get("signedURL") or data.get("signedUrl")
                if signed_path:
                    return f"{self.url}/storage/v1{signed_path}"
            return None
        except Exception as e:
            logger.error(f"create_signed_url exception: {e}")
            return None

    # --------------------------------------------------------------------------
    # 4. DATABASE REST CLIENT (PostgREST)
    # --------------------------------------------------------------------------
    def insert_row(self, table_name: str, row: Dict[str, Any], token: Optional[str] = None) -> Tuple[bool, Any]:
        endpoint = f"{self.url}/rest/v1/{table_name}"
        headers = self._get_headers(token)
        headers["Prefer"] = "return=representation"
        try:
            resp = self.session.post(endpoint, json=row, headers=headers, timeout=DEFAULT_TIMEOUT)
            if resp.status_code in [200, 201]:
                return True, resp.json()
            return False, resp.text
        except Exception as e:
            return False, str(e)

    def delete_rows(self, table_name: str, query_params: str, token: Optional[str] = None) -> Tuple[bool, int]:
        """
        Delete rows matching `query_params` (a PostgREST filter, e.g.
        "purpose=eq.registration"). Returns (ok, deleted_count).

        PostgREST refuses an unfiltered DELETE, which is a useful safety net:
        every call here must name what it removes.
        """
        endpoint = f"{self.url}/rest/v1/{table_name}?{query_params}"
        headers = self._get_headers(token)
        headers["Prefer"] = "return=representation"
        try:
            resp = self.session.delete(endpoint, headers=headers, timeout=DEFAULT_TIMEOUT)
            if resp.status_code in [200, 204]:
                try:
                    body = resp.json()
                    return True, len(body) if isinstance(body, list) else 0
                except Exception:
                    return True, 0
            logger.error(f"delete_rows {table_name} failed: {resp.status_code} {resp.text[:200]}")
            return False, 0
        except Exception as e:
            logger.error(f"delete_rows exception: {e}")
            return False, 0

    def select_rows(self, table_name: str, query_params: str = "select=*", token: Optional[str] = None) -> Tuple[bool, List[Dict[str, Any]]]:
        endpoint = f"{self.url}/rest/v1/{table_name}?{query_params}"
        headers = self._get_headers(token)
        try:
            resp = self.session.get(endpoint, headers=headers, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                return True, resp.json()
            return False, []
        except Exception as e:
            return False, []


# Global shared instance
supabase = SupabaseClient()
