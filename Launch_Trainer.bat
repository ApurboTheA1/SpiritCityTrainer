@echo off
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
    python -B spirit_city_trainer.py
) else (
    py -3 -B spirit_city_trainer.py
)
if errorlevel 1 pause
