"""
Late Arrival Notification Service
Handles validation of mobile numbers, SMS message generation, and dispatching
late arrival alerts to students and parents without blocking the recognition loop.
"""

import os
import re
import sys
import json
import socket
import logging
import threading
from datetime import datetime
from dotenv import load_dotenv

# Ensure environment variables are loaded
# override=True ensures .env always wins over stale OS-level env vars
load_dotenv(override=True)

logger = logging.getLogger("notification_service")

# ---------------------------------------------------------------------------
# Auto-Discovery: SMS Gate Gateway IP Cache
# ---------------------------------------------------------------------------
# Keeps the last-known working gateway IP in memory and auto-scans the
# local network when the configured IP stops responding.
# ---------------------------------------------------------------------------
_gateway_ip_lock = threading.Lock()
_cached_gateway_ip: str = ""          # last-known working IP
_last_discovery_time: float = 0.0     # epoch seconds of last scan
_DISCOVERY_COOLDOWN = 30.0            # don't re-scan more than once per 30s
_SMS_GATE_PORT = 8080


def _get_local_subnets() -> list[str]:
    """Return a list of /24 subnet prefixes for all local network interfaces."""
    subnets = set()
    try:
        # Primary route subnet
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        prefix = ".".join(local_ip.split(".")[:3])
        subnets.add(prefix)
    except Exception:
        pass
    return list(subnets)


def _probe_gateway(ip: str, port: int = _SMS_GATE_PORT, timeout: float = 0.4) -> bool:
    """Return True if port 8080 is open on the given IP (TCP-only probe).
    
    We use TCP-only because the SMS Gate app sometimes accepts the connection
    but hangs on HTTP responses when backgrounded — an HTTP probe would time out
    and incorrectly report the device as missing.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def discover_gateway(api_key: str = "", force: bool = False) -> str:
    """
    Discover the SMS Gate gateway IP on the local network.

    Scans the /24 subnet of each local interface in parallel.
    Returns the discovered IP string, or empty string if not found.
    Updates .env SMS_API_URL automatically when found.
    """
    import time
    import concurrent.futures

    global _cached_gateway_ip, _last_discovery_time

    with _gateway_ip_lock:
        now = time.time()
        if not force and (now - _last_discovery_time) < _DISCOVERY_COOLDOWN:
            return _cached_gateway_ip
        _last_discovery_time = now

    print("[SMS GATEWAY] Scanning local network for SMS Gate app...", flush=True)

    subnets = _get_local_subnets()
    candidates = []
    for prefix in subnets:
        for i in range(1, 255):
            candidates.append(f"{prefix}.{i}")

    found_ip = ""
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as executor:
        future_to_ip = {executor.submit(_probe_gateway, ip): ip for ip in candidates}
        for future in concurrent.futures.as_completed(future_to_ip):
            ip = future_to_ip[future]
            try:
                if future.result():
                    found_ip = ip
                    # Cancel remaining futures once found
                    for f in future_to_ip:
                        f.cancel()
                    break
            except Exception:
                pass

    if found_ip:
        print(f"[SMS GATEWAY] Discovered gateway at {found_ip}:{_SMS_GATE_PORT}", flush=True)
        with _gateway_ip_lock:
            _cached_gateway_ip = found_ip
        # Auto-update .env so future restarts use the right IP
        _update_env_api_url(f"{found_ip}:{_SMS_GATE_PORT}")
    else:
        print("[SMS GATEWAY] Gateway not found on local network.", flush=True)

    return found_ip


def _update_env_api_url(new_url: str):
    """Rewrite SMS_API_URL in .env with the newly discovered IP."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                lines = f.readlines()

        updated = False
        new_lines = []
        for line in lines:
            if line.strip().startswith("SMS_API_URL="):
                new_lines.append(f"SMS_API_URL={new_url}\n")
                updated = True
            else:
                new_lines.append(line)

        if not updated:
            new_lines.append(f"SMS_API_URL={new_url}\n")

        with open(env_path, "w") as f:
            f.writelines(new_lines)

        # Reload into os.environ immediately
        os.environ["SMS_API_URL"] = new_url
        print(f"[SMS GATEWAY] .env updated: SMS_API_URL={new_url}", flush=True)
    except Exception as exc:
        print(f"[SMS GATEWAY] Failed to update .env: {exc}", flush=True)


# ---------------------------------------------------------------------------
# SMS Retry Queue
# ---------------------------------------------------------------------------
# If the gateway is unreachable when an alert fires, the job is queued and
# retried every 30 seconds in a background thread until it succeeds.
# ---------------------------------------------------------------------------
import queue as _queue
import time as _time_mod

_sms_retry_queue: "_queue.Queue[dict]" = _queue.Queue()
_retry_thread_started = False
_retry_thread_lock = threading.Lock()
_RETRY_INTERVAL = 30  # seconds between retry sweeps


def _sms_retry_worker():
    """Background thread: retry queued SMS jobs every 30 seconds."""
    while True:
        _time_mod.sleep(_RETRY_INTERVAL)

        pending = []
        while True:
            try:
                job = _sms_retry_queue.get_nowait()
                pending.append(job)
            except _queue.Empty:
                break

        if not pending:
            continue

        print(f"[SMS RETRY] Retrying {len(pending)} queued SMS job(s)...", flush=True)

        # Fresh discovery before retrying
        discover_gateway(force=True)

        config = get_config()
        provider = get_sms_provider(config)

        requeue = []
        for job in pending:
            to = job["to"]
            msg = job["message"]
            rtype = job["recipient_type"]
            attempts = job.get("attempts", 0) + 1

            try:
                provider.send(to, msg, recipient_type=rtype)
                print(f"[SMS RETRY] Success after {attempts} attempt(s) for {to}", flush=True)
            except Exception as exc:
                print(f"[SMS RETRY] Still failing for {to}: {exc}", flush=True)
                if attempts < 20:  # give up after 20 attempts (~10 minutes)
                    job["attempts"] = attempts
                    requeue.append(job)
                else:
                    print(f"[SMS RETRY] Giving up on {to} after {attempts} attempts.", flush=True)

        for job in requeue:
            _sms_retry_queue.put(job)


def _ensure_retry_thread():
    """Start the background retry thread if not already running."""
    global _retry_thread_started
    with _retry_thread_lock:
        if not _retry_thread_started:
            t = threading.Thread(target=_sms_retry_worker, daemon=True, name="SMSRetryWorker")
            t.start()
            _retry_thread_started = True


def enqueue_sms_retry(to: str, message: str, recipient_type: str):
    """Add a failed SMS to the retry queue and ensure the retry worker is running."""
    _ensure_retry_thread()
    _sms_retry_queue.put({
        "to": to,
        "message": message,
        "recipient_type": recipient_type,
        "attempts": 0,
    })
    print(f"[SMS RETRY] Queued SMS for {recipient_type} ({to}) — will retry in {_RETRY_INTERVAL}s", flush=True)




def get_config():
    """Load current notification configuration from environment.
    
    Always re-reads .env so changes take effect without restarting.
    """
    # Re-read .env on every call — ensures updates take effect immediately
    load_dotenv(override=True)

    sms_enabled_str = os.getenv("SMS_ENABLED", "true").strip().lower()
    sms_enabled = sms_enabled_str in ("true", "1", "yes", "on")

    provider = os.getenv("SMS_PROVIDER", "mock").strip().lower()
    api_key = os.getenv("SMS_API_KEY", "").strip()
    sender_id = os.getenv("SMS_SENDER_ID", "").strip()
    api_url = os.getenv("SMS_API_URL", "").strip()
    device_id = os.getenv("SMS_DEVICE_ID", "").strip()

    twilio_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    twilio_from = os.getenv("TWILIO_FROM_NUMBER", "").strip()

    return {
        "enabled": sms_enabled,
        "provider": provider,
        "api_key": api_key,
        "sender_id": sender_id,
        "api_url": api_url,
        "device_id": device_id,
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
    time_str = dt.strftime("%I:%M %p")

    parts = []
    if year and str(year).strip() != "N/A":
        parts.append(str(year).strip())
    if department and str(department).strip() != "N/A":
        parts.append(str(department).strip())

    academic_info = " - ".join(parts) if parts else ""
    academic_prefix = f" of {academic_info}" if academic_info else ""

    return (
        f"Dear Student, {name} ({student_id}){academic_prefix} "
        f"was late to college today ({date_str} at {time_str}). "
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
    time_str = dt.strftime("%I:%M %p")

    parts = []
    if year and str(year).strip() != "N/A":
        parts.append(str(year).strip())
    if department and str(department).strip() != "N/A":
        parts.append(str(department).strip())

    academic_info = " - ".join(parts) if parts else ""
    academic_prefix = f" of {academic_info}" if academic_info else ""

    return (
        f"Dear Parent, Your Son/Daughter, {name} ({student_id}){academic_prefix} "
        f"was late to college today ({date_str} at {time_str}). "
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
    """Sends SMS via a local Android phone running the SMS Gate app.
    
    Uses the documented SMS Gate local server API format:
      POST /message
      Body: { "textMessage": { "text": "..." }, "phoneNumbers": ["+91..."] }
      Auth: Basic (username:password)
    
    Includes retry logic with exponential backoff for transient failures.
    """

    MAX_RETRIES = 2
    BASE_TIMEOUT = 5  # seconds per attempt
    BACKOFF_FACTOR = 1  # seconds between retries (doubles each attempt)

    def __init__(self, api_url: str, api_key: str = ""):
        self.api_url = (api_url or "").strip()
        self.api_key = (api_key or "").strip()

    def _effective_url(self) -> str:
        """Return the current best URL, using cached discovery if available."""
        with _gateway_ip_lock:
            cached = _cached_gateway_ip

        # Prefer in-memory discovered IP over .env (may be stale)
        base = cached if cached else self.api_url
        if not base:
            return ""

        if not base.startswith(("http://", "https://")):
            base = f"http://{base}"

        from urllib.parse import urlparse
        parsed = urlparse(base)
        if not parsed.path or parsed.path == "/":
            base = base.rstrip("/") + "/message"

        return base

    def _build_auth(self) -> tuple:
        """Return (headers_dict, auth_tuple) for the request."""
        headers = {"Content-Type": "application/json"}
        auth = None

        if self.api_key:
            if ":" in self.api_key:
                user, pwd = self.api_key.split(":", 1)
                auth = (user, pwd)
            else:
                headers["Authorization"] = f"Bearer {self.api_key}"
                headers["X-API-Key"] = self.api_key

        return headers, auth

    def send(self, to_number: str, message: str, recipient_type: str = "recipient") -> dict:
        import requests
        import time as _time

        if not self.api_url and not _cached_gateway_ip:
            raise ValueError("Android SMS Gateway provider configured but SMS_API_URL is missing in .env")

        headers, auth = self._build_auth()
        phone = to_number if to_number.startswith("+") else f"+91{to_number}"

        payload = {
            "textMessage": {"text": message},
            "phoneNumbers": [phone],
        }

        last_error = None
        discovered_this_send = False

        for attempt in range(1, self.MAX_RETRIES + 1):
            url = self._effective_url()
            try:
                print(f"[SMS GATEWAY] Attempt {attempt}/{self.MAX_RETRIES} -> {url} for {phone}", flush=True)

                resp = requests.post(
                    url, json=payload, headers=headers, auth=auth,
                    timeout=self.BASE_TIMEOUT,
                )

                if resp.status_code in (200, 201, 202):
                    print(f"[SMS GATEWAY] Success ({resp.status_code})", flush=True)
                    return {
                        "success": True,
                        "provider": "android_gateway",
                        "status_code": resp.status_code,
                        "attempts": attempt,
                    }

                # Non-retryable client errors (auth issues, bad request)
                if 400 <= resp.status_code < 500:
                    raise ValueError(
                        f"Android SMS Gateway Error ({resp.status_code}): "
                        f"{resp.text or 'Unauthorized / Bad Request'}"
                    )

                last_error = ValueError(
                    f"Android SMS Gateway Error ({resp.status_code}): {resp.text}"
                )
                print(f"[SMS GATEWAY] Server error ({resp.status_code}), retrying...", flush=True)

            except requests.exceptions.ConnectionError as exc:
                last_error = exc
                print(f"[SMS GATEWAY] Connection error on attempt {attempt}: {exc}", flush=True)
            except requests.exceptions.Timeout as exc:
                last_error = exc
                print(f"[SMS GATEWAY] Timeout on attempt {attempt}: {exc}", flush=True)
            except ValueError:
                raise  # Don't retry auth/client errors
            except Exception as exc:
                last_error = exc
                print(f"[SMS GATEWAY] Unexpected error on attempt {attempt}: {exc}", flush=True)

            # On first failure: try auto-discovering the gateway IP
            if attempt == 1 and not discovered_this_send:
                discovered_this_send = True
                print("[SMS GATEWAY] Configured IP unreachable — attempting auto-discovery...", flush=True)
                new_ip = discover_gateway(api_key=self.api_key)
                if new_ip:
                    print(f"[SMS GATEWAY] Found gateway at {new_ip}, retrying send...", flush=True)
                    continue  # Retry immediately with the new IP

            if attempt < self.MAX_RETRIES:
                wait = self.BACKOFF_FACTOR * attempt
                print(f"[SMS GATEWAY] Waiting {wait}s before retry...", flush=True)
                _time.sleep(wait)

        raise ConnectionError(
            f"SMS Gateway unreachable after {self.MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        )


class SMSGateCloudProvider(SMSProvider):
    """Sends SMS via the sms-gate.app Cloud API.

    Bypasses the local server entirely — cloud API pushes to the phone
    via sms-gate.app servers, so the phone's local IP doesn't matter.

    Requires Cloud Server mode enabled in the SMS Gate app.
    Set in .env:
      SMS_PROVIDER=smsgate_cloud
      SMS_API_KEY=<cloud_username>:<cloud_password>
      SMS_DEVICE_ID=<device_id from app>   (optional, for multi-device)
    """

    CLOUD_URL = "https://api.sms-gate.app/3rdparty/v1/messages"

    def __init__(self, api_key: str, device_id: str = ""):
        # api_key format: "username:password"
        self.api_key = (api_key or "").strip()
        self.device_id = (device_id or "").strip()

    def send(self, to_number: str, message: str, recipient_type: str = "recipient") -> dict:
        import requests

        if not self.api_key or ":" not in self.api_key:
            raise ValueError(
                "SMSGate Cloud provider requires SMS_API_KEY=username:password "
                "(from Cloud Server section in the SMS Gate app)"
            )

        username, password = self.api_key.split(":", 1)
        phone = to_number if to_number.startswith("+") else f"+91{to_number}"

        payload = {
            "textMessage": {"text": message},
            "phoneNumbers": [phone],
        }
        if self.device_id:
            payload["deviceId"] = self.device_id

        resp = requests.post(
            self.CLOUD_URL,
            json=payload,
            auth=(username, password),
            timeout=15,
        )

        if resp.status_code in (200, 201, 202):
            print(f"[SMS CLOUD] Sent to {phone} via sms-gate.app cloud", flush=True)
            return {"success": True, "provider": "smsgate_cloud", "status_code": resp.status_code}

        raise ValueError(
            f"SMSGate Cloud API Error ({resp.status_code}): "
            f"{resp.text[:200] or 'Unknown error'}"
        )


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
    elif provider_name in ("smsgate_cloud", "smsgate"):
        return SMSGateCloudProvider(
            config.get("api_key"),
            config.get("device_id", ""),
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
    """Dispatch SMS to a single recipient with safety and error handling.
    
    On failure, automatically queues the SMS for retry every 30 seconds
    until the gateway comes back online.
    """
    is_valid, normalized = normalize_indian_mobile(to_number)
    if not is_valid:
        print(f"[SMS ALERT] Skipped {recipient_type}: Missing or invalid mobile number '{to_number}'", flush=True)
        return {"success": False, "reason": "invalid_number", "number": to_number}

    try:
        result = provider.send(normalized, message, recipient_type=recipient_type)
        return {"success": True, "result": result}
    except Exception as exc:
        print(f"[SMS ALERT ERROR] Failed to send SMS to {recipient_type} ({normalized}): {exc}", flush=True)
        # Auto-queue for retry — will be retried every 30s until gateway responds
        enqueue_sms_retry(normalized, message, recipient_type)
        return {"success": False, "queued": True, "error": str(exc), "number": normalized}


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
    time.sleep(0.5)

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
        elif student_res.get("queued"):
            status_notes.append("Student SMS queued (gateway offline)")
        else:
            status_notes.append("Student alert failed")

        if parent_res.get("success"):
            status_notes.append("Parent alerted")
        elif parent_res.get("reason") == "invalid_number":
            status_notes.append("Parent mobile missing/invalid")
        elif parent_res.get("queued"):
            status_notes.append("Parent SMS queued (gateway offline)")
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
