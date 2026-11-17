@echo off
rem Starts the barrier-audit app with Anaconda's Python. Double-click me.
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "PY="
for %%P in (
    "%USERPROFILE%\anaconda3\python.exe"
    "%USERPROFILE%\Anaconda3\python.exe"
    "%USERPROFILE%\miniconda3\python.exe"
    "%LOCALAPPDATA%\anaconda3\python.exe"
    "%LOCALAPPDATA%\miniconda3\python.exe"
    "%LOCALAPPDATA%\Continuum\anaconda3\python.exe"
    "%ProgramData%\anaconda3\python.exe"
    "%ProgramData%\Anaconda3\python.exe"
    "%ProgramData%\miniconda3\python.exe"
    "C:\anaconda3\python.exe"
    "C:\Anaconda3\python.exe"
) do (
    if not defined PY if exist %%P set "PY=%%~P"
)

rem Fall back to a python on PATH, skipping the Microsoft Store stub.
if not defined PY (
    for /f "delims=" %%W in ('where python 2^>nul') do (
        if not defined PY (
            echo %%W | find /i "WindowsApps" >nul || set "PY=%%W"
        )
    )
)

if not defined PY (
    echo Could not find Anaconda's Python.
    echo.
    echo Please open "Anaconda Prompt" from the Start menu and type these two lines:
    echo     cd /d "%~dp0"
    echo     python -m barrier_audit
    echo.
    pause
    exit /b 1
)

rem Anaconda's DLLs, in case this Python was never "activated".
for %%D in ("!PY!") do set "PYDIR=%%~dpD"
set "PATH=!PYDIR!;!PYDIR!Library\bin;!PYDIR!Scripts;%PATH%"

echo Using !PY!
"!PY!" -m barrier_audit %*
echo.
pause
