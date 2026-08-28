# SAT-SA

Supervisory Analytics Tool for SOC Assessment — Smart India Hackathon 2026 (SIH26157, NCIIPC).

## Prerequisites

- Python 3.10+
- `pip`
- Linux (for building the bundled executable)
- GTK/WebKit runtime libraries (for `pywebview` GUI on Linux)

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run (development)

```bash
# Start API server
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# Open dashboard
# Browser: http://localhost:8000/dashboard/
```

Or use the Makefile:

```bash
make setup
make run
```

## Run (desktop launcher)

```bash
source venv/bin/activate
python sat_sa_desktop.py
```

This starts the FastAPI backend and opens the dashboard in a native desktop window via `pywebview`.

## Run tests

```bash
make test
```

Or directly:

```bash
source venv/bin/activate
pytest tests/ -v --tb=short
```

## Build standalone executable

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name SAT-SA sat_sa_desktop.py
```

The output binary is placed in `dist/SAT-SA`.

### Notes on the executable

- The build above produces a **Linux ELF binary** (`dist/SAT-SA`) because the build host is Linux.
- To produce a Windows `.exe`, run the same PyInstaller command on a Windows machine or use Wine with a Windows Python environment.
- The bundled executable contains the full application and server runtime. No separate Python installation is required on the target machine, but the system must have the shared libraries required by `pywebview` (e.g., `libwebkit2gtk` on Debian/Ubuntu).

## Project structure

```
src/
  api/          # FastAPI backend
  analytics/    # Supervisory analytics engines
  evidence/     # Evidence tracing and findings
  ingestion/    # Data ingestion adapters
  storage/      # Database layer
  dashboard/    # Jinja2 + vanilla JS dashboard
tests/          # Pytest suite
scripts/        # Data generation and pipeline scripts
```
