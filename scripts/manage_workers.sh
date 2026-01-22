# Neurocards Worker Management Script
# Manages multiple worker instances

WORKERS_COUNT=${WORKER_INSTANCES:-20}  # Default 20 workers, можно переопределить через env

# Start all workers
start_all() {
    echo "🚀 Starting $WORKERS_COUNT worker instances..."
    for i in $(seq 1 $WORKERS_COUNT); do
        systemctl start neurocards-worker@$i
    done
    echo "✅ All workers started!"
}

# Stop all workers
stop_all() {
    echo "🛑 Stopping all worker instances..."
    systemctl stop 'neurocards-worker@*'
    echo "✅ All workers stopped!"
}

# Restart all workers
restart_all() {
    echo "🔄 Restarting $WORKERS_COUNT worker instances..."
    for i in $(seq 1 $WORKERS_COUNT); do
        systemctl restart neurocards-worker@$i
    done
    echo "✅ All workers restarted!"
}

# Status of all workers
status_all() {
    echo "📊 Worker instances status:"
    systemctl status 'neurocards-worker@*' --no-pager
}

# Enable all workers to start on boot
enable_all() {
    echo "🔧 Enabling $WORKERS_COUNT worker instances..."
    for i in $(seq 1 $WORKERS_COUNT); do
        systemctl enable neurocards-worker@$i
    done
    echo "✅ All workers enabled for autostart!"
}

# Disable all workers
disable_all() {
    echo "🔧 Disabling all worker instances..."
    for i in $(seq 1 $WORKERS_COUNT); do
        systemctl disable neurocards-worker@$i
    done
    echo "✅ All workers disabled!"
}

# Show logs for all workers
logs_all() {
    echo "📋 Showing logs for all workers (Ctrl+C to exit)..."
    journalctl -u 'neurocards-worker@*' -f
}

# Show logs for specific worker
logs_one() {
    if [ -z "$1" ]; then
        echo "Usage: logs_one <worker_number>"
        return 1
    fi
    echo "📋 Showing logs for worker #$1 (Ctrl+C to exit)..."
    journalctl -u neurocards-worker@$1 -f
}

# Main script
case "${1:-}" in
    start)
        start_all
        ;;
    stop)
        stop_all
        ;;
    restart)
        restart_all
        ;;
    status)
        status_all
        ;;
    enable)
        enable_all
        ;;
    disable)
        disable_all
        ;;
    logs)
        logs_all
        ;;
    logs-one)
        logs_one "$2"
        ;;
    *)
        echo "Neurocards Worker Manager"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|enable|disable|logs|logs-one N}"
        echo ""
        echo "Commands:"
        echo "  start      - Start all $WORKERS_COUNT workers"
        echo "  stop       - Stop all workers"
        echo "  restart    - Restart all workers"
        echo "  status     - Show status of all workers"
        echo "  enable     - Enable workers to start on boot"
        echo "  disable    - Disable workers autostart"
        echo "  logs       - Show logs from all workers (follow mode)"
        echo "  logs-one N - Show logs from worker #N (follow mode)"
        echo ""
        echo "Current configuration: $WORKERS_COUNT workers"
        echo "To change: export WORKER_INSTANCES=30 before running"
        exit 1
        ;;
esac

exit 0
