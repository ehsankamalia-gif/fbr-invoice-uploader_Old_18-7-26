"""Desktop Staff/Admin account management: login, creation, and per-module
permissions. Entirely separate from the Django portal's authentication
system (django.contrib.auth, CustomerPortalAuth) - no shared code, no
shared tables. See app/db/models.py's StaffAccount/StaffPermission and
app/core/staff_modules.py for the data shapes this works with."""
import hashlib
import secrets
import datetime as dt
from typing import Any, Dict, List, Optional, Set

from app.db.session import SessionLocal
from app.db.models import StaffAccount, StaffPermission, Company, PasswordResetOTP, pk_now
from app.core.logger import logger
from app.services.auth_session import auth_session


def hash_password(password: str) -> str:
    """Self-contained PBKDF2-SHA256 hash - no new dependency, no Django
    compatibility needed (these accounts never cross into the portal)."""
    iterations = 390000
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algo, iterations_str, salt, digest_hex = password_hash.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iterations_str)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
        return secrets.compare_digest(expected, actual)
    except Exception:
        return False


def _account_to_dict(account: StaffAccount) -> Dict[str, Any]:
    return {
        "id": account.id,
        "mobile_number": account.mobile_number,
        "full_name": account.full_name,
        "role": account.role,
        "is_active": account.is_active,
        "created_at": account.created_at,
    }


def has_any_admin() -> bool:
    """True if an active Admin account already exists. Used at startup
    (app/qt_main.py) to decide whether the normal login screen is even
    reachable - with zero admins in the whole database, it would be a
    guaranteed dead end, so first-run setup is shown instead."""
    db = SessionLocal()
    try:
        exists = (
            db.query(StaffAccount.id)
            .filter_by(role=StaffAccount.ADMIN, is_active=True)
            .first()
        )
        return exists is not None
    finally:
        db.close()


def create_first_admin(*, mobile_number: str, password: str, full_name: str) -> Dict[str, Any]:
    """Self-service bootstrap: only allowed while there's no active Admin
    yet (checked again here, not just by the caller, so two people can't
    race to create two "first" admins)."""
    if has_any_admin():
        raise ValueError("An Admin account already exists. Ask your Admin to create your account instead.")

    db = SessionLocal()
    try:
        existing = db.query(StaffAccount).filter_by(mobile_number=mobile_number).first()
        if existing:
            raise ValueError("This mobile number is already registered to an account.")

        account = StaffAccount(
            mobile_number=mobile_number,
            password_hash=hash_password(password),
            full_name=full_name,
            role=StaffAccount.ADMIN,
            is_active=True,
        )
        db.add(account)
        db.commit()
        db.refresh(account)
        logger.info(f"Created first Admin account (mobile={mobile_number}).")
        return _account_to_dict(account)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _build_login_result(db, account: StaffAccount) -> Dict[str, Any]:
    permissions: Set[str] = set()
    if account.role != StaffAccount.ADMIN:
        rows = db.query(StaffPermission.module_code).filter_by(staff_account_id=account.id).all()
        permissions = {r[0] for r in rows}
    return {
        "staff_id": account.id,
        "role": account.role,
        "full_name": account.full_name,
        "mobile_number": account.mobile_number,
        "permissions": permissions,
    }


def authenticate(mobile_number: str, password: str) -> Optional[Dict[str, Any]]:
    db = SessionLocal()
    try:
        account = db.query(StaffAccount).filter_by(mobile_number=mobile_number.strip()).first()
        if not account or not account.is_active:
            return None
        if not verify_password(password, account.password_hash):
            return None
        return _build_login_result(db, account)
    finally:
        db.close()


def get_login_result_for_staff(staff_id: int) -> Optional[Dict[str, Any]]:
    db = SessionLocal()
    try:
        account = db.query(StaffAccount).filter_by(id=staff_id).first()
        if not account or not account.is_active:
            return None
        return _build_login_result(db, account)
    finally:
        db.close()


def list_staff() -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        accounts = db.query(StaffAccount).order_by(StaffAccount.full_name).all()
        return [_account_to_dict(a) for a in accounts]
    finally:
        db.close()


def get_permissions_for_staff(staff_id: int) -> Set[str]:
    db = SessionLocal()
    try:
        rows = db.query(StaffPermission.module_code).filter_by(staff_account_id=staff_id).all()
        return {r[0] for r in rows}
    finally:
        db.close()


def create_staff_account(*, mobile_number: str, password: str,
                          full_name: str, permissions: Set[str], created_by_id: int) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        existing = db.query(StaffAccount).filter_by(mobile_number=mobile_number.strip()).first()
        if existing:
            raise ValueError("This mobile number is already registered to an account.")

        account = StaffAccount(
            mobile_number=mobile_number.strip(),
            password_hash=hash_password(password),
            full_name=full_name.strip(),
            role=StaffAccount.STAFF,
            is_active=True,
            created_by_id=created_by_id,
        )
        db.add(account)
        db.flush()

        for module_code in permissions:
            db.add(StaffPermission(staff_account_id=account.id, module_code=module_code))

        db.commit()
        db.refresh(account)
        logger.info(f"Admin (id={created_by_id}) created Staff account '{full_name}'.")
        return _account_to_dict(account)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def set_staff_permissions(staff_id: int, permissions: Set[str]) -> None:
    db = SessionLocal()
    try:
        db.query(StaffPermission).filter_by(staff_account_id=staff_id).delete()
        for module_code in permissions:
            db.add(StaffPermission(staff_account_id=staff_id, module_code=module_code))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def set_staff_active(staff_id: int, is_active: bool) -> None:
    db = SessionLocal()
    try:
        account = db.query(StaffAccount).filter_by(id=staff_id).first()
        if not account:
            raise ValueError("Staff account not found.")
        if account.role == StaffAccount.ADMIN and not is_active:
            remaining = (
                db.query(StaffAccount.id)
                .filter_by(role=StaffAccount.ADMIN, is_active=True)
                .filter(StaffAccount.id != staff_id)
                .first()
            )
            if not remaining:
                raise ValueError("Cannot deactivate the only Admin account.")
        account.is_active = is_active
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


MIN_PASSWORD_LENGTH = 6


def change_password(staff_id: int, new_password: str) -> None:
    """Admin-initiated reset of someone else's (forgotten) password - does
    not require knowing the current password. For a user changing their own
    known password, use change_own_password() instead, which does.

    Authorization is enforced HERE, not just by what the UI shows: the
    caller must be the currently logged-in session (read from auth_session,
    never trusted from a parameter, so nothing upstream of this call can
    spoof who's "acting") and must be an Admin. A Staff account calling
    this at all is rejected regardless of what dialog or code path reached
    this function."""
    db = SessionLocal()
    try:
        acting_staff_id = auth_session.current_staff_id()
        if acting_staff_id is None:
            raise ValueError("You must be logged in to reset a password.")
        if not auth_session.is_admin():
            raise ValueError("Only an Admin can reset another account's password.")

        if len(new_password or "") < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")

        account = db.query(StaffAccount).filter_by(id=staff_id).first()
        if not account:
            raise ValueError("Staff account not found.")

        account.password_hash = hash_password(new_password)
        db.commit()
        logger.info(f"Password reset for staff_id={staff_id} by admin staff_id={acting_staff_id}.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def change_own_password(current_password: str, new_password: str) -> None:
    """Self-service password change for whoever is currently logged in.
    Requires proving knowledge of the current password - the security
    property that distinguishes this from an Admin's change_password()
    reset of someone else's account, where not knowing the old password is
    the whole point.

    Deliberately takes no staff_id parameter - the account being changed is
    always auth_session's own current_staff_id(), read here rather than
    accepted from the caller, so this function can never be used (by a UI
    bug or a direct call) to change anyone else's password."""
    db = SessionLocal()
    try:
        staff_id = auth_session.current_staff_id()
        if staff_id is None:
            raise ValueError("You must be logged in to change your password.")

        account = db.query(StaffAccount).filter_by(id=staff_id).first()
        if not account:
            raise ValueError("Account not found.")
        if not verify_password(current_password, account.password_hash):
            raise ValueError("Current password is incorrect.")
        if len(new_password or "") < MIN_PASSWORD_LENGTH:
            raise ValueError(f"New password must be at least {MIN_PASSWORD_LENGTH} characters.")
        if new_password == current_password:
            raise ValueError("New password must be different from the current password.")
        account.password_hash = hash_password(new_password)
        db.commit()
        logger.info(f"Password changed by staff_id={staff_id} (self-service).")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# --- Forgot Password (OTP) ---------------------------------------------
#
# For whoever cannot log in at all because they forgot their password.
# Three steps, each its own function, mirroring the DB's verified_at/
# consumed_at lifecycle on PasswordResetOTP:
#   1. request_password_reset_otp(mobile)      - send a code to that phone
#   2. verify_password_reset_otp(mobile, code) - prove the phone is theirs
#   3. reset_password_with_verified_otp(...)   - spend that proof once

OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_VERIFIED_WINDOW_MINUTES = 10


def _generate_otp_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))


def _send_otp_sms(mobile_number: str, message: str) -> tuple[bool, str]:
    """Sends one SMS immediately (not queued - the user is actively waiting
    on the login screen)."""
    from app.db.models import SMSConfiguration
    from app.services.sms_service import sms_service, normalize_pk_mobile

    db = SessionLocal()
    try:
        config = db.query(SMSConfiguration).filter_by(is_enabled=True).first()
        if not config:
            return False, "SMS gateway is not configured. Contact your administrator."

        phone = normalize_pk_mobile(mobile_number)
        if (config.gateway_type or "").upper() == "CLOUD" and config.api_url:
            return sms_service.send_sms_via_cloud(
                (config.api_url or "").strip(), phone, message,
                (config.api_key or None), (config.cloud_username or None), (config.cloud_password or None),
            )
        elif config.gateway_ip:
            return sms_service.send_sms_via_wifi(
                (config.gateway_ip or "").strip(), (config.gateway_port or "8080"), phone, message,
                (config.api_key or None), (config.gateway_username or None), (config.gateway_password or None),
                use_https=bool(getattr(config, "use_https", False)),
            )
        return False, "SMS Gateway not configured properly."
    finally:
        db.close()


def request_password_reset_otp(mobile_number: str) -> Dict[str, Any]:
    """Step 1: starts a Forgot Password flow. Finds the active account
    matching this mobile number, generates an OTP, and sends it via SMS to
    that exact number."""
    mobile = (mobile_number or "").strip()
    if not mobile:
        raise ValueError("Enter your registered mobile number.")

    db = SessionLocal()
    try:
        account = db.query(StaffAccount).filter_by(mobile_number=mobile, is_active=True).first()
        if not account:
            raise ValueError("No account was found for this mobile number.")

        recent = (
            db.query(PasswordResetOTP)
            .filter_by(mobile_number=mobile)
            .order_by(PasswordResetOTP.created_at.desc())
            .first()
        )
        if recent:
            elapsed = (pk_now() - recent.created_at).total_seconds()
            if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
                wait = int(OTP_RESEND_COOLDOWN_SECONDS - elapsed)
                raise ValueError(f"Please wait {wait} seconds before requesting another code.")

        code = _generate_otp_code()
        otp = PasswordResetOTP(
            mobile_number=mobile,
            otp_hash=hash_password(code),
            expires_at=pk_now() + dt.timedelta(minutes=OTP_EXPIRY_MINUTES),
        )
        db.add(otp)
        db.commit()

        template = "Your password reset code is {code}. It expires in " + str(OTP_EXPIRY_MINUTES) + " minutes. Do not share this code."
        sent, info = _send_otp_sms(mobile, template.format(code=code))
        if not sent:
            raise ValueError(f"Could not send the verification code: {info}")

        logger.info(f"Password reset OTP sent for mobile={mobile}.")
        return {"mobile_number": mobile}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def verify_password_reset_otp(mobile_number: str, code: str) -> Dict[str, Any]:
    """Step 2: verifies the code and, on success, returns the account's info."""
    mobile = (mobile_number or "").strip()
    code = (code or "").strip()

    db = SessionLocal()
    try:
        otp = (
            db.query(PasswordResetOTP)
            .filter_by(mobile_number=mobile, verified_at=None, consumed_at=None)
            .order_by(PasswordResetOTP.created_at.desc())
            .first()
        )
        if not otp:
            raise ValueError("No pending verification code for this number. Request a new one.")
        if otp.expires_at < pk_now():
            raise ValueError("This code has expired. Request a new one.")
        if (otp.attempts or 0) >= OTP_MAX_ATTEMPTS:
            raise ValueError("Too many incorrect attempts. Request a new code.")

        if not verify_password(code, otp.otp_hash):
            otp.attempts = (otp.attempts or 0) + 1
            db.commit()
            remaining = OTP_MAX_ATTEMPTS - otp.attempts
            if remaining > 0:
                raise ValueError(f"Incorrect code. {remaining} attempt(s) remaining.")
            raise ValueError("Incorrect code. Too many attempts - request a new code.")

        otp.verified_at = pk_now()
        db.commit()

        account = db.query(StaffAccount).filter_by(mobile_number=mobile, is_active=True).first()
        if not account:
            raise ValueError("No active account found for this mobile number.")

        logger.info(f"Password reset OTP verified for mobile={mobile}.")
        return {
            "staff_id": account.id,
            "full_name": account.full_name,
            "role": account.role,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def reset_password_with_verified_otp(mobile_number: str, new_password: str) -> None:
    """Step 3: completes a Forgot Password reset. Requires a recently
    verified (not yet consumed) OTP for this exact mobile number."""
    mobile = (mobile_number or "").strip()

    db = SessionLocal()
    try:
        otp = (
            db.query(PasswordResetOTP)
            .filter(PasswordResetOTP.mobile_number == mobile)
            .filter(PasswordResetOTP.verified_at.isnot(None))
            .filter(PasswordResetOTP.consumed_at.is_(None))
            .order_by(PasswordResetOTP.verified_at.desc())
            .first()
        )
        if not otp:
            raise ValueError("Please verify your mobile number with a code first.")
        if otp.verified_at < pk_now() - dt.timedelta(minutes=OTP_VERIFIED_WINDOW_MINUTES):
            raise ValueError("Your verification has expired. Please request a new code.")

        account = db.query(StaffAccount).filter_by(mobile_number=mobile, is_active=True).first()
        if not account:
            raise ValueError("Account not found for this mobile number.")

        if len(new_password or "") < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")

        account.password_hash = hash_password(new_password)
        otp.consumed_at = pk_now()
        db.commit()
        logger.info(f"Password reset via OTP for staff_id={account.id} (mobile={mobile}).")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
