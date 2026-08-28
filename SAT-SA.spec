# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['sat_sa_desktop.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['src.api.main', 'src.api.routes', 'src.dashboard.routes', 'src.analytics.schemas', 'src.analytics.profiles', 'src.analytics.profiler', 'src.analytics.signal_engine', 'src.analytics.execution_gaps', 'src.analytics.negative_space', 'src.analytics.behavioral_anomalies', 'src.analytics.peer_deviation', 'src.analytics.scoring', 'src.analytics.expected_evidence', 'src.analytics.fusion', 'src.analytics.benchmarking', 'src.analytics.finding', 'src.evidence.tracer', 'src.evidence.findings', 'src.evidence.llm_explainer', 'src.ingestion.adapters', 'src.ingestion.mapper', 'src.ingestion.normalizer', 'src.ingestion.pipeline', 'src.ingestion.quality', 'src.ingestion.log_parser', 'src.storage.db'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SAT-SA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
