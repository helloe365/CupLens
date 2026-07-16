# CupLens deployment

CupLens uses one multi-stage image. Node 20 builds the React application, then
Python 3.11 runs one Uvicorn worker and serves both the API and the compiled SPA.
The production container reads committed snapshots only and never trains a model.

## WSL public-ingress architecture

For the three-day competition review window, CupLens runs only in the current
WSL Docker environment. The cloud server is a lightweight public ingress:

```text
public :80 -> Nginx -> server 127.0.0.1:18080
           -> SSH reverse tunnel -> WSL 127.0.0.1:18080
           -> CupLens container :8000
```

Both port 18080 listeners are loopback-only. Nginx is the only public listener,
and the cloud server does not build or run CupLens.

## Local verification

Docker Compose binds WSL loopback port 18080:

```bash
docker compose config -q
docker compose up -d --build
docker compose ps
curl --fail http://127.0.0.1:18080/api/health
curl --fail http://127.0.0.1:18080/api/snapshots/latest
curl --fail http://127.0.0.1:18080/
```

The service is ready only when `docker compose ps` reports `healthy`. The health
response must contain `status: ok` and a non-empty `snapshot_id`. Template mode
remains available when `DASHSCOPE_API_KEY` is empty.

Stop the local service without deleting the image:

```bash
docker compose down
```

## Reverse tunnel

The WSL SSH client creates the connection outbound, so company Wi-Fi does not
need to accept inbound traffic. Use an approved key-authenticated SSH account;
never store a password in a command, file, or screenshot.

When the SSH key is stored on Windows, run the repository's PowerShell
supervisor. It uses Windows OpenSSH, keeps the server listener loopback-only,
and reconnects five seconds after an SSH process exits:

```powershell
$supervisor = Start-Process `
  -FilePath "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" `
  -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "C:\path\to\CupLens\deploy\windows\cuplens-tunnel-supervisor.ps1",
    "-IdentityFile", "C:\path\to\approved-key",
    "-RemoteHost", "user@47.108.64.133"
  ) `
  -WindowStyle Hidden `
  -PassThru
$supervisor.Id
```

Verify from the server side before enabling Nginx:

```bash
ssh aliyun_22 \
  'curl --fail --max-time 10 http://127.0.0.1:18080/api/health'
```

The server SSH daemon must allow TCP forwarding. `GatewayPorts` is not required
because the forwarded listener stays on server loopback.

## Server ingress

The target server remains Ubuntu with a reachable SSH administration port.
Install Nginx only when it is absent:

```bash
ssh aliyun_22 \
  'command -v nginx || { sudo apt-get update && sudo apt-get install -y nginx; }'
```

Inspect existing port-80 sites before making changes. Do not replace an
unrelated live application:

```bash
ssh aliyun_22 \
  'sudo nginx -T 2>/dev/null | grep -nE "listen .*80|default_server|server_name" | head -80'
```

Upload and enable the repository configuration:

```bash
scp deploy/nginx/cuplens.conf aliyun_22:/tmp/cuplens.conf
ssh aliyun_22 '
  set -eu
  sudo install -m 0644 /tmp/cuplens.conf /etc/nginx/sites-available/cuplens
  if [ -L /etc/nginx/sites-enabled/default ]; then
    sudo unlink /etc/nginx/sites-enabled/default
  fi
  sudo ln -sfn /etc/nginx/sites-available/cuplens /etc/nginx/sites-enabled/cuplens
  sudo nginx -t
  sudo systemctl enable --now nginx
  sudo systemctl reload nginx
'
```

The Alibaba Cloud security group must allow inbound TCP 80. Keep port 18080
closed publicly and do not broaden SSH access.

## Three-day operation

- Keep the Windows computer powered and connected to the company Wi-Fi.
- Disable Windows sleep and automatic shutdown for the review window.
- After a Windows, WSL, Docker, server, or network restart, recheck the local
  container, tunnel, server loopback health, and public health endpoint.
- The PowerShell supervisor reconnects after brief network interruptions, but
  it must be started again after Windows restarts.
- An empty or failed DashScope configuration continues to use deterministic
  template responses.

Check service health:

```bash
docker compose ps
curl --fail http://127.0.0.1:18080/api/health
ssh aliyun_22 \
  'curl --fail http://127.0.0.1:18080/api/health'
curl --fail http://47.108.64.133/api/health
```

## Shutdown and rollback

After the competition, stop only the PowerShell process running the CupLens
supervisor, disable the CupLens Nginx site, and stop the local container:

```powershell
Get-CimInstance Win32_Process |
  Where-Object {
    $_.Name -eq "powershell.exe" -and
    $_.CommandLine -like "*cuplens-tunnel-supervisor.ps1*"
  } |
  ForEach-Object { Stop-Process -Id $_.ProcessId }
```

```bash
ssh aliyun_22 '
  sudo unlink /etc/nginx/sites-enabled/cuplens
  if [ -f /etc/nginx/sites-available/default ]; then
    sudo ln -sfn /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default
  fi
  sudo nginx -t
  sudo systemctl reload nginx
'
docker compose down
```

## Alternative server prerequisites

Target: Ubuntu 24.04 LTS, 2 CPU cores, 2 GB RAM, 40 GB disk, plus 2 GB swap.
These commands are for running CupLens directly on a server and are not used by
the WSL reverse-tunnel deployment:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git ufw
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw --force enable
```

After signing in again, verify:

```bash
docker version
docker compose version
free -h
sudo ufw status
```

## Secret handling and deployment

Transfer the project through an approved private Git remote or `scp`. Never copy
a developer `.env`, Git credentials, Qoder private conversations, or terminal
history into the image or deployment archive.

Create the server `.env` interactively. The key is not echoed and the resulting
file is owner-readable only:

```bash
umask 077
read -rsp "DashScope API key: " DASHSCOPE_API_KEY
printf '\nDASHSCOPE_API_KEY=%s\n' "$DASHSCOPE_API_KEY" > .env
unset DASHSCOPE_API_KEY
chmod 600 .env
docker compose up -d --build
```

Optional public configuration belongs in the same ignored file:

```dotenv
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus
```

## Public smoke test

From WSL, replace the placeholder only in the local shell. Do not save private
addresses or credentials in committed documentation:

```bash
read -rp "Server public IP: " SERVER_IP
for path in /api/health /api/snapshots/latest /; do
  curl --fail --max-time 10 "http://${SERVER_IP}${path}"
done
unset SERVER_IP
```

Open the public site in a signed-out desktop browser. Confirm all three Web views
load, `ACTUAL` and `FORECAST` remain distinct, and template mode still works
without Qwen. Before any screenshot, remove keys, private paths, terminal history,
identity details, and any IP that should not be public.

## Evidence checklist

- `docker compose ps` shows the single `cuplens` service as healthy.
- Local health, latest snapshot, and SPA paths return HTTP 200.
- Server Docker, swap, firewall, and container health are visible without secrets.
- The three public paths pass from WSL.
- The homepage and all three Web views pass in a signed-out desktop browser.
- Qoder deployment notes and screenshots are saved only after privacy review.
