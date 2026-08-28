"""Desktop launcher for SAT-SA."""
import subprocess
import sys
import time
import threading
import webview


def start_server():
    """Start uvicorn server in background thread or subprocess."""
    if getattr(sys, "frozen", False):
        import uvicorn
        from src.api.main import app

        config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
    else:
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "src.api.main:app",
             "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    if not start_server():
        print("Failed to start server")
        sys.exit(1)
    window = webview.create_window(
        "SAT-SA — Supervisory Analytics Tool",
        "http://127.0.0.1:8000/dashboard/",
        width=1280,
        height=800,
        min_size=(1024, 600),
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
