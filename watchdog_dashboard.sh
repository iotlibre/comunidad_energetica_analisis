#!/bin/bash

BASE_DIR="/home/oscar/sw/comunidad_energetica_analisis"
VENV="/home/oscar/sw/envs/.dash"
PROCESS="streamlit run dashboard/app.py --server.port 8501"

LOGFILE="$BASE_DIR/watchdog_dashboard.log"
APP_LOG="$BASE_DIR/dashboard.log"

if pgrep -f "$PROCESS" > /dev/null 2>&1; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - dashboard ya está ejecutándose" >> "$LOGFILE"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - dashboard NO está ejecutándose. Arrancando..." >> "$LOGFILE"

    nohup bash -c "
        cd '$BASE_DIR' || exit 1
        source '$VENV/bin/activate'
        exec streamlit run dashboard/app.py --server.port 8501
    " >> "$APP_LOG" 2>&1 &

    echo "$(date '+%Y-%m-%d %H:%M:%S') - dashboard arrancado" >> "$LOGFILE"
fi

