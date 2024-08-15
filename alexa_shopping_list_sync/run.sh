#!/usr/bin/with-contenv bashio
bashio::log.info "Starting Alexa Shopping List Sync"

# Activate the virtual environment
source /app/venv/bin/activate

python main.py
