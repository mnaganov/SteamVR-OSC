@echo off
rem Double-click wrapper for start-headtracker.ps1. Extra arguments are passed on to the bridge,
rem for example:  start-headtracker.cmd --front=+y --port 9001
rem The window stays open (pause) only if the launcher or the bridge ended with an error.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-headtracker.ps1" %*
set "HT_RC=%ERRORLEVEL%"
if not "%HT_RC%"=="0" (
    echo.
    echo The head tracker launcher ended with an error ^(exit code %HT_RC%^). See the messages above.
    pause
)
exit /b %HT_RC%
