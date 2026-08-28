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


def test_apache_log_without_timestamp_parsed():
    line = '10.0.0.23 - - "GET /index.html HTTP/1.1" 200 4521'
    log = parse_line(line)
    assert log.host == "10.0.0.23"
    assert log.status_code == 200
    assert log.request == "GET /index.html HTTP/1.1"
    assert log.timestamp is None
    assert "web access" in log.message


def test_nginx_via_syslog_hybrid_parsed():
    line = ('2026-08-28T10:01:12Z server01 nginx[1842]: '
            '192.168.1.45 - - "GET /login HTTP/1.1" 200 1245')
    log = parse_line(line)
    assert log.host == "192.168.1.45"
    assert log.status_code == 200
    assert log.request == "GET /login HTTP/1.1"
    assert log.timestamp is not None
    assert log.timestamp.year == 2026
    assert "web access" in log.message
    assert "/login" in log.message


def test_nginx_via_syslog_hybrid_401_detected():
    line = ('2026-08-28T10:01:15Z server01 nginx[1842]: '
            '192.168.1.45 - - "POST /login HTTP/1.1" 401 532')
    log = parse_line(line)
    assert log.status_code == 401
    assert log.request == "POST /login HTTP/1.1"


def test_nginx_via_syslog_path_traversal_detected():
    line = ('2026-08-28T10:04:31Z server01 nginx[1842]: '
            '203.0.113.42 - - "GET /../../etc/passwd HTTP/1.1" 400 166')
    log = parse_line(line)
    assert log.host == "203.0.113.42"
    assert log.status_code == 400
    assert log.request == "GET /../../etc/passwd HTTP/1.1"
    assert "../" in log.message or "passwd" in log.message


def test_sshd_via_syslog_still_parsed():
    line = ('2026-08-28T10:02:15Z server01 sshd[2911]: '
            'Failed password for admin from 203.0.113.42 port 49221 ssh2')
    log = parse_line(line)
    assert log.host == "server01"
    assert log.status_code is None
    assert log.request is None
    assert "Failed password" in log.message


def test_kernel_via_syslog_still_parsed():
    line = ('2026-08-28T10:03:07Z server01 kernel: '
            'Possible SYN flooding on port 443. Sending cookies.')
    log = parse_line(line)
    assert log.host == "server01"
    assert log.status_code is None
    assert "SYN flooding" in log.message
