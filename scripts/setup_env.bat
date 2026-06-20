@echo off
setlocal enabledelayedexpansion

:: ---------------------------------------------------------------
:: setup_env.bat
:: Installs uv (if missing), ensures it's on PATH for this session,
:: then runs "uv sync" from the repository root.
:: ---------------------------------------------------------------

:: Step 1 — check if uv is already available
where uv >nul 2>&1
if %errorlevel% == 0 (
    echo [setup] uv is already installed.
    goto :sync
)

:: Step 2 — install uv via the official PowerShell installer
echo [setup] uv not found. Installing via PowerShell installer...
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
if %errorlevel% neq 0 (
    echo [setup] ERROR: uv installation failed. Check your internet connection.
    exit /b 1
)

:: Step 3 — add the uv install location to PATH for this session
::           The official installer places uv.exe in %USERPROFILE%\.local\bin
set "UV_BIN=%USERPROFILE%\.local\bin"
if exist "%UV_BIN%\uv.exe" (
    set "PATH=%UV_BIN%;%PATH%"
    echo [setup] Added %UV_BIN% to PATH for this session.
    goto :sync
)

:: Fallback: some older installer versions use %LOCALAPPDATA%\uv\bin
set "UV_BIN=%LOCALAPPDATA%\uv\bin"
if exist "%UV_BIN%\uv.exe" (
    set "PATH=%UV_BIN%;%PATH%"
    echo [setup] Added %UV_BIN% to PATH for this session.
    goto :sync
)

echo [setup] ERROR: Could not locate uv.exe after installation.
echo         Please open a new terminal (PATH will be updated) and re-run this script.
exit /b 1

:sync
:: Step 4 — run uv sync from the repository root (one level up from /scripts)
cd /d "%~dp0\.."
echo [setup] Running: uv sync
uv sync
if %errorlevel% neq 0 (
    echo [setup] ERROR: uv sync failed.
    exit /b 1
)

echo.
echo [setup] Done. Virtual environment is ready at .venv\
echo         To activate manually: .venv\Scripts\activate
