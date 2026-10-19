@echo off
setlocal
chcp 65001 >nul
if "%~3"=="" (
 echo Usage: run_prediction_then_research.bat existing_collector.bat saved.keiba statistics.sqlite
 exit /b 2
)
set "research_collector=%~f1"
set "research_keiba=%~f2"
set "research_stats=%~f3"
if not exist "%research_collector%" exit /b 2
rem The caller explicitly chooses the existing entry point. No existing BAT is edited.
for /f %%T in ('python -c "import time; print(time.time_ns())"') do set "research_started_ns=%%T"
if not defined research_started_ns exit /b 4
call "%research_collector%"
if errorlevel 1 exit /b %errorlevel%
if not exist "%research_keiba%" exit /b 3
python "%~dp0new_ai_research.py" --keiba "%research_keiba%" --stats "%research_stats%" --not-before-ns "%research_started_ns%" --out "%~dp0..\research\predictions.sqlite" --export-dir "%~dp0..\research\portable" --bundle-dir "%~dp0..\research\bundles"
exit /b %errorlevel%
