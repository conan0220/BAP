@echo off
setlocal

set "REPO_ROOT=%~dp0"
set "PYTHON_EXE=%REPO_ROOT%.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [BAP] Cannot find the project Python environment:
    echo       %PYTHON_EXE%
    echo.
    echo Run "uv sync --all-extras --group dev" in the repository root first.
    exit /b 1
)

pushd "%REPO_ROOT%" >nul
"%PYTHON_EXE%" -m bap_desktop.app %*
set "APP_EXIT_CODE=%ERRORLEVEL%"
popd >nul

exit /b %APP_EXIT_CODE%
