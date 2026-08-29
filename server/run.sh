#!/usr/bin/env bash
set -e
command -v ollama >/dev/null || { echo 'Install Ollama first.'; exit 1; }
ollama pull qwen2.5:3b
python3 server.py
