"""Unit tests cho app.core.security — JWT + bcrypt utilities."""

import time
from unittest.mock import patch

import jwt
import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


# ── Password hashing ──────────────────────────────────────────────────────────


class TestHashPassword:
    def test_hash_password_returns_string(self):
        hashed = hash_password("my_secret_password")
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_hash_password_different_each_time(self):
        """Mỗi lần hash cùng password phải cho kết quả khác nhau (do salt)."""
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2

    def test_hash_password_unicode(self):
        """Hash password với ký tự Unicode."""
        hashed = hash_password("mật_khẩu_tiếng_việt_🔒")
        assert isinstance(hashed, str)
        assert verify_password("mật_khẩu_tiếng_việt_🔒", hashed)

    def test_hash_password_empty_string(self):
        """Hash empty string vẫn hoạt động."""
        hashed = hash_password("")
        assert isinstance(hashed, str)
        assert verify_password("", hashed)

    def test_hash_password_long_password(self):
        """Password dài (>72 bytes) bị truncate tự động."""
        long_password = "a" * 200
        hashed = hash_password(long_password)
        assert verify_password(long_password, hashed)

    def test_hash_password_special_characters(self):
        """Password với ký tự đặc biệt."""
        password = "p@$$w0rd!#%^&*()_+-=[]{}|;':\",./<>?"
        hashed = hash_password(password)
        assert verify_password(password, hashed)


class TestVerifyPassword:
    def test_verify_password_correct(self):
        hashed = hash_password("correct_password")
        assert verify_password("correct_password", hashed) is True

    def test_verify_password_incorrect(self):
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_verify_password_case_sensitive(self):
        hashed = hash_password("Password")
        assert verify_password("password", hashed) is False
        assert verify_password("PASSWORD", hashed) is False

    def test_verify_password_empty(self):
        hashed = hash_password("")
        assert verify_password("", hashed) is True
        assert verify_password("not_empty", hashed) is False

    def test_verify_password_unicode(self):
        hashed = hash_password("tiếng_việt")
        assert verify_password("tiếng_việt", hashed) is True
        assert verify_password("tiếng Việt", hashed) is False


# ── Access token ──────────────────────────────────────────────────────────────


class TestCreateAccessToken:
    @patch("app.core.security.get_settings")
    def test_create_access_token_returns_string(self, mock_settings):
        mock_settings.return_value.jwt_secret_key = "test-secret-key-32chars!"
        mock_settings.return_value.jwt_algorithm = "HS256"
        mock_settings.return_value.jwt_access_token_expire_minutes = 15

        token = create_access_token("user-123")
        assert isinstance(token, str)
        assert len(token) > 0

    @patch("app.core.security.get_settings")
    def test_access_token_contains_user_id(self, mock_settings):
        mock_settings.return_value.jwt_secret_key = "test-secret-key-32chars!"
        mock_settings.return_value.jwt_algorithm = "HS256"
        mock_settings.return_value.jwt_access_token_expire_minutes = 15

        token = create_access_token("user-abc")
        decoded = jwt.decode(token, "test-secret-key-32chars!", algorithms=["HS256"])
        assert decoded["sub"] == "user-abc"
        assert decoded["type"] == "access"

    @patch("app.core.security.get_settings")
    def test_access_token_has_expiry(self, mock_settings):
        mock_settings.return_value.jwt_secret_key = "test-secret-key-32chars!"
        mock_settings.return_value.jwt_algorithm = "HS256"
        mock_settings.return_value.jwt_access_token_expire_minutes = 30

        token = create_access_token("user-123")
        decoded = jwt.decode(token, "test-secret-key-32chars!", algorithms=["HS256"])
        assert "exp" in decoded
        # exp should be in the future (within ~30 minutes)
        assert decoded["exp"] > time.time()

    @patch("app.core.security.get_settings")
    def test_access_token_expiry_matches_config(self, mock_settings):
        mock_settings.return_value.jwt_secret_key = "test-secret-key-32chars!"
        mock_settings.return_value.jwt_algorithm = "HS256"
        mock_settings.return_value.jwt_access_token_expire_minutes = 60

        token = create_access_token("user-123")
        decoded = jwt.decode(token, "test-secret-key-32chars!", algorithms=["HS256"])
        now = time.time()
        # Should expire within ~60 minutes (allow 5 second tolerance)
        assert decoded["exp"] - now < 3660
        assert decoded["exp"] - now > 3500


# ── Refresh token ─────────────────────────────────────────────────────────────


class TestCreateRefreshToken:
    @patch("app.core.security.get_settings")
    def test_create_refresh_token_returns_string(self, mock_settings):
        mock_settings.return_value.jwt_secret_key = "test-secret-key-32chars!"
        mock_settings.return_value.jwt_algorithm = "HS256"
        mock_settings.return_value.jwt_refresh_token_expire_days = 7

        token = create_refresh_token("user-123")
        assert isinstance(token, str)
        assert len(token) > 0

    @patch("app.core.security.get_settings")
    def test_refresh_token_contains_user_id(self, mock_settings):
        mock_settings.return_value.jwt_secret_key = "test-secret-key-32chars!"
        mock_settings.return_value.jwt_algorithm = "HS256"
        mock_settings.return_value.jwt_refresh_token_expire_days = 7

        token = create_refresh_token("user-xyz")
        decoded = jwt.decode(token, "test-secret-key-32chars!", algorithms=["HS256"])
        assert decoded["sub"] == "user-xyz"
        assert decoded["type"] == "refresh"

    @patch("app.core.security.get_settings")
    def test_refresh_token_has_unique_jti(self, mock_settings):
        """Mỗi refresh token phải có jti duy nhất (cho token rotation)."""
        mock_settings.return_value.jwt_secret_key = "test-secret-key-32chars!"
        mock_settings.return_value.jwt_algorithm = "HS256"
        mock_settings.return_value.jwt_refresh_token_expire_days = 7

        t1 = create_refresh_token("user-123")
        t2 = create_refresh_token("user-123")
        d1 = jwt.decode(t1, "test-secret-key-32chars!", algorithms=["HS256"])
        d2 = jwt.decode(t2, "test-secret-key-32chars!", algorithms=["HS256"])
        assert d1["jti"] != d2["jti"], "Mỗi refresh token phải có jti khác nhau"

    @patch("app.core.security.get_settings")
    def test_refresh_token_jti_is_hex_string(self, mock_settings):
        mock_settings.return_value.jwt_secret_key = "test-secret-key-32chars!"
        mock_settings.return_value.jwt_algorithm = "HS256"
        mock_settings.return_value.jwt_refresh_token_expire_days = 7

        token = create_refresh_token("user-123")
        decoded = jwt.decode(token, "test-secret-key-32chars!", algorithms=["HS256"])
        jti = decoded["jti"]
        assert isinstance(jti, str)
        # jti should be a 32-char hex string (secrets.token_hex(16))
        assert len(jti) == 32
        int(jti, 16)  # Should not raise — valid hex

    @patch("app.core.security.get_settings")
    def test_refresh_token_has_expiry(self, mock_settings):
        mock_settings.return_value.jwt_secret_key = "test-secret-key-32chars!"
        mock_settings.return_value.jwt_algorithm = "HS256"
        mock_settings.return_value.jwt_refresh_token_expire_days = 7

        token = create_refresh_token("user-123")
        decoded = jwt.decode(token, "test-secret-key-32chars!", algorithms=["HS256"])
        assert "exp" in decoded
        now = time.time()
        # Should expire within ~7 days
        assert decoded["exp"] - now < 7 * 24 * 3600 + 10
        assert decoded["exp"] - now > 6 * 24 * 3600


# ── Decode token ──────────────────────────────────────────────────────────────


class TestDecodeToken:
    @patch("app.core.security.get_settings")
    def test_decode_valid_access_token(self, mock_settings):
        mock_settings.return_value.jwt_secret_key = "test-secret-key-32chars!"
        mock_settings.return_value.jwt_algorithm = "HS256"
        mock_settings.return_value.jwt_access_token_expire_minutes = 15

        token = create_access_token("user-123")
        decoded = decode_token(token)
        assert decoded["sub"] == "user-123"
        assert decoded["type"] == "access"

    @patch("app.core.security.get_settings")
    def test_decode_valid_refresh_token(self, mock_settings):
        mock_settings.return_value.jwt_secret_key = "test-secret-key-32chars!"
        mock_settings.return_value.jwt_algorithm = "HS256"
        mock_settings.return_value.jwt_refresh_token_expire_days = 7

        token = create_refresh_token("user-456")
        decoded = decode_token(token)
        assert decoded["sub"] == "user-456"
        assert decoded["type"] == "refresh"
        assert "jti" in decoded

    @patch("app.core.security.get_settings")
    def test_decode_wrong_secret_raises(self, mock_settings):
        mock_settings.return_value.jwt_secret_key = "correct-secret-32chars!!!"
        mock_settings.return_value.jwt_algorithm = "HS256"
        mock_settings.return_value.jwt_access_token_expire_minutes = 15

        token = create_access_token("user-123")

        # Decode with wrong secret should raise
        with patch("app.core.security.get_settings") as mock_wrong:
            mock_wrong.return_value.jwt_secret_key = "wrong-secret-32chars!!!!"
            mock_wrong.return_value.jwt_algorithm = "HS256"
            with pytest.raises(jwt.InvalidSignatureError):
                decode_token(token)

    @patch("app.core.security.get_settings")
    def test_decode_expired_token_raises(self, mock_settings):
        mock_settings.return_value.jwt_secret_key = "test-secret-key-32chars!"
        mock_settings.return_value.jwt_algorithm = "HS256"
        mock_settings.return_value.jwt_access_token_expire_minutes = 15

        # Create an already-expired token manually
        import datetime

        expired_payload = {
            "sub": "user-123",
            "type": "access",
            "exp": datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(seconds=10),
        }
        token = jwt.encode(
            expired_payload,
            "test-secret-key-32chars!",
            algorithm="HS256",
        )

        with pytest.raises(jwt.ExpiredSignatureError):
            decode_token(token)

    @patch("app.core.security.get_settings")
    def test_decode_malformed_token_raises(self, mock_settings):
        mock_settings.return_value.jwt_secret_key = "test-secret-key-32chars!"
        mock_settings.return_value.jwt_algorithm = "HS256"

        with pytest.raises(jwt.DecodeError):
            decode_token("not.a.valid.token")

    @patch("app.core.security.get_settings")
    def test_decode_empty_token_raises(self, mock_settings):
        mock_settings.return_value.jwt_secret_key = "test-secret-key-32chars!"
        mock_settings.return_value.jwt_algorithm = "HS256"

        with pytest.raises(jwt.DecodeError):
            decode_token("")


# ── Integration: hash → verify roundtrip ──────────────────────────────────────


class TestPasswordRoundtrip:
    def test_hash_and_verify_roundtrip(self):
        """Full roundtrip: hash → verify."""
        passwords = [
            "simple",
            "p@$$w0rd",
            "tiếng_việt_🔒",
            "a" * 100,
            "",
            " spaces around ",
        ]
        for pwd in passwords:
            hashed = hash_password(pwd)
            assert verify_password(pwd, hashed), f"Failed for password: {pwd!r}"
            assert not verify_password(pwd + "x", hashed)


# ── _to_bytes helper ──────────────────────────────────────────────────────────


class TestToBytes:
    def test_to_bytes_encodes_utf8(self):
        from app.core.security import _to_bytes

        result = _to_bytes("hello")
        assert result == b"hello"

    def test_to_bytes_truncates_long_password(self):
        from app.core.security import _to_bytes, _BCRYPT_MAX_BYTES

        long_pwd = "a" * 200
        result = _to_bytes(long_pwd)
        assert len(result) == _BCRYPT_MAX_BYTES
        assert result == b"a" * _BCRYPT_MAX_BYTES

    def test_to_bytes_unicode(self):
        from app.core.security import _to_bytes

        result = _to_bytes("xin_chào")
        assert result == "xin_chào".encode("utf-8")
