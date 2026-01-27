import paramiko

HOST='185.93.108.162'
USER='root'
PASS='rgew92341'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=15)
print('🔌 Connected to', HOST)

def run(cmd):
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    print(f'CMD: {cmd}\nOUT: {out}\nERR: {err}\n---')

# Stop bot & workers
run('pkill -f "neurocards.*bot" || true')
run('pkill -f "main_polling.py" || true')
run('systemctl stop neurocards-bot || true')
run('systemctl stop "neurocards-worker@*" || true')

# Enable only worker@1 and restart
run('systemctl disable "neurocards-worker@*" || true')
run('systemctl enable neurocards-worker@1')
run('systemctl restart neurocards-worker@1')
run('systemctl restart neurocards-bot')

# Status
run('systemctl is-active --quiet neurocards-bot && echo "Bot: active" || echo "Bot: failed"')
run('systemctl is-active --quiet neurocards-worker@1 && echo "Worker1: active" || echo "Worker1: failed"')

# Quick DB check
run('sudo -u postgres psql -d neurocards -c "SELECT tg_user_id, credits FROM users ORDER BY created_at DESC LIMIT 5;"')

client.close()
print('✅ Remote ops complete.')
