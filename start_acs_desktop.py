#!/usr/bin/env python3
"""ACS Desktop Launcher — one-click start for 资料采集助手.

Usage: python start_acs_desktop.py [--port 5020] [--no-browser]
"""
import argparse
import os
import sys
import time


def main():
    p = argparse.ArgumentParser(description="ACS 资料采集助手 桌面启动器")
    p.add_argument("--port", type=int, default=5020, help="本地服务端口 (默认: 5020)")
    p.add_argument("--host", default="127.0.0.1", help="绑定地址 (默认: 127.0.0.1)")
    p.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    p.add_argument("--timeout", type=int, default=30, help="等待服务就绪超时秒数")
    args = p.parse_args()

    print("+==========================================+")
    print("|   ACS 资料采集助手                        |")
    print("|   v1.1.2-desktop-polish 安全测试模式       |")
    print("+==========================================+")
    print()

    # Set project root
    project_root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_root)
    print(f"[PROJECT] {project_root}")

    # Check Python
    print(f"[ENV] Python {sys.version.split()[0]}")

    # Check dependencies
    missing = []
    for mod in ["flask", "bs4", "lxml", "requests"]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        print(f"[ERROR] 缺少依赖: {', '.join(missing)}")
        print(f"  请运行: pip install -r requirements.txt")
        sys.exit(1)
    print("[OK] 依赖已满足")

    # Check port
    from acs.web.server_launcher import check_port
    if not check_port(args.port):
        print(f"[ERROR] 端口 {args.port} 已被占用。")
        print(f"  请先关闭占用 {args.port} 端口的程序，再重新启动。")
        sys.exit(1)

    # Start server in background
    import subprocess
    import threading

    print(f"[START] 正在启动本地服务 {args.host}:{args.port} ...")
    print(f"[MODE] ACS_MODE=shadow（安全测试模式）")

    server_proc = subprocess.Popen(
        [sys.executable, "-m", "acs.web.local_server",
         "--port", str(args.port), "--host", args.host],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, cwd=project_root,
    )

    # Monitor server output in background
    def _log_output():
        for line in server_proc.stdout:
            line = line.rstrip()
            if "running on" in line.lower() or "ACS_MODE" in line:
                print(f"[服务] {line}")

    t = threading.Thread(target=_log_output, daemon=True)
    t.start()

    # Wait for health
    from acs.web.server_launcher import wait_for_health
    health_url = f"http://{args.host}:{args.port}/api/health"
    print(f"[等待] 等待服务就绪 ({health_url}) ...")

    if wait_for_health(health_url, timeout=args.timeout):
        print("[就绪] 服务已启动")
    else:
        print(f"[WARN] 服务未在 {args.timeout} 秒内就绪，请检查")
        if server_proc.poll() is not None:
            print("[ERROR] 服务进程已退出")
            sys.exit(1)

    # Open browser
    if not args.no_browser:
        from acs.web.browser_open import open_browser
        index_html = os.path.join(project_root, "acs_ui", "index.html")
        print(f"[OPEN] 正在打开 {index_html} ...")
        open_browser(index_html)

    print()
    print("==========================================")
    print(f"  ACS 资料采集助手已启动")
    print(f"  本地地址: http://{args.host}:{args.port}")
    print(f"  安全模式: ACS_MODE=shadow")
    print(f"  真实生产: 未启用")
    print("==========================================")
    print()
    print("按 Ctrl+C 退出...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[EXIT] 正在停止服务...")
        server_proc.terminate()
        server_proc.wait(timeout=5)
        print("[EXIT] 已停止。")


if __name__ == "__main__":
    main()
