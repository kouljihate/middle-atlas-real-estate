@echo off
REM Start the app against Neon Postgres (Command Prompt version).
REM Paste the RAW Neon connection string when asked - the app converts
REM the scheme automatically. Nothing is saved to disk.
setlocal
if "%DATABASE_URL%"=="" (
  set /p DATABASE_URL="Paste Neon URL (postgresql://...?sslmode=require): "
)
if "%MAC_FILTER_ENABLED%"=="" set MAC_FILTER_ENABLED=false
if "%PORT%"=="" set PORT=5000
venv\Scripts\python.exe run.py
