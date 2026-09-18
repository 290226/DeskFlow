@echo off
rem DeskFlow launcher: double-click this file to start the app.
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [DeskFlow] Python was not found on PATH.
    echo           Install Python 3.9 or newer from https://www.python.org/downloads/
    pause
    exit /b 1
)

python -c "import PySide6" >nul 2>nul
if errorlevel 1 (
    echo [DeskFlow] First run: installing PySide6, this may take a minute...
    python -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 (
        echo [DeskFlow] Could not install PySide6. Check your network or run manually:
        echo           python -m pip install PySide6
        pause
        exit /b 1
    )
)

python main.py %*
if errorlevel 1 (
    echo.
    echo [DeskFlow] The app exited with an error. See the messages above.
    pause
)

endlocal
