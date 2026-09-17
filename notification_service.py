"""
Late Arrival Notification Service
Handles validation of mobile numbers, SMS message generation, and dispatching
late arrival alerts to students and parents without blocking the recognition loop.
"""

import os
import re
import sys
import json
import logging
import threading
from datetime import datetime
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

logger = logging.getLogger("notification_service")


def get_config():
    """Load current notification configuration from environment."""
    sms_enabled_str = os.getenv("SMS_ENABLED", "true").strip().lower()
    sms_enabled = sms_enabled_str in ("true", "1", "yes", "on")

    provider = os.getenv("SMS_PROVIDER", "mock").strip().lower()
    api_key = os.getenv("SMS_API_KEY", "").strip()
    sender_id = os.getenv("SMS_SENDER_ID", "").strip()
    api_url = os.getenv("SMS_API_URL", "").strip()

    twilio_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    twilio_from = os.getenv("TWILIO_FROM_NUMBER", "").strip()

    return {
        "enabled": sms_enabled,
        "provider": provider,
        "api_key": api_key,
        "sender_id": sender_id,
        "api_url": api_url,
        "twilio_sid": twilio_sid,
        "twilio_token": twilio_token,
        "twilio_from": twilio_from,
    }


def normalize_indian_mobile(mobile: str) -> tuple[bool, str]:
    """
    Validates and normalizes an Indian mobile number.
    
    Accepts:
      - 10 digits starting with 6, 7, 8, 9
      - Numbers with leading '+91', '91', or '0'
      - Numbers with hyphens, spaces, or parentheses
      
    Returns:
      (is_valid, normalized_10_digit_string_or_empty)
    """
    if not mobile:
        return False, ""

    # Remove all non-digits except a leading plus
    cleaned = str(mobile).strip()
    digits = re.sub(r"\D", "", cleaned)

    # Handle prefixes: +91 or 91
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    # Must be exactly 10 digits and start with 6, 7, 8, or 9
    if len(digits) == 10 and digits[0] in "6789":
        return True, digits

    return False, digits


def format_attendance_time(dt: datetime = None) -> str:
    """Format time into 12-hour format without leading zero, e.g. '8:47 AM'."""
    if dt is None:
        dt = datetime.now()
    # Format with %I (01-12), %M (00-59), %p (AM/PM)
    formatted = dt.strftime("%I:%M %p")
    return formatted.lstrip("0")


def format_student_message(
    name: str,
    student_id: str,
    year: str = "",
    department: str = "",
    dt: datetime = None
) -> str:
    """Format professional student alert message."""
    if dt is None:
        dt = datetime.now()
    date_str = dt.strftime("%d/%m/%Y")

    parts = []
    if year and str(year).strip() != "N/A":
        parts.append(str(year).strip())
    if department and str(department).strip() != "N/A":
        parts.append(str(department).strip())

    academic_info = " - ".join(parts) if parts else ""
    academic_prefix = f" of {academic_info}" if academic_info else ""

    return (
        f"Dear Student, {name} ({student_id}){academic_prefix} "
        f"was late to college today ({date_str}). "
        f"St.Joseph's College of Arts & Science (Autonomous) - Cuddalore."
    )


def format_parent_message(
    name: str,
    student_id: str,
    year: str = "",
    department: str = "",
    dt: datetime = None
) -> str:
    """Format professional parent alert message matching St. Joseph's College format."""
    if dt is None:
        dt = datetime.now()
    date_str = dt.strftime("%d/%m/%Y")

    parts = []
    if year and str(year).strip() != "N/A":
        parts.append(str(year).strip())
    if department and str(department).strip() != "N/A":
        parts.append(str(department).strip())

    academic_info = " - ".join(parts) if parts else ""
    academic_prefix = f" of {academic_info}" if academic_info else ""

    return (
        f"Dear Parent, Your Son/Daughter, {name} ({student_id}){academic_prefix} "
        f"was late to college today ({date_str}). "
        f"St.Joseph's College of Arts & Science (Autonomous) - Cuddalore."
    )


class SMSProvider:
    """Base SMS provider interface."""
    def send(self, to_number: str, message: str, recipient_type: str = "recipient") -> dict:
        raise NotImplementedError


class MockSMSProvider(SMSProvider):
    """Mock SMS provider that logs messages without sending external HTTP requests."""
    def send(self, to_number: str, message: str, recipient_type: str = "recipient") -> dict:
        print(f"[SMS MOCK] Dispatched to {recipient_type} ({to_number}): {message}", flush=True)
        return {
            "success": True,
            "provider": "mock",
            "to": to_number,
            "message": message,
        }


class GenericHttpSMSProvider(SMSProvider):
    """Sends SMS via a generic HTTP POST webhook endpoint."""
    def __init__(self, api_url: str, api_key: str = "", sender_id: str = ""):
        self.api_url = api_url
        self.api_key = api_key
        self.sender_id = sender_id

    def send(self, to_number: str, message: str, recipient_type: str = "recipient") -> dict:
        import requests
        if not self.api_url:
            raise ValueError("Generic SMS provider configured but SMS_API_URL is missing")

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "to": to_number,
            "message": message,
            "sender_id": self.sender_id,
            "recipient_type": recipient_type,
        }

        resp = requests.post(self.api_url, json=payload, headers=headers, timeout=6)
        resp.raise_for_status()
        return {"success": True, "provider": "generic", "status_code": resp.status_code}


class AndroidSMSGatewayProvider(SMSProvider):
    """Sends SMS via a local Android phone running an SMS Gateway server app."""
    def __init__(self, api_url: str, api_key: str = ""):
        self.api_url = (api_url or "").strip()
        self.api_key = (api_key or "").strip()

    def send(self, to_number: str, message: str, recipient_type: str = "recipient") -> dict:
        import requests
        if not self.api_url:
            raise ValueError("Android SMS Gateway provider configured but SMS_API_URL is missing in .env")

        url = self.api_url
        if not url.startswith(("http://", "https://")):
            url = f"http://{url}"

        # If base URL given without endpoint path, append /message
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if not parsed.path or parsed.path == "/":
            url = url.rstrip("/") + "/message"

        headers = {"Content-Type": "application/json"}
        auth = None

        if self.api_key:
            if ":" in self.api_key:
                user, pwd = self.api_key.split(":", 1)
                auth = (user, pwd)
            else:
                headers["Authorization"] = f"Bearer {self.api_key}"
                headers["X-API-Key"] = self.api_key

        phone = to_number if to_number.startswith("+") else f"+91{to_number}"

        payload = {
            "phone": phone,
            "to": phone,
            "number": phone,
            "phoneNumbers": [phone],
            "numbers": [phone],
            "message": message,
            "text": message,
        }

        resp = requests.post(url, json=payload, headers=headers, auth=auth, timeout=12)
        if resp.status_code not in (200, 201, 202):
            raise ValueError(f"Android SMS Gateway Error ({resp.status_code}): {resp.text or 'Unauthorized / Bad Request'}")
        
        return {"success": True, "provider": "android_gateway", "status_code": resp.status_code}


class Fast2SMSProvider(SMSProvider):
    """Fast2SMS API provider for Indian mobile numbers."""
    def __init__(self, api_key: str, sender_id: str = ""):
        self.api_key = api_key
        self.sender_id = sender_id

    def send(self, to_number: str, message: str, recipient_type: str = "recipient") -> dict:
        import requests
        if not self.api_key:
            raise ValueError("Fast2SMS provider configured but SMS_API_KEY is missing")

        url = "https://www.fast2sms.com/dev/bulkV2"
        headers = {
            "authorization": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "route": "q",
            "message": message,
            "language": "english",
            "numbers": to_number,
        }
        resp = requests.post(url, data=data, headers=headers, timeout=8)
        
        try:
            res_json = resp.json()
        except Exception:
            res_json = {}

        if resp.status_code != 200 or not res_json.get("return", True):
            msg = res_json.get("message") or (res_json.get("message", [None])[0] if isinstance(res_json.get("message"), list) else None) or resp.text
            raise ValueError(f"Fast2SMS API Error: {msg}")

        return {"success": True, "provider": "fast2sms", "response": res_json}


class TwilioSMSProvider(SMSProvider):
    """Twilio SMS provider."""
    def __init__(self, sid: str, token: str, from_number: str):
        self.sid = sid
        self.token = token
        self.from_number = from_number

    def send(self, to_number: str, message: str, recipient_type: str = "recipient") -> dict:
        import requests
        if not (self.sid and self.token and self.from_number):
            raise ValueError("Twilio provider requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM_NUMBER")

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json"
        # Indian numbers in international E.164 format for Twilio
        to_e164 = f"+91{to_number}" if not to_number.startswith("+") else to_number
        data = {
            "To": to_e164,
            "From": self.from_number,
            "Body": message,
        }
        resp = requests.post(url, data=data, auth=(self.sid, self.token), timeout=5)
        resp.raise_for_status()
        return {"success": True, "provider": "twilio", "sid": resp.json().get("sid")}


def get_sms_provider(config: dict = None) -> SMSProvider:
    """Factory to instantiate the configured SMS provider."""
    if config is None:
        config = get_config()

    provider_name = config.get("provider", "mock")

    if provider_name in ("android", "android_gateway", "android_sms"):
        return AndroidSMSGatewayProvider(
            config.get("api_url"),
            config.get("api_key"),
        )
    elif provider_name == "fast2sms":
        return Fast2SMSProvider(config.get("api_key"), config.get("sender_id"))
    elif provider_name == "twilio":
        return TwilioSMSProvider(
            config.get("twilio_sid"),
            config.get("twilio_token"),
            config.get("twilio_from"),
        )
    elif provider_name == "generic":
        return GenericHttpSMSProvider(
            config.get("api_url"),
            config.get("api_key"),
            config.get("sender_id"),
        )
    else:
        return MockSMSProvider()


def dispatch_single_sms(to_number: str, message: str, recipient_type: str, provider: SMSProvider) -> dict:
    """Dispatch SMS to a single recipient with safety and error handling."""
    is_valid, normalized = normalize_indian_mobile(to_number)
    if not is_valid:
        print(f"[SMS ALERT] Skipped {recipient_type}: Missing or invalid mobile number '{to_number}'", flush=True)
        return {"success": False, "reason": "invalid_number", "number": to_number}

    try:
        result = provider.send(normalized, message, recipient_type=recipient_type)
        return {"success": True, "result": result}
    except Exception as exc:
        print(f"[SMS ALERT ERROR] Failed to send SMS to {recipient_type} ({normalized}): {exc}", flush=True)
        return {"success": False, "error": str(exc), "number": normalized}


def _async_send_late_alerts(
    student_id: str,
    name: str,
    student_mobile: str,
    parent_mobile: str,
    attendance_id: int,
    attendance_time: datetime,
    year: str = "",
    department: str = "",
):
    """
    Background worker that formats messages, calls the SMS provider,
    updates late_alert_sent on Attendance, and records an activity log entry.
    """
    from database.models import get_session, Attendance, ActivityLog

    student_msg = format_student_message(name, student_id, year, department, attendance_time)
    parent_msg = format_parent_message(name, student_id, year, department, attendance_time)

    config = get_config()

    if not config.get("enabled", True):
        print(f"[SMS ALERT] SMS alerts are disabled by configuration (SMS_ENABLED=false)", flush=True)
        return

    provider = get_sms_provider(config)

    # 1. Send alert to student
    student_res = dispatch_single_sms(student_mobile, student_msg, "student", provider)

    import time
    time.sleep(1.0)

    # 2. Send alert to parent
    parent_res = dispatch_single_sms(parent_mobile, parent_msg, "parent", provider)

    # 3. Mark attendance.late_alert_sent = True in DB
    session = get_session()
    try:
        att = session.query(Attendance).filter(Attendance.id == attendance_id).first()
        if att:
            att.late_alert_sent = True
            session.commit()

        # 4. Log to ActivityLog
        status_notes = []
        if student_res.get("success"):
            status_notes.append("Student alerted")
        elif student_res.get("reason") == "invalid_number":
            status_notes.append("Student mobile missing/invalid")
        else:
            status_notes.append("Student alert failed")

        if parent_res.get("success"):
            status_notes.append("Parent alerted")
        elif parent_res.get("reason") == "invalid_number":
            status_notes.append("Parent mobile missing/invalid")
        else:
            status_notes.append("Parent alert failed")

        summary = f"{name} ({student_id}) - {', '.join(status_notes)}"

        activity = ActivityLog(
            event_type="late_alert_sent",
            title="Late alert sent",
            detail=summary,
            student_id=student_id,
            created_at=datetime.now(),
        )
        session.add(activity)
        session.commit()

        print(f"[SMS ALERT COMPLETE] {summary}", flush=True)

    except Exception as exc:
        session.rollback()
        print(f"[SMS ALERT DB ERROR] Error updating alert status for {student_id}: {exc}", flush=True)
    finally:
        session.close()


def send_late_alert(student, attendance) -> bool:
    """
    Public entrypoint to trigger a late arrival alert.
    
    Verifies that the attendance record is 'late' and that an alert
    has not already been sent, then initiates asynchronous dispatch.
    
    Returns:
      True if an alert dispatch task was spawned, False if skipped.
    """
    if attendance is None or student is None:
        print("[SMS ALERT] Skipped: student or attendance record is None", flush=True)
        return False

    if getattr(attendance, "status", None) != "late":
        return False

    if getattr(attendance, "late_alert_sent", False):
        print(f"[SMS ALERT] Skipped: alert already sent for attendance #{attendance.id} ({student.student_id})", flush=True)
        return False

    # Spawn daemon thread so recognition and frame processing continue without delay
    thread = threading.Thread(
        target=_async_send_late_alerts,
        args=(
            student.student_id,
            student.name,
            getattr(student, "student_mobile", None),
            getattr(student, "parent_mobile", None),
            attendance.id,
            getattr(attendance, "date", datetime.now()),
            getattr(student, "year", ""),
            getattr(student, "department", ""),
        ),
        daemon=True,
    )
    thread.start()
    return True
