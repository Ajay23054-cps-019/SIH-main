"""Plain-text syslog parser for SAT-SA log-only ingestion.

Real CSEs sometimes submit raw SOC/device logs instead of structured alert
feeds. This module turns free-form syslog lines into normalized
:class:`ParsedLog` records. Classification (severity, category, recommended
solution) lives in :mod:`src.analytics.log_classifier`; this module only
extracts structure from text.

Supported line shapes (all partial-tolerant)::

    Jun  1 10:00:00 host-5 process[1234]: suspicious file detected
    <134>Jun  1 10:00:00 host-5 app: connection refused
    2024-06-01T10:00:00.123Z host-5 malware: ransomware payload observed
    2024-06-01 10:00:00 [WARN] host-5 - failed login attempt
    10:00:00 CRITICAL host-5 network: lateral movement detected
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

# Leading syslog priority, e.g. "<134>"
_PRIORITY_RE = re.compile(r"^\s*<\d+>")

# ISO-ish timestamp at the very start: 2024-06-01T10:00:00[.123][Z] or
# 2024-06-01 10:00:00[.123]
_ISO_TS_RE = re.compile(
    r"^\s*(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
)

# Classic syslog date: "Jun  1 10:00:00" (no year).
_SYSLOG_TS_RE = re.compile(
    r"^\s*([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})"
)

# Bare "HH:MM:SS" timestamp.
_TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2}):(\d{2})\b")

# Leading bracketed level: [ERROR] / (ERROR)
_BRACKET_LEVEL_RE = re.compile(r"^\s*[\[(]([A-Za-z]+)[\])]\s*")
# Leading bare level word: ERROR: / CRITICAL / WARN / etc.
# NOTE: SUSPICIOUS/ANOMALY/UNUSUAL are intentionally excluded — they are far
# more often message content than syslog level labels, and the classifier
# re-derives severity from keywords regardless.
_WORD_LEVEL_RE = re.compile(
    r"^\s*(CRITICAL|CRIT|FATAL|EMERG|ALERT|ERROR|ERR|FAIL|FAILURE|SEVERE|"
    r"WARN|WARNING|INFO|NOTICE|DEBUG|SUCCESS|OK)"
    r"\b\s*[:\-]?\s*", re.IGNORECASE)
# Process prefix such as "process[1234]:" or "sshd[5678]:".
_PROC_PREFIX_RE = re.compile(r"^[\w.\-]+\[\d+\]\s*:\s*")

# Apache/Nginx Combined + Common Log Format, e.g.
# 127.0.0.1 - frank [10/Oct/2000:13:55:36 -0700] "GET /x HTTP/1.0" 200 2326
# The [ts] bracket is optional so we also match access-log entries that were
# forwarded via syslog (timestamp lives in the syslog header, not the entry).
_APACHE_RE = re.compile(
    r'^(?P<ip>\S+)\s+(?P<ident>\S+)\s+(?P<user>\S+)\s+'
    r'(?:\[(?P<ts>[^\]]+)\]\s+)?'
    r'"(?P<request>[^"]*)"\s+(?P<status>\d{3})\s+(?P<bytes>\S+)'
    r'(?:\s+"(?P<referer>[^"]*)"\s+"(?P<ua>[^"]*)")?\s*$'
)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


@dataclass
class ParsedLog:
    """One parsed log line (pre-classification)."""

    raw: str
    timestamp: Optional[datetime] = None
    host: Optional[str] = None
    level: Optional[str] = None          # raw level word if present
    message: str = ""
    status_code: Optional[int] = None    # HTTP status for web/access logs
    request: Optional[str] = None        # raw request line for web/access logs
    rejected: bool = False
    reject_reason: Optional[str] = None


def _parse_iso(ts: str) -> Optional[datetime]:
    cleaned = ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _parse_syslog_date(mon: str, day: str, hh: str, mm: str, ss: str) -> Optional[datetime]:
    month = _MONTHS.get(mon.lower())
    if month is None:
        return None
    try:
        return datetime(datetime.now().year, month, int(day), int(hh), int(mm), int(ss))
    except ValueError:
        return None


def _parse_time_only(hh: str, mm: str, ss: str) -> Optional[datetime]:
    try:
        return datetime(datetime.now().year, 1, 1, int(hh), int(mm), int(ss))
    except ValueError:
        return None


def _parse_apache_timestamp(ts: str) -> Optional[datetime]:
    """Parse an Apache timestamp like ``10/Oct/2000:13:55:36 -0700``."""
    for fmt in ("%d/%b/%Y:%H:%M:%S %z", "%d/%b/%Y:%H:%M:%S"):
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    return None


def _split_request(request: str) -> tuple[str, str]:
    """Return ``(method, path)`` from a request line like ``GET /x HTTP/1.0``."""
    parts = request.split()
    if len(parts) >= 2:
        return parts[0], parts[1]
    if len(parts) == 1:
        return parts[0], ""
    return "", ""


def parse_timestamp(line: str) -> tuple[Optional[datetime], str]:
    """Return ``(timestamp, rest)`` where ``rest`` is the line after the
    timestamp was consumed (or the whole line if none was found)."""
    m = _ISO_TS_RE.match(line)
    if m:
        ts = _parse_iso(m.group(1))
        return ts, line[m.end():]
    m = _SYSLOG_TS_RE.match(line)
    if m:
        ts = _parse_syslog_date(m.group(1), m.group(2), m.group(3),
                                m.group(4), m.group(5))
        return ts, line[m.end():]
    m = _TIME_RE.match(line)
    if m:
        ts = _parse_time_only(m.group(1), m.group(2), m.group(3))
        return ts, line[m.end():]
    return None, line


def _extract_level(rest: str) -> tuple[Optional[str], str]:
    for rx in (_BRACKET_LEVEL_RE, _WORD_LEVEL_RE):
        m = rx.match(rest)
        if m:
            return m.group(1).upper(), rest[m.end():]
    return None, rest


def _looks_like_host(token: str) -> bool:
    """Heuristic: hostnames usually contain a digit, hyphen or dot
    (host-5, SYS-001, web01.local). Pure words are treated as message text."""
    return bool(re.match(r"^[\w.\-]+$", token)) and bool(re.search(r"\d|[-.]", token))


def parse_line(line: str) -> ParsedLog:
    raw = line.rstrip("\n")
    if not raw.strip():
        return ParsedLog(raw=raw, rejected=True, reject_reason="empty line")

    # Apache/Nginx access log? Parse it on its own path (timestamp, client IP,
    # request, status) before the generic syslog handling.
    apache = _APACHE_RE.match(raw)
    if apache:
        ts_str = apache.group("ts")
        ts = _parse_apache_timestamp(ts_str) if ts_str else None
        status = int(apache.group("status"))
        method, path = _split_request(apache.group("request"))
        user = apache.group("user")
        message = f"web access {method} {path} status {status}"
        if user and user != "-":
            message += f" user {user}"
        return ParsedLog(raw=raw, timestamp=ts, host=apache.group("ip"),
                         level=None, message=message, status_code=status,
                         request=apache.group("request"))

    text = raw
    # Strip syslog priority prefix.
    m = _PRIORITY_RE.match(text)
    if m:
        text = text[m.end():]

    timestamp, rest = parse_timestamp(text)
    if timestamp is None:
        rest = text  # no timestamp; treat whole line as body

    level, rest = _extract_level(rest)
    rest = rest.strip()

    # Host is the next whitespace-delimited token, if it looks host-like
    # and is followed by more text (the actual message).
    host = None
    parts = rest.split(None, 1)
    if len(parts) == 2 and _looks_like_host(parts[0]):
        host = parts[0]
        rest = parts[1].strip()

    # Drop a leading "process[pid]:" prefix from the message body.
    rest = _PROC_PREFIX_RE.sub("", rest)
    rest = rest.lstrip("-: ").strip()

    # After stripping the syslog prefix (timestamp, host, process), the
    # remaining text may itself be an Apache/Nginx access-log line — common
    # when web-server logs are forwarded via syslog (the timestamp lives in
    # the syslog header, not in the access-log entry).  Re-check against the
    # access-log grammar; if it matches, return an access-log style record.
    apache = _APACHE_RE.match(rest)
    if apache:
        ts_str = apache.group("ts")
        apache_ts = _parse_apache_timestamp(ts_str) if ts_str else None
        status = int(apache.group("status"))
        method, path = _split_request(apache.group("request"))
        user = apache.group("user")
        client_ip = apache.group("ip")
        message = f"web access {method} {path} status {status}"
        if user and user != "-":
            message += f" user {user}"
        return ParsedLog(raw=raw, timestamp=timestamp or apache_ts,
                         host=client_ip, level=None, message=message,
                         status_code=status, request=apache.group("request"))

    return ParsedLog(raw=raw, timestamp=timestamp, host=host,
                     level=level, message=rest)


def parse_syslog(text: str) -> List[ParsedLog]:
    """Parse a multi-line syslog blob into :class:`ParsedLog` records."""
    logs: List[ParsedLog] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        logs.append(parse_line(line))
    return logs


def parse_log_file(path) -> List[ParsedLog]:
    from pathlib import Path

    return parse_syslog(Path(path).read_text(encoding="utf-8", errors="replace"))
