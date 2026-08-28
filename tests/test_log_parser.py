"""Unit tests for the plain-text syslog parser."""
from __future__ import annotations

from src.ingestion.log_parser import (
    parse_line,
    parse_syslog,
)


SAMPLE = """
Jun  1 10:00:00 host-5 process[1234]: suspicious file detected
<134>Jun  1 10:00:00 host-5 app: connection refused
2024-06-01T10:00:00.123Z host-5 malware: ransomware payload observed
2024-06-01 10:00:00 [WARN] host-5 - failed login attempt
10:00:00 CRITICAL host-5 network: lateral movement detected
2024-06-01 12:30:00 suspicious activity on the gateway
"""


def test_parse_count():
    logs = parse_syslog(SAMPLE)
    assert len(logs) == 6


def test_host_extracted():
    logs = parse_syslog(SAMPLE)
    hosts = {log.host for log in logs}
    assert "host-5" in hosts


def test_level_extracted():
    logs = {log.message: log for log in parse_syslog(SAMPLE)}
    warn = next(l for l in parse_syslog(SAMPLE) if l.level == "WARN")
    assert warn.message == "failed login attempt"
    crit = next(l for l in parse_syslog(SAMPLE) if l.level == "CRITICAL")
    assert "lateral movement" in crit.message


def test_timestamp_parsed():
    logs = parse_syslog(SAMPLE)
    # ISO timestamp with year is preserved exactly.
    iso = next(l for l in logs if l.raw.startswith("2024-06-01T10"))
    assert iso.timestamp is not None
    assert iso.timestamp.year == 2024


def test_empty_lines_rejected():
    logs = parse_syslog("\n\n   \n")
    assert all(l.rejected for l in logs)


def test_bare_message_no_host():
    log = parse_line("suspicious activity on the gateway")
    assert log.host is None
    assert "suspicious" in log.message


def test_apache_combined_log_parsed():
    line = ('127.0.0.1 - frank [10/Oct/2000:13:55:36 -0700] '
            '"GET /apache_pb.gif HTTP/1.0" 200 2326')
    log = parse_line(line)
    assert log.host == "127.0.0.1"
    assert log.status_code == 200
    assert log.request == "GET /apache_pb.gif HTTP/1.0"
    assert log.timestamp is not None
    assert log.timestamp.year == 2000
    assert "web access" in log.message
    assert "user frank" in log.message


def test_apache_common_log_parsed():
    line = ('192.168.1.5 - - [10/Oct/2000:13:56:10 -0700] '
            '"POST /wp-login.php HTTP/1.1" 403 512')
    log = parse_line(line)
    assert log.host == "192.168.1.5"
    assert log.status_code == 403
    assert "user" not in log.message  # anonymous '-' user not echoed
