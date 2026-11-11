#!/bin/bash

BASE_DIR="/home/oscar/sw/filebrowser"
PROCESS="/usr/local/bin/filebrowser"
DB="$BASE_DIR/filebrowser.db"

LOGFILE="$BASE_DIR/watchdog_filebrowser.log"
APP_LOG="$BASE_DIR/filebrowser.log"

if pgrep -x filebrowser > /dev/null; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - filebrowser ya está ejecutándose" >> "$LOGFILE"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - filebrowser NO está ejecutándose. Arrancando..." >> "$LOGFILE"

    nohup "$PROCESS" -d "$DB" >> "$APP_LOG" 2>&1 &

    sleep 2

    if pgrep -x filebrowser > /dev/null; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - filebrowser arrancado correctamente" >> "$LOGFILE"
    else
        echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR al arrancar filebrowser" >> "$LOGFILE"
    fi
fi
