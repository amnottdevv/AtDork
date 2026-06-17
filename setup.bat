# AtDork v1.3.2 - Setup Script (PowerShell)
$ErrorActionPreference = "Stop"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  AtDork v1.3.2 - Setup" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# ── Check Python ──────────────────────────────────────────────────────
$python = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $python = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $python = "python3"
}

if (-not $python) {
    Write-Host "[!] Python not found." -ForegroundColor Red
    Write-Host "    Please install Python from https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "    Make sure to check 'Add Python to PATH' during installation." -ForegroundColor Yellow
    pause
    exit 1
}

Write-Host "[√] Python found:" -ForegroundColor Green
& $python --version
Write-Host ""

# ── Check pip ─────────────────────────────────────────────────────────
$pipCheck = & $python -m pip --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] pip not found. Installing pip..." -ForegroundColor Yellow
    & $python -m ensurepip --upgrade
}
Write-Host "[√] pip ready." -ForegroundColor Green
Write-Host ""

# ── Install from pyproject.toml ───────────────────────────────────────
Write-Host "[*] Attempting to install AtDork from pyproject.toml..." -ForegroundColor Yellow
$installResult = & $python -m pip install . --quiet 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "[√] AtDork installed successfully from pyproject.toml!" -ForegroundColor Green
    Write-Host ""
    Write-Host "    You can now run: atdork --version" -ForegroundColor White
} else {
    Write-Host "[!] Could not install from pyproject.toml." -ForegroundColor Yellow
    Write-Host "[*] Falling back to requirements.txt..." -ForegroundColor Yellow
    Write-Host ""

    if (Test-Path "requirements.txt") {
        & $python -m pip install -r requirements.txt
        Write-Host ""
        Write-Host "[√] Dependencies installed from requirements.txt." -ForegroundColor Green
        Write-Host ""
        Write-Host "    You can run: $python atdork.py --version" -ForegroundColor White
    } else {
        Write-Host "[×] requirements.txt not found. Please check your installation." -ForegroundColor Red
        pause
        exit 1
    }
}

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Setup Complete!" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
pause
