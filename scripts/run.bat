@echo off
rem TAKAM-Kal - setup and run in one command (Windows):
rem   scripts\run.bat               full run
rem   scripts\run.bat --check-only  preflight checks only
rem Creates a venv if missing, installs deps, and delegates to scripts\run.py -
rem all the logic (preflight, index, server) lives there, cross-platform.
cd /d "%~dp0.."

if not exist .venv (
    echo Creating virtual environment ^(.venv^)...
    py -m venv .venv 2>nul || python -m venv .venv
)
call .venv\Scripts\pip install --quiet -r requirements.txt
.venv\Scripts\python scripts\run.py %*
