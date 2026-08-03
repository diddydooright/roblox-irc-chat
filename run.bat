@echo off
setlocal

echo Checking for Python...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed.
    echo Please install Python 3.13+ and try again.
    echo Opening Python 3.13 Microsoft Store link.
    start "" "https://apps.microsoft.com/detail/9PNRBTZXMB4Z?hl=en-us&gl=US&ocid=pdpshare"
    pause
    exit /b 1
)

echo Checking for required packages...

:: Check and install irc
python -c "import irc" 2>nul
if %errorlevel% neq 0 (
    echo Installing irc...
    python -m pip install irc
) else (
    echo irc already installed.
)

:: Check and install PySide6
python -c "import PySide6" 2>nul
if %errorlevel% neq 0 (
    echo Installing PySide6...
    python -m pip install PySide6
) else (
    echo PySide6 already installed.
)

echo Running your script...
python roblox_chat_overlay.py

endlocal
