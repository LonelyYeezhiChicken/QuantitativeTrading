@echo off
title Crypto AI Quant Dashboard
cd /d "%~dp0"

echo ==============================================
echo   Starting Crypto AI Quant Dashboard...
echo   Opening in your default browser: http://localhost:8501
echo ==============================================

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m streamlit run apps/dashboard/app.py
) else (
    python -m streamlit run apps/dashboard/app.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Application exited with error code %ERRORLEVEL%.
    pause
)
