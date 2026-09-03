@echo off
title Prompt Token Optimizer - Local Server
where ollama >nul 2>nul
if errorlevel 1 (echo Ollama not found. Install Ollama first.&pause&exit /b 1)
ollama pull qwen2.5:3b
python -m pip install -r requirements.txt -q
python server.py
pause