"""Deterministic classification of parsed syslog records into alerts.

Turns :class:`~src.ingestion.log_parser.ParsedLog` records into canonical
:class:`~src.analytics.schemas.Alert` objects. Classification is **rule-based
and fully deterministic** (keyword/regex scoring + a playbook lookup) — no ML,
no LLM — consistent with SAT-SA's evidence-based analytics philosophy.

Three fields are derived per log line:

* ``severity``  — from an explicit level token (``[ERROR]``, ``CRITICAL`` …)
  and from content keywords (``ransomware``, ``breach`` …), taking the higher.
* ``category``  — malware / authentication / network / endpoint / database /
  web, by keyword priority.
* ``description`` — original message plus a recommended solution from the
  response playbook.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from src.analytics.schemas import Alert
from src.ingestion.log_parser import ParsedLog

# ---------------------------------------------------------------------------
# Severity scoring
# ---------------------------------------------------------------------------

SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

LEVEL_TO_SEVERITY: Dict[str, str] = {
    "CRITICAL": "CRITICAL", "CRIT": "CRITICAL", "FATAL": "CRITICAL",
    "EMERG": "CRITICAL", "EMERGENCY": "CRITICAL", "ALERT": "CRITICAL",
    "ERROR": "HIGH", "ERR": "HIGH", "FAIL": "HIGH", "FAILURE": "HIGH",
    "SEVERE": "HIGH",
    "WARN": "MEDIUM", "WARNING": "MEDIUM",
    "INFO": "LOW", "NOTICE": "LOW", "DEBUG": "LOW",
    "SUCCESS": "LOW", "OK": "LOW",
}

# Content keywords that *escalate* severity regardless of any level token.
CRITICAL_KEYWORDS = {
    "ransomware", "data exfiltration", "exfiltration", "lateral movement",
    "privilege escalation", "root compromise", "zero-day", "zero day",
    "exploit", "breach", "credential dump", "credential dumping",
    "backdoor", "wiper", "implant", "command and control", "c2", "rce",
    "remote code execution", "domain controller", "active directory",
    "destructive", "widespread",
}
HIGH_KEYWORDS = {
    "malware", "virus", "trojan", "worm", "rootkit", "spyware", "payload",
    "phishing", "spearphish", "brute force", "bruteforce", "password spray",
    "sql injection", "xss", "csrf", "ddos", "denial of service",
    "port scan", "unauthorized access", "intrusion", "compromise",
    "suspicious file", "obfuscated", "malicious", "botnet", "keylogger",
    # Web/access-log attack indicators (path or query fragments)
    "wp-login", "wp-admin", "phpmyadmin", "xmlrpc.php", "etc/passwd",
    ".env", ".git", "cmd.exe", "powershell", "select *", "union select",
    "command injection", "traversal", "../", "passwd",
}
MEDIUM_KEYWORDS = {
    "suspicious", "failed login", "failed password", "anomaly", "anomalous",
    "unusual", "unauthorized", "policy violation", "reconnaissance",
    "scan", "probe", "warning", "elevated", "blocked connection",
}

# Boundary-aware matchers. ``(?<![\w]) ... (?![\w])`` treats hyphens/punctuation
# as boundaries, so ``locked`` no longer matches inside ``blocked`` while
# ``ransomware`` still matches inside ``anti-ransomware``.
_BOUNDARY = r"(?<![\w])(?:{})(?![\w])"


def _compile(words):
    return re.compile(_BOUNDARY.format("|".join(re.escape(w) for w in words)),
                     re.IGNORECASE)


CRIT_RES = _compile(CRITICAL_KEYWORDS)
HIGH_RES = _compile(HIGH_KEYWORDS)
MED_RES = _compile(MEDIUM_KEYWORDS)

# ---------------------------------------------------------------------------
# Category detection
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS: Dict[str, set] = {
    "authentication": {
        "login", "logon", "auth", "password", "credential", "mfa", "2fa",
        "account", "kerberos", "sudo", "ssh", "session", "token", "oauth",
        "ldap", "radius", "access denied", "locked",
    },
    "malware": {
        "malware", "virus", "trojan", "ransomware", "worm", "rootkit",
        "spyware", "payload", "implant", "botnet", "keylogger", "backdoor",
        "edr", "antivirus", "signature", "ioc", "hash",
    },
    "network": {
        "network", "packet", "firewall", "port", "tcp", "udp", "dns", "http",
        "https", "ip", "vpn", "proxy", "lateral", "bandwidth", "traffic",
        "connection", "socket", "subnet", "gateway", "router", "switch",
    },
    "database": {
        "database", "sql", "query", "table", "oracle", "postgres",
        "mysql", "mongodb", "schema", "record", "datastore",
        "nosql", "redis", "cursor",
    },
    "web": {
        "web", "website", "apache", "nginx", "url", "owasp", "csrf",
        "xss", "form", "cookie", "session", "browser", "http request",
    },
    "endpoint": {
        "endpoint", "host", "workstation", "laptop", "desktop", "process",
        "executable", "registry", "usb", "file", "service", "daemon",
        "kernel", "driver", "memory", "schedule", "cron", "task",
    },
}
CATEGORY_ORDER = ("authentication", "malware", "network", "database", "web",
                  "endpoint")  # endpoint is the generic fallback
DEFAULT_CATEGORY = "endpoint"
CATEGORY_RES = {cat: _compile(words) for cat, words in CATEGORY_KEYWORDS.items()}


# ---------------------------------------------------------------------------
# Response playbook
# ---------------------------------------------------------------------------

PLAYBOOK: Dict[str, str] = {
    "malware": ("Isolate the affected asset, capture a forensic image, run a "
                "full EDR scan, and submit observed IOCs to threat intelligence."),
    "authentication": ("Force a credential reset, enforce MFA, review for "
                       "impossible-travel and privileged-account abuse, and "
                       "audit recent session tokens."),
    "network": ("Capture pcaps, block the offending source IPs at the firewall, "
                "and verify lateral-movement containment."),
    "database": ("Revoke the exposed credentials, audit query history, and "
                 "enable query logging and alerting on sensitive tables."),
    "web": ("Patch the vulnerable endpoint, deploy a WAF rule, and scan for "
            "additional injection points."),
    "endpoint": ("Isolate the endpoint, inspect the process tree, and confirm "
                 "no persistence remains before re-enabling access."),
}

# Keyword-specific overrides appended after the base playbook action.
RESPONSE_OVERRIDES: List[Tuple[set, str]] = [
    ({"ransomware", "wiper", "destructive"},
     "Treat as a declared incident: disconnect from the network, preserve "
     "evidence, and prepare for restoration from clean backups."),
    ({"data exfiltration", "exfiltration", "credential dump"},
     "Assume data loss: rotate all secrets, inspect egress paths, and engage "
     "the incident-response and legal teams."),
    ({"lateral movement", "privilege escalation", "domain controller"},
     "Scope the blast radius across the estate and reset domain credentials."),
    ({"phishing", "spearphish"},
     "Block the sending domain, hunt for clicked links/attachments, and run "
     "user-awareness follow-up."),
    ({"brute force", "password spray", "failed login", "failed password"},
     "Rate-limit authentication, alert on repeat offenders, and review "
     "lockout policy."),
    ({"sql injection", "xss", "csrf"},
     "Escalate to the application owner for emergency remediation and add the "
     "finding to the secure-code review backlog."),
]


# ---------------------------------------------------------------------------
# Classification functions
# ---------------------------------------------------------------------------


def classify_severity(message: str, level: Optional[str] = None,
                      status_code: Optional[int] = None) -> str:
    """Return the highest of (level-derived, status-derived, content-derived)
    severity.

    For web/access logs, HTTP status codes drive severity: 5xx → HIGH,
    4xx → MEDIUM, 2xx/3xx → leave as content-derived (usually LOW).
    """
    text = message or ""
    score = 0
    if level:
        sev = LEVEL_TO_SEVERITY.get(level.upper())
        if sev:
            score = max(score, SEVERITY_RANK[sev])
    if status_code is not None:
        if 500 <= status_code <= 599:
            score = max(score, SEVERITY_RANK["HIGH"])
        elif 400 <= status_code <= 499:
            score = max(score, SEVERITY_RANK["MEDIUM"])
    if CRIT_RES.search(text):
        score = max(score, SEVERITY_RANK["CRITICAL"])
    if HIGH_RES.search(text):
        score = max(score, SEVERITY_RANK["HIGH"])
    if MED_RES.search(text):
        score = max(score, SEVERITY_RANK["MEDIUM"])
    if score == 0:
        return "LOW"
    rank_to_name = {r: name for name, r in SEVERITY_RANK.items()}
    return rank_to_name[score]


def classify_category(message: str) -> str:
    for cat in CATEGORY_ORDER:
        if CATEGORY_RES[cat].search(message or ""):
            return cat
    return DEFAULT_CATEGORY


def recommend_solution(category: str, message: str) -> str:
    base = PLAYBOOK.get(category, PLAYBOOK[DEFAULT_CATEGORY])
    text = message or ""
    extras = [note for keywords, note in RESPONSE_OVERRIDES
              if _compile(keywords).search(text)]
    if extras:
        return base + " " + " ".join(extras)
    return base


def _safe_id(cse_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", cse_id) or "CSE"


def classify_log(log: ParsedLog, cse_id: str, index: int,
                  default_status: str = "closed") -> Alert:
    """Build one :class:`Alert` from a parsed log line."""
    severity = classify_severity(log.message, log.level, log.status_code)
    category = classify_category(log.message)
    solution = recommend_solution(category, log.message)
    timestamp = log.timestamp or datetime.now()
    description = (log.message or log.raw).strip()
    if solution:
        description = f"{description} || RECOMMENDED: {solution}"
    return Alert(
        alert_id=f"LOG-{_safe_id(cse_id)}-{index:04d}",
        cse_id=cse_id,
        timestamp=timestamp,
        severity=severity,
        category=category,
        asset_id=log.host or "unknown",
        status=default_status,
        closure_timestamp=None,
        description=description,
    )


def logs_to_alerts(parsed: List[ParsedLog], cse_id: str,
                   default_status: str = "closed") -> Tuple[List[Alert], List[dict]]:
    """Classify parsed logs into alerts.

    Returns ``(alerts, rejections)``. A log with no usable message is
    rejected (recorded, not raised) so a malformed line never aborts the batch.
    """
    alerts: List[Alert] = []
    rejections: List[dict] = []
    idx = 0
    for log in parsed:
        if not (log.message or "").strip() and not (log.raw or "").strip():
            rejections.append({"raw": log.raw, "error": "empty message"})
            continue
        try:
            alerts.append(classify_log(log, cse_id, idx, default_status))
        except Exception as exc:  # pragma: no cover - defensive
            rejections.append({"raw": log.raw, "error": str(exc)})
            continue
        idx += 1
    return alerts, rejections
