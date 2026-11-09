#!/bin/bash

BASE_DIR="/home/oscar/sw/comunidad_energetica_analisis"
VENV="/home/oscar/sw/envs/.api"
PROCESS="uvicorn api36:app --host 0.0.0.0 --port 8000 --reload"

LOGFILE="$BASE_DIR/watchdog_uvicorn.log"
UVICORN_LOG="$BASE_DIR/uvicorn.log"

if pgrep -f "$PROCESS" > /dev/null 2>&1; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - uvicorn ya está ejecutándose" >> "$LOGFILE"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - uvicorn NO está ejecutándose. Arrancando..." >> "$LOGFILE"

    nohup bash -c "
        cd '$BASE_DIR' || exit 1
        source '$VENV/bin/activate'
        exec uvicorn api36:app --host 0.0.0.0 --port 8000 --reload
    " >> "$UVICORN_LOG" 2>&1 &

    echo "$(date '+%Y-%m-%d %H:%M:%S') - uvicorn arrancado" >> "$LOGFILE"
fi

