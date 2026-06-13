# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # ── core libraries ──
        'universal_core',
        'core_urls',
        'core_export',
        'core_database',
        'core_ai_storage',
        'core_firecrawl',
        'core_firecrawl_flow',
        'core_nl_web_crawler',

        # ── universal self-test suite ──
        'universal_self_test',
        'universal_self_test_ai_flow',
        'universal_self_test_ai_history',
        'universal_self_test_launchers',
        'universal_self_test_queue',
        'universal_self_test_results',
        'universal_self_test_runtime',
        'universal_self_test_ui_smoke',

        # ── UI workers ──
        'ui_workers',

        # ── UI: AI & settings ──
        'ui_ai_settings',
        'ui_ai_runtime',
        'ui_ai_wizard',
        'ui_ai_buttons',
        'ui_ai_preview',

        # ── UI: AI actions & results ──
        'ui_ai_actions',
        'ui_ai_nl',
        'ui_ai_quality',
        'ui_ai_results',
        'ui_ai_table',

        # ── UI: collection runtime ──
        'ui_collect_runtime',
        'ui_preflight',

        # ── UI: detail & preview ──
        'ui_detail_panel',
        'ui_detail_panel_runtime',
        'ui_preview_quality',
        'ui_subpages',

        # ── UI: diagnostics & quality ──
        'ui_diagnostics',
        'ui_quality',

        # ── UI: exports & files ──
        'ui_exports',
        'ui_export_utils',
        'ui_file_actions',

        # ── UI: firecrawl integration ──
        'ui_firecrawl',

        # ── UI: history & changes ──
        'ui_history',
        'ui_history_change',
        'ui_ai_history',

        # ── UI: logging ──
        'ui_logging',

        # ── UI: overview & navigation ──
        'ui_overview',

        # ── UI: queue management ──
        'ui_queue',

        # ── UI: records & memory ──
        'ui_records_memory',

        # ── UI: result tables ──
        'ui_result_tables',

        # ── UI: run archive ──
        'ui_run_archive',

        # ── UI: schedules ──
        'ui_schedules',

        # ── UI: simple collect & results ──
        'ui_simple_collect',
        'ui_simple_results',

        # ── UI: strategy ──
        'ui_strategy',

        # ── UI: tab construction ──
        'ui_task_tab',
        'ui_template_tab',

        # ── UI: template operations ──
        'ui_template_ops',

        # ── UI: two-click & wizard ──
        'ui_two_click',
        'ui_wizard_plan',
        'ui_wizard_runtime',
        'ui_wizard_scene',

        # ── UI: worker runtime ──
        'ui_worker_runtime',

        # ── legacy xianyu compatibility (--xianyu) ──
        'legacy_xianyu.app_core',
        'legacy_xianyu.cache_tools',
        'legacy_xianyu.notifications',
        'legacy_xianyu.process_tools',
        'legacy_xianyu.rules',
        'legacy_xianyu.self_test',
        'legacy_xianyu.storage',
        'legacy_xianyu.ui',
        'legacy_xianyu.worker',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'numpy',
        'pandas',
        'sklearn',
        'scipy',
        'matplotlib',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='通用网站采集中心',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='通用网站采集中心',
)
