@echo off
rem ---------------------------------------------------------------------------
rem  Nikki4 (閃耀暖暖) daily check-in + reward redemption
rem  Double-click on Windows. First run creates .venv and installs selenium,
rem  then asks for the account e-mail / password if they are not in .env.
rem ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"

if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if /i "%%A"=="NIKKI_EMAIL" set "NIKKI_EMAIL=%%B"
        if /i "%%A"=="NIKKI_PASSWORD" set "NIKKI_PASSWORD=%%B"
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo [setup] Creating virtual environment...
    python -m venv .venv || goto :nopython
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :failed
)

rem Edge ships with Windows 10/11 and supports Chrome-style mobile emulation.
if not defined BROWSER set "BROWSER=edge"
if not defined SE_CACHE_PATH set "SE_CACHE_PATH=%~dp0.selenium"

".venv\Scripts\python.exe" checkin.py %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo Done.
) else (
    echo Finished with exit code %RC%.
    echo Run with DEBUG=1 to keep a screenshot and the page HTML in artifacts\.
)
echo.
pause
exit /b %RC%

:nopython
echo.
echo Python was not found. Install Python 3.9+ from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during setup.
pause
exit /b 1

:failed
echo.
echo Setup failed - see the messages above.
pause
exit /b 1
