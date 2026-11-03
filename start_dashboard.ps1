# PowerShell Launcher for AI Quant Dashboard
Set-Location $PSScriptRoot
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  Starting AI Quantitative Trading Dashboard..." -ForegroundColor Green
Write-Host "  Browser URL: http://localhost:8501" -ForegroundColor Yellow
Write-Host "===================================================" -ForegroundColor Cyan
python -m streamlit run app.py
