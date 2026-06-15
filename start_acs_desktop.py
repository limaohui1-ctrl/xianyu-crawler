#!/usr/bin/env python3
"""ACS Desktop Launcher — 双击启动即可。自动处理端口冲突。"""
import argparse, os, sys, time, subprocess, webbrowser, socket

PROJECT = os.path.dirname(os.path.abspath(__file__))
HOST, PORT = "127.0.0.1", 5020


def port_free(port):
    try:
        s = socket.socket()
        s.settimeout(1)
        s.bind((HOST, port))
        s.close()
        return True
    except OSError:
        return False


def kill_port(port):
    """Kill the process listening on the given port (Windows)."""
    r = subprocess.run(f'netstat -ano | findstr :{port} | findstr LISTENING',
                       shell=True, capture_output=True, text=True, timeout=5)
    for line in r.stdout.strip().split('\n'):
        parts = line.strip().split()
        if parts and parts[-1].isdigit():
            subprocess.run(f'taskkill //F //PID {parts[-1]}',
                           shell=True, capture_output=True, timeout=5)
    time.sleep(1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=PORT)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()

    os.chdir(PROJECT)
    print(f"+==========================================+")
    print(f"|   ACS 资料采集助手                        |")
    print(f"|   v1.3.4-one-click-searxng 安全测试模式   |")
    print(f"+==========================================+")
    print()

    # ── Dependencies ──
    for mod in ["flask", "bs4", "lxml", "requests"]:
        try:
            __import__(mod)
        except ImportError:
            print(f"[ERROR] 缺少依赖: {mod}")
            print(f"  请先运行: pip install -r requirements.txt")
            input("按任意键关闭...")
            sys.exit(1)
    print("[OK] 依赖已满足")

    # ── .env ──
    if not os.path.exists(".env"):
        if os.path.exists(".env.example"):
            print("[WARN] 未发现 .env，正在从 .env.example 复制...")
            with open(".env.example", encoding="utf-8") as src, \
                 open(".env", "w", encoding="utf-8") as dst:
                dst.write(src.read())
            print("[OK] .env 已创建")
        else:
            print("[WARN] 缺少 .env.example")

    # ── SearXNG ──
    try:
        r = subprocess.run(
            'curl -sf http://127.0.0.1:8080/search?q=test&format=json',
            shell=True, capture_output=True, timeout=5
        )
        if r.returncode == 0:
            print("[OK] 本地 SearXNG 已连接")
        else:
            print("[WARN] 本地 SearXNG 未响应")
    except Exception:
        print("[WARN] 未检测到 SearXNG（不影响软件启动）")

    # ── Port auto-clean ──
    if not port_free(args.port):
        print(f"[AUTO] 端口 {args.port} 被占用，自动清理...")
        kill_port(args.port)
        if port_free(args.port):
            print("[OK] 已释放")
        else:
            print(f"[WARN] 无法释放端口 {args.port}，尝试继续...")

    # ── Start server ──
    print(f"[START] 本地服务 http://{HOST}:{args.port}")
    server = subprocess.Popen(
        [sys.executable, "-m", "acs.web.local_server",
         "--port", str(args.port), "--host", HOST],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        cwd=PROJECT,
    )

    # Wait for health
    for _ in range(20):
        try:
            r = subprocess.run(
                f'curl -sf http://{HOST}:{args.port}/api/health',
                shell=True, capture_output=True, timeout=3
            )
            if r.returncode == 0:
                break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        print("[WARN] 服务启动较慢，请稍候...")
        time.sleep(2)

    print("[就绪] ACS 资料采集助手已启动")

    # ── Open browser ──
    if not args.no_browser:
        url = f"http://{HOST}:{args.port}"
        print(f"[OPEN] {url}")
        webbrowser.open(url)

    print()
    print(f"  地址: http://{HOST}:{args.port}")
    print(f"  模式: ACS_MODE=shadow（安全）")
    print(f"  按 Ctrl+C 退出，关闭本窗口也会停止服务")
    print()

    # ── Kill server on exit ──
    import atexit
    atexit.register(lambda: server.kill() if server.poll() is None else None)

    try:
        server.wait()
    except KeyboardInterrupt:
        server.kill()


if __name__ == "__main__":
    main()
