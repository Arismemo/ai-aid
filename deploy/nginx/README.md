# Nginx site config for ai-aid

## Install

```bash
sudo cp deploy/nginx/ai-aid.conf /etc/nginx/sites-available/ai-aid.conf
sudo ln -sf /etc/nginx/sites-available/ai-aid.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Edit `server_name` first (change `ai-aid.your-domain.example` to your real
hostname).

## HTTPS

For HTTPS, use [certbot](https://certbot.eff.org/):
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d ai-aid.your-domain.com
```
Certbot will edit the config in place and add `ssl_*` directives. The SSE
location continues to work unchanged.

## Why these specific knobs

- `proxy_buffering off` — without this, Nginx buffers SSE frames and delivers
  them to the browser in batches with multi-second latency.
- `proxy_read_timeout 24h` — default 60s would cut idle SSE connections.
- `proxy_http_version 1.1` + `Connection ""` — keeps the upstream connection
  alive, required for SSE.
- `client_max_body_size 256k` — slightly above the server's own 100KB cap so
  Nginx returns the right code (413) on egregiously oversized requests
  before they reach the app.

## Verifying

After reload:
```bash
curl -s -i https://ai-aid.your-domain.com/health   # expect 200 + JSON
curl -s -N https://ai-aid.your-domain.com/events?max_seconds=2  # expect text/event-stream
```
