"""Generate a large, varied set of test samples for SAT-SA upload/analysis.

Creates ~45 sample *scenarios* (≈70 individual files):

  test_samples/logs/syslog/   -- 20 SOC/device syslog scenarios
  test_samples/logs/web/      -- 15 bulk Apache/Nginx access-log scenarios
  test_samples/json_bundles/  -- 5 JSON alert bundles
  test_samples/cse_bundles/   -- 5 full structured CSE bundles (CSV per entity)

All content is deterministic (fixed seed) and written in the exact schema the
ingestion pipeline expects, so every sample ingests and classifies cleanly.
"""
from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

SEED = 1337
random.seed(SEED)

ROOT = Path("test_samples")
SYSL = ROOT / "logs" / "syslog"
WEB = ROOT / "logs" / "web"
JDIR = ROOT / "json_bundles"
CBUNDLE = ROOT / "cse_bundles"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
HOSTS = [f"host-{i:02d}" for i in range(1, 21)]
WEBHOSTS = [f"10.0.{i}.{j}" for i in range(1, 6) for j in range(2, 6)]
ASSETS = [f"AS-{i:04d}" for i in range(1, 9)]


def _ts(offset_min: int) -> datetime:
    return datetime(2024, 6, 1, 9, 0, 0) + timedelta(minutes=offset_min)


def _syslog(ts: datetime, host: str, msg: str, level: str | None = None) -> str:
    mon = MONTHS[ts.month - 1]
    stamp = f"{mon} {ts.day:>2} {ts.hour:02d}:{ts.minute:02d}:{ts.second:02d}"
    lvl = f" [{level}] " if level else " "
    return f"{stamp} {host} process[1234]:{lvl}{msg}"


def _apache(ts: datetime, ip: str, method: str, path: str, status: int,
            user: str = "-", bytes_: int = 512) -> str:
    stamp = ts.strftime("%d/%b/%Y:%H:%M:%S -0700")
    return (f'{ip} - {user} [{stamp}] "{method} {path} HTTP/1.1" '
            f'{status} {bytes_}')


# ---------------------------------------------------------------------------
# Syslog scenario definitions: (filename, [list of (level_or_None, message)])
# Each scenario is expanded into many bulk lines.
# ---------------------------------------------------------------------------

SYSL_SAMPLES: list[tuple[str, list[tuple[str | None, str]]]] = [
    ("ransomware_incident", [
        (None, "malware: ransomware payload enc.exe detected on host"),
        (None, "EDR isolated host after ransomware signature match"),
        (None, "data exfiltration to unknown IP over TLS observed"),
        (None, "lateral movement via SMB to file server detected"),
        (None, "shadow copies deleted by vssadmin command"),
    ]),
    ("brute_force_auth", [
        (None, "failed password for root from 10.0.1.9"),
        (None, "failed password for admin from 10.0.1.9"),
        (None, "password spray across 40 accounts detected"),
        (None, "account lockout threshold reached for svc_backup"),
        (None, "brute force attempt blocked by lockout policy"),
    ]),
    ("lateral_movement", [
        (None, "lateral movement observed from host-03 to host-07 via SMB"),
        (None, "privilege escalation via token impersonation on host-07"),
        (None, "remote code execution attempted on domain controller"),
        (None, "pass-the-hash authentication success from unknown host"),
        (None, "network: anomalous east-west traffic spike detected"),
    ]),
    ("data_exfiltration", [
        (None, "data exfiltration to 185.34.12.9 over DNS tunnel"),
        (None, "unusual outbound transfer of 4.2GB to external host"),
        (None, "credential dump of lsass process memory detected"),
        (None, "large archive uploaded to cloud storage outside policy"),
        (None, "DLP alert: sensitive PII leaving the network"),
    ]),
    ("sql_injection_web", [
        (None, "SQL injection attempt on /login.php blocked by WAF"),
        (None, "union select query detected in parameter id"),
        (None, "blind SQLi probing on /products?cat= observed"),
        (None, "database: suspicious query pattern from web tier"),
        (None, "web: error-based injection string ' OR 1=1 -- detected"),
    ]),
    ("phishing_campaign", [
        (None, "phishing email reported by 12 users this hour"),
        (None, "spearphish targeting finance with fake invoice"),
        (None, "malicious macro blocked in incoming attachment"),
        (None, "url click to known-bad domain flagged by proxy"),
        (None, "credential harvest page mimicry of SSO portal"),
    ]),
    ("ddos_attack", [
        (None, "SYN flood saturating edge firewall interfaces"),
        (None, "HTTP flood against public web tier detected"),
        (None, "DNS amplification traffic from botnet sources"),
        (None, "network: bandwidth exhaustion on uplink"),
        (None, "rate-limiting engaged on API gateway"),
    ]),
    ("port_scan", [
        (None, "port scan from 10.0.4.5 across 1024 ports"),
        (None, "reconnaissance: sequential connection attempts"),
        (None, "network: stealth SYN scan signature observed"),
        (None, "service enumeration on internal subnet detected"),
        (None, "probe of unused ports flagged by IDS"),
    ]),
    ("malware_detection", [
        (None, "trojan heuristic match in downloaded binary"),
        (None, "worm propagation attempt between workstations"),
        (None, "rootkit artifacts found in kernel memory"),
        (None, "spyware beaconing to C2 infrastructure"),
        (None, "antivirus: malicious payload quarantined"),
    ]),
    ("suspicious_login", [
        (None, "impossible travel: login from two countries in 10 min"),
        (None, "suspicious login at 03:14 from new device"),
        (None, "authentication: MFA bypass attempt detected"),
        (None, "session token reuse across geographies"),
        (None, "anomalous access to HR system by contractor"),
    ]),
    ("firewall_blocks", [
        (None, "firewall denied inbound connection on port 3389"),
        (None, "blocked connection from suspicious ip rep list"),
        (None, "network: egress to known malware domain blocked"),
        (None, "proxy blocked access to uncategorized site"),
        (None, "IPS dropped exploit kit traffic"),
    ]),
    ("privilege_escalation", [
        (None, "privilege escalation via sudo misconfiguration"),
        (None, "unauthorized addition to administrators group"),
        (None, "endpoint: persistence via scheduled task created"),
        (None, "registry run key modified by unknown process"),
        (None, "kernel driver load from temp directory"),
    ]),
    ("credential_dump", [
        (None, "credential dump of SAM hive attempted"),
        (None, "mimikatz-style memory scrape detected"),
        (None, "credential dumping tool execution blocked"),
        (None, "secrets harvested from browser store"),
        (None, "lsass access by non-system process"),
    ]),
    ("web_defacement", [
        (None, "web: unauthorized change to homepage detected"),
        (None, "file integrity violation on web root"),
        (None, "CMS plugin exploited to alter content"),
        (None, "web server: unexpected file write outside docroot"),
        (None, "defacement restored from known-good backup"),
    ]),
    ("insider_threat", [
        (None, "mass download of confidential files by employee"),
        (None, "off-hours access to restricted share"),
        (None, "usb mass storage usage on protected endpoint"),
        (None, "unauthorized cloud upload of source code"),
        (None, "anomalous data staging before departure"),
    ]),
    ("critical_infra", [
        ("CRITICAL", "network: SCADA controller unreachable"),
        ("CRITICAL", "power grid telemetry gap detected"),
        ("CRITICAL", "ics: unsafe state transition prevented"),
        ("CRITICAL", "water treatment setpoint altered abnormally"),
        ("CRITICAL", "ot: historian database connection lost"),
    ]),
    ("endpoint_anomalies", [
        (None, "endpoint: unknown process spawning powershell"),
        (None, "executable run from AppData temp location"),
        (None, "registry persistence created by unknown process"),
        (None, "endpoint: wmi subscription installed"),
        (None, "unexpected service installed on server"),
    ]),
    ("network_recon", [
        (None, "network: ARP sweep of local segment"),
        (None, "sniffing attempt detected on span port"),
        (None, "network: traceroute to internal subnets"),
        (None, "scan of SMB shares across VLAN"),
        (None, "reconnaissance prior to exploitation"),
    ]),
    ("mixed_severity", [
        ("INFO", "routine backup completed successfully"),
        ("WARN", "disk usage above 80% on host-09"),
        ("ERROR", "service crashed and auto-restarted"),
        (None, "suspicious login attempt blocked"),
        ("CRITICAL", "ransomware indicator found on endpoint"),
    ]),
    ("benign_noise", [
        ("INFO", "user session started"),
        ("INFO", "config reloaded"),
        ("DEBUG", "cache warmed"),
        ("NOTICE", "scheduled job finished"),
        ("INFO", "heartbeat ok"),
    ]),
]


def gen_syslog_file(path: Path, scenario: list[tuple[str | None, str]], n: int) -> None:
    lines = []
    for i in range(n):
        level, msg = random.choice(scenario)
        ts = _ts(i * 3 + random.randint(0, 2))
        host = random.choice(HOSTS)
        if level:
            msg = f"[{level}] {msg}"
        lines.append(_syslog(ts, host, msg, level if level else None))
    path.write_text("\n".join(lines) + "\n")


def gen_web_sample(path: Path, scenario: list[tuple[str, str, int]], n: int) -> None:
    lines = []
    for i in range(n):
        method, path_seg, status = random.choice(scenario)
        ts = _ts(i * 2 + random.randint(0, 1))
        ip = random.choice(WEBHOSTS)
        user = random.choice(["-", "frank", "admin", "guest", "root"])
        lines.append(_apache(ts, ip, method, path_seg, status, user))
    path.write_text("\n".join(lines) + "\n")


WEB_SAMPLES: list[tuple[str, list[tuple[str, str, int]]]] = [
    ("normal_web_traffic", [
        ("GET", "/index.html", 200), ("GET", "/style.css", 200),
        ("GET", "/apache_pb.gif", 200), ("POST", "/contact", 200),
        ("GET", "/about", 200),
    ]),
    ("wp_bruteforce", [
        ("POST", "/wp-login.php", 403), ("POST", "/wp-login.php", 403),
        ("POST", "/xmlrpc.php", 403), ("GET", "/wp-admin", 302),
        ("POST", "/wp-login.php", 200),
    ]),
    ("path_traversal", [
        ("GET", "/../etc/passwd", 404), ("GET", "/..%2f..%2fwin.ini", 404),
        ("GET", "/download?file=../../config.php", 404),
        ("GET", "/static/..%2fsecrets", 403), ("GET", "/api/../.env", 404),
    ]),
    ("sqli_attempts", [
        ("GET", "/items?id=1+UNION+SELECT+1,2,3", 500),
        ("POST", "/login", 500), ("GET", "/p?cat=1' OR '1'='1", 500),
        ("GET", "/s?q=%27%20OR%201=1--", 500), ("GET", "/x?id=0x73656c656374", 500),
    ]),
    ("scanner_recon", [
        ("GET", "/admin", 404), ("GET", "/phpmyadmin/", 404),
        ("GET", "/.git/config", 404), ("GET", "/robots.txt", 200),
        ("GET", "/wp-login.php", 404),
    ]),
    ("admin_panel_probing", [
        ("GET", "/admin", 302), ("GET", "/admin/index.php", 200),
        ("POST", "/admin/login", 403), ("GET", "/administrator", 404),
        ("GET", "/manager/html", 404),
    ]),
    ("dos_burst", [
        ("GET", "/", 200), ("GET", "/", 200), ("GET", "/", 503),
        ("GET", "/", 503), ("GET", "/", 200),
    ]),
    ("api_abuse", [
        ("POST", "/api/login", 429), ("POST", "/api/login", 429),
        ("GET", "/api/users", 401), ("POST", "/api/token", 400),
        ("GET", "/api/export", 403),
    ]),
    ("mixed_status", [
        ("GET", "/", 200), ("GET", "/missing", 404),
        ("GET", "/server-error", 500), ("POST", "/form", 200),
        ("GET", "/forbidden", 403),
    ]),
    ("webshell_upload", [
        ("POST", "/uploads/shell.php", 200), ("GET", "/uploads/shell.php", 200),
        ("POST", "/api/upload", 200), ("GET", "/uploads/cmd.php?c=whoami", 200),
        ("POST", "/admin/upload", 403),
    ]),
    ("normal_high_volume", [
        ("GET", "/img/logo.png", 200), ("GET", "/js/app.js", 200),
        ("GET", "/css/main.css", 200), ("GET", "/api/health", 200),
        ("GET", "/favicon.ico", 200),
    ]),
    ("auth_bypass_attempts", [
        ("POST", "/login", 200), ("POST", "/login", 403),
        ("GET", "/login?debug=1", 200), ("POST", "/auth", 401),
        ("GET", "/session?token=", 401),
    ]),
    ("bot_traffic", [
        ("GET", "/", 200), ("GET", "/?utm=1", 200),
        ("GET", "/product/1", 200), ("GET", "/cart", 200),
        ("GET", "/checkout", 200),
    ]),
    ("slowloris_like", [
        ("GET", "/", 200), ("GET", "/", 408), ("GET", "/", 408),
        ("GET", "/", 200), ("GET", "/", 503),
    ]),
    ("healthy_api", [
        ("GET", "/api/v1/alerts", 200), ("POST", "/api/v1/alerts", 201),
        ("GET", "/api/v1/health", 200), ("GET", "/api/v1/status", 200),
        ("GET", "/api/v1/metrics", 200),
    ]),
]


# ---------------------------------------------------------------------------
# Structured CSE bundles (canonical CSV schema)
# ---------------------------------------------------------------------------

SECTORS = ["Telecom", "Financial Services", "Power & Energy",
           "Healthcare", "Government"]
SIZES = ["Small", "Medium", "Large"]
CATS = ["malware", "authentication", "network", "endpoint", "database", "web"]
SEVS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
SHALLOW_NOTES = ["Checked.", "Benign.", "Reviewed.", "OK.", "Closed."]
DEEP_NOTES = [
    "Analyzed malware signature against threat intelligence feeds. Verified IOC "
    "hash via sandbox and confirmed no lateral movement across the estate.",
    "Correlated firewall and EDR events, cross-referenced with historical "
    "baseline, and validated against known-good behaviour patterns.",
    "Reviewed authentication logs, confirmed expected behaviour, and checked "
    "for impossible-travel using geo-IP enrichment.",
]


def _csv(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def gen_cse_bundle(idx: int) -> None:
    cse = f"SAMPLE-CSE-{idx:03d}"
    folder = CBUNDLE / cse
    n_alerts = random.randint(8, 20)
    alerts = []
    for i in range(n_alerts):
        ts = _ts(i * 7)
        sev = random.choice(SEVS)
        cat = random.choice(CATS)
        asset = random.choice(ASSETS)
        shallow = random.random() < 0.4
        desc = f"{cat} detection on {asset} ({sev.lower()} severity)"
        alerts.append([f"{cse}-AL-{i:04d}", cse, ts.isoformat(),
                       sev, cat, asset, "closed",
                       (ts + timedelta(minutes=random.randint(1, 30))).isoformat(),
                       desc])

    invs = []
    for i in range(n_alerts):
        al = alerts[i]
        ts_o = _ts(i * 7)
        note = random.choice(SHALLOW_NOTES if random.random() < 0.5 else DEEP_NOTES)
        invs.append([f"{cse}-INV-{i:04d}", al[0], cse,
                     ts_o.isoformat(),
                     (ts_o + timedelta(minutes=random.randint(1, 20))).isoformat(),
                     random.randint(1, 6), f"analyst_{i % 4}", note,
                     round(random.uniform(1.0, 5.0), 1)])

    escs = []
    for i in range(max(1, n_alerts // 4)):
        al = alerts[i]
        ts = _ts(i * 7 + 1)
        escs.append([f"{cse}-ESC-{i:04d}", f"{cse}-INV-{i:04d}", cse,
                     ts.isoformat(), "escalated",
                     random.choice(["true", "false"]),
                     "soc-lead@org", "High-severity alert requires review"])

    cases = []
    for i in range(max(1, n_alerts // 5)):
        al = alerts[i]
        ts = _ts(i * 7 + 2)
        cases.append([f"{cse}-CASE-{i:04d}", cse, json.dumps([al[0]]),
                      "incident", random.choice(SEVS),
                      ts.isoformat(), "Resolved via standard IR process"])

    assets = []
    for a in random.sample(ASSETS, k=random.randint(4, 8)):
        assets.append([a, cse, random.choice(["server", "endpoint", "network_device", "database"]),
                       random.choice(["CRITICAL", "HIGH", "MEDIUM"]),
                       random.choice(["production", "staging"]),
                       random.choice(["monitored", "partially_monitored", "unmonitored"])])

    _csv(folder / "cse_metadata.csv",
         ["cse_id", "name", "sector", "size_band", "claimed_capabilities", "submitted_at"],
         [[cse, f"Sample {SECTORS[idx % len(SECTORS)]} {SIZES[idx % len(SIZES)]}",
           SECTORS[idx % len(SECTORS)], SIZES[idx % len(SIZES)],
           "{}", "2025-01-15"]])
    _csv(folder / "alerts.csv",
         ["alert_id", "cse_id", "timestamp", "severity", "category",
          "asset_id", "status", "closure_timestamp", "description"], alerts)
    _csv(folder / "investigations.csv",
         ["investigation_id", "alert_id", "cse_id", "timestamp_open",
          "timestamp_close", "evidence_entries", "assigned_to", "notes", "depth_score"],
         invs)
    _csv(folder / "escalations.csv",
         ["escalation_id", "investigation_id", "cse_id", "timestamp",
          "decision", "has_followup", "recipient", "rationale"], escs)
    _csv(folder / "cases.csv",
         ["case_id", "cse_id", "related_alerts", "case_type", "severity",
          "closure_time", "resolution"], cases)
    _csv(folder / "assets.csv",
         ["asset_id", "cse_id", "asset_type", "criticality", "environment",
          "monitoring_status"], assets)


def gen_json_bundle(idx: int) -> None:
    cse = f"SAMPLE-JSON-{idx:03d}"
    n = random.randint(6, 12)
    alerts = []
    for i in range(n):
        ts = _ts(i * 6)
        alerts.append({
            "alert_id": f"{cse}-AL-{i:04d}", "cse_id": cse,
            "timestamp": ts.isoformat(), "severity": random.choice(SEVS),
            "category": random.choice(CATS),
            "asset_id": random.choice(ASSETS), "status": "closed",
            "description": f"{random.choice(CATS)} detection (json sample)",
        })
    JDIR.mkdir(parents=True, exist_ok=True)
    (JDIR / f"alerts_{idx:02d}.json").write_text(json.dumps(alerts, indent=2))


def main() -> None:
    SYSL.mkdir(parents=True, exist_ok=True)
    WEB.mkdir(parents=True, exist_ok=True)

    for fname, scenario in SYSL_SAMPLES:
        gen_syslog_file(SYSL / f"{fname}.log", scenario, n=random.randint(15, 40))

    for fname, scenario in WEB_SAMPLES:
        gen_web_sample(WEB / f"{fname}.log", scenario, n=random.randint(15, 40))

    for i in range(1, 6):
        gen_cse_bundle(i)
    for i in range(1, 6):
        gen_json_bundle(i)

    n_sys = len(list(SYSL.glob("*.log")))
    n_web = len(list(WEB.glob("*.log")))
    n_cse = len(list(CBUNDLE.glob("*")))
    n_json = len(list(JDIR.glob("*.json")))
    print(f"Generated: {n_sys} syslog, {n_web} web, {n_cse} CSE bundles, "
          f"{n_json} JSON bundles "
          f"(total scenario samples = {n_sys + n_web + n_cse + n_json})")


if __name__ == "__main__":
    main()
