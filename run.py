import os
import sys


def _env_dir() -> str:
    """Directory where `.env` lives: next to the .exe when frozen, else project root."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(os.path.join(_env_dir(), ".env"))


_load_env()

# Dev: project root on path. Frozen: PyInstaller extracts here; `backend` package resolves.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.app import create_app

app = create_app()


def main() -> None:
    host = os.environ.get("APP_HOST", "127.0.0.1")
    port = int(os.environ.get("APP_PORT", "5000"))
    use_dev = os.environ.get("APP_USE_DEV_SERVER", "").lower() in ("1", "true", "yes")

    if use_dev:
        app.run(host=host, port=port, threaded=True)
        return

    from waitress import serve

    threads = int(os.environ.get("WAITRESS_THREADS", "4"))
    serve(app, host=host, port=port, threads=threads)


if __name__ == "__main__":
    main()
