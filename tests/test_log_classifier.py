"""Unit tests for deterministic log classification."""
from __future__ import annotations

from src.analytics.log_classifier import (
    classify_category,
    classify_severity,
    logs_to_alerts,
    recommend_solution,
)
from src.ingestion.log_parser import parse_syslog


def test_severity_from_level():
    assert classify_severity("something happened", "CRITICAL") == "CRITICAL"
    assert classify_severity("something happened", "ERROR") == "HIGH"
    assert classify_severity("something happened", "WARN") == "MEDIUM"
    assert classify_severity("something happened", "INFO") == "LOW"


def test_severity_from_keywords():
    assert classify_severity("ransomware payload detected") == "CRITICAL"
    assert classify_severity("malware blocked") == "HIGH"
    assert classify_severity("suspicious login") == "MEDIUM"
    assert classify_severity("routine backup completed") == "LOW"


def test_severity_takes_max():
    # A CRITICAL level with benign text still resolves CRITICAL.
    assert classify_severity("system check ok", "CRITICAL") == "CRITICAL"


def test_category_detection():
    assert classify_category("failed password for root") == "authentication"
    assert classify_category("ransomware on endpoint") == "malware"
    assert classify_category("lateral movement across network") == "network"
    assert classify_category("sql injection attempt") == "database"
    assert classify_category("xss in web form") == "web"
    assert classify_category("process crashed on host") == "endpoint"


def test_substring_not_misclassified():
    # "locked" must not match inside "blocked".
    assert classify_category("blocked connection from suspicious ip") != "authentication"
    assert classify_severity("connection blocked") == "LOW"


def test_recommendation_includes_playbook():
    sol = recommend_solution("malware", "ransomware observed")
    assert "isolate" in sol.lower()
    assert "backup" in sol.lower()  # ransomware override


def test_severity_from_http_status():
    # Status codes drive severity for web/access logs (passed via status_code).
    assert classify_severity("web access GET /x status 200", status_code=200) == "LOW"
    assert classify_severity("web access GET /x status 404", status_code=404) == "MEDIUM"
    assert classify_severity("web access GET /x status 500", status_code=500) == "HIGH"
    # Keyword escalation still wins for attack paths.
    assert classify_severity("web access GET /etc/passwd status 404",
                             status_code=404) == "HIGH"


def test_apache_log_to_alert():
    from src.ingestion.log_parser import parse_line

    line = ('10.0.0.9 - - [10/Oct/2000:13:57:02 -0700] '
            '"GET /etc/passwd HTTP/1.0" 404 210')
    logs = [parse_line(line)]
    alerts, rej = logs_to_alerts(logs, "WEB-CSE")
    assert rej == []
    assert alerts[0].severity == "HIGH"
    assert alerts[0].category == "web"
    assert alerts[0].asset_id == "10.0.0.9"
    assert alerts[0].timestamp.year == 2000


def test_logs_to_alerts_end_to_end():
    text = (
        "2024-06-01T10:00:00.123Z host-5 malware: ransomware payload observed\n"
        "2024-06-01 10:05:00 [WARN] host-3 auth: failed password for root\n"
    )
    logs = parse_syslog(text)
    alerts, rej = logs_to_alerts(logs, "CSE-TEST")
    assert len(rej) == 0
    assert len(alerts) == 2
    assert alerts[0].severity == "CRITICAL"
    assert alerts[0].category == "malware"
    assert "RECOMMENDED" in alerts[0].description
    # alert ids are unique and cse-scoped
    assert len({a.alert_id for a in alerts}) == 2
    assert all(a.cse_id == "CSE-TEST" for a in alerts)
