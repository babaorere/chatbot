# Chatbot Core — Runbook (Operations Manual)

## Overview
This runbook contains procedures for operating, troubleshooting, and recovering the Chatbot Core multi-tenant system in production.

## Table of Contents
1. [System Architecture](#system-architecture)
2. [Daily Operations](#daily-operations)
3. [Backup & Restore](#backup--restore)
4. [Troubleshooting](#troubleshooting)
5. [Scaling & Performance](#scaling--performance)
6. [Security](#security)
7. [Emergency Procedures](#emergency-procedures)

---

## System Architecture

### Services
| Service | Port | Health Check | Dependencies |
|---------|------|--------------|--------------|
| Nginx | 80/443 | `wget http://localhost/health` | API |
| FastAPI | 8000 (internal) | `curl http://localhost:8000/health` | PostgreSQL, OpenRouter |
| PostgreSQL | 5432 (shared) | `pg_isready` | None |
| Prometheus | 9090 | `curl http://localhost:9090/-/healthy` | None |
| Grafana | 3000 | `curl http://localhost:3000/api/health` | Prometheus |
| Alertmanager | 9093 | `curl http://localhost:9093/-/healthy` | None |

### Network Topology
```
Internet
    ↓ (ports 80/443)
[ Nginx ] ←→ [ FastAPI ] ←→ [ PostgreSQL (shared with Windmill) ]
    ↓
[ Prometheus ] ←→ [ Grafana ]
    ↓
[ Alertmanager ]
```

---

## Daily Operations

### Service Status
```bash
# Check all services
docker-compose -f docker-compose.prod.yml ps

# Check monitoring stack
docker-compose -f docker-compose.monitoring.yml ps

# View logs (follow)
docker-compose -f docker-compose.prod.yml logs -f
docker-compose -f docker-compose.monitoring.yml logs -f

# View specific service logs
docker-compose -f docker-compose.prod.yml logs -f api
docker-compose -f docker-compose.prod.yml logs -f nginx
```

### Resource Usage
```bash
# Container stats
docker stats

# Image cleanup (weekly)
docker system prune -af --volumes

# Log rotation (handled by Docker json-file driver)
```

### API Metrics
Access Grafana at `http://<host>/monitoring` (default credentials in `.env`):
- Dashboard: "Chatbot Core - System Overview"
- Panels: API status, request rates, error rates, response times, DB connections

---

## Backup & Restore

### Automated Backups
Backups run daily at 2:00 AM via cron (configured in deployment):
```bash
# Manual backup (full)
./scripts/backup.sh full 30   # 30-day retention

# Schema-only backup (for migrations)
./scripts/backup.sh schema 7

# Custom format (pg_restore compatible)
./scripts/backup.sh custom 30
```

### Restore Procedures
```bash
# List available backups
ls -lht /opt/chatbot/backups/

# Restore most recent (requires FORCE=1 for production)
./scripts/restore.sh latest

# Restore specific backup
./scripts/restore.sh /opt/chatbot/backups/chatbot_full_20260521_020000.sql.gz

# Restore to different database (testing)
./scripts/restore.sh latest chatbot_test
```

### Backup Verification
```bash
# Verify backup integrity
gzip -t /opt/chatbot/backups/chatbot_full_*.sql.gz  # for gzipped
pg_restore --list /opt/chatbot/backups/*.dump          # for custom format

# Check latest symlink
ls -l /opt/chatbot/backups/latest
```

### Off-site Sync (if configured)
Backups sync to S3 if `S3_BUCKET` is set in environment:
```bash
# Manual sync test
aws s3 ls s3://your-bucket/backups/
```

---

## Troubleshooting

### API Not Responding (502/504)
```bash
# 1. Check if API container is running
docker-compose -f docker-compose.prod.yml ps api

# 2. Check API logs
docker-compose -f docker-compose.prod.yml logs api --tail 50

# 3. Check health endpoint directly
curl -v http://localhost:8000/health

# 4. Check database connectivity
docker-compose -f docker-compose.prod.yml exec api python -c "
import urllib.request
try:
    urllib.request.urlopen('http://localhost:8000/health')
    print('API healthy')
except Exception as e:
    print(f'API unhealthy: {e}')
"

# 5. Restart if needed
docker-compose -f docker-compose.prod.yml restart api
```

### Database Connection Issues
```bash
# 1. Check PostgreSQL container
docker-compose -f docker-compose.prod.yml ps api  # Note: DB is external

# 2. Test connection from API container
docker-compose -f docker-compose.prod.yml exec api pg_isready -h booking-titanium-wm-db-1 -U windmill

# 3. Check database logs (external - check Windmill logs)
#    On Windmill host: docker logs booking-titanium-wm-db-1

# 4. Verify database exists
docker-compose -f docker-compose.prod.yml exec api psql -h booking-titanium-wm-db-1 -U windmill -d windmill -c \
    "\l" | grep chatbot

# 5. Check connection count
docker-compose -f docker-compose.prod.yml exec api psql -h booking-titanium-wm-db-1 -U windmill -d chatbot -c \
    "SELECT count(*) FROM pg_stat_activity WHERE datname = 'chatbot';"
```

### High Latency / Timeouts
```bash
# 1. Check OpenRouter API status
#    (Requires API key - check logs for provider errors)

# 2. Check database query performance
docker-compose -f docker-compose.prod.yml exec api psql -h booking-titanium-wm-db-1 -U windmill -d chatbot -c \
    "SELECT query, mean_time FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 5;"

# 3. Check Nginx error rates
docker-compose -f docker-compose.prod.yml logs nginx | grep -E "(50[0-9]|timeout)" | tail -20

# 4. Check API worker utilization
docker-compose -f docker-compose.prod.yml top api
```

### Rate Limiting (429 Errors)
```bash
# Check Nginx rate limit status (requires ngx_http_stub_status_module)
#    Or check application logs for rate limit headers

# Temporarily adjust limits in nginx.conf:
#   limit_req_zone $binary_remote_addr zone=chat_limit:10m rate=20r/m;  # increased from 10r/m

# Then reload:
docker-compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

### Backup Failures
```bash
# 1. Check backup logs
ls -lht /opt/chatbot/logs/
cat /opt/botelleria/logs/backup_*.log | tail -50

# 2. Verify disk space
df -h /opt/chatbot/backups

# 3. Verify database connectivity (run backup manually with verbose)
./scripts/backup.sh full 1  # Short retention for testing

# 4. Check pg_dump availability
which pg_dump
pg_dump --version
```

---

## Scaling & Performance

### Vertical Scaling (API)
Adjust resources in `docker-compose.prod.yml`:
```yaml
api:
  deploy:
    resources:
      limits:
        memory: 4096M   # Increased from 2048M
      reservations:
        memory: 2048M   # Increased from 1024M
```

### Horizontal Scaling (API Workers)
The API uses Uvicorn workers (configured via environment):
```bash
# In chatbot_core/.env:
UVICORN_WORKERS=4  # Default, increase based on CPU cores
```

### Database Connection Pool
Adjust in SQLAlchemy configuration:
```bash
# In chatbot_core/.env:
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=30
```

### Caching (Nginx)
Already configured in nginx.conf:
- FastCGI cache for PHP (if applicable)
- Proxy cache for API responses
- Browser caching headers

### CDN Integration
For static files, consider:
1. Uploading frontend/tenant/* and frontend/admin/* to CDN
2. Updating nginx.conf to proxy /tenant/ and /admin/ to CDN origin
3. Setting appropriate Cache-Control headers

---

## Security

### Certificate Renewal (Let's Encrypt)
```bash
# Manual renewal (certbot handles auto-renewal via cron)
sudo certbot renew --dry-run

# Force renewal
sudo certbot force-renewal

# After renewal, reload nginx
docker-compose -f docker-compose.prod.yml exec nginx nginx -s reload
```

### API Key Rotation
```bash
# 1. Update OpenRouter key in .env:
#    OPENROUTER_API_KEY=new_key_here

# 2. Restart API to pick up new key:
docker-compose -f docker-compose.prod.yml restart api

# 3. Verify in logs:
docker-compose -f docker-compose.prod.yml logs api | grep -i openrouter
```

### Database Password Rotation
```bash
# 1. Update password in:
#    - chatbot_core/.env (DB_PASSWORD)
#    - Windmill's PostgreSQL user 'windmill' (external)

# 2. Restart affected services:
docker-compose -f docker-compose.prod.yml restart api
docker-compose -f docker-compose.monitoring.yml restart prometheus  # if scraping DB metrics
```

### Firewall Rules (ufw)
```bash
# Allow only necessary ports
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS
sudo ufw allow 9090/tcp    # Prometheus (internal only - consider restricting)
sudo ufw allow 3000/tcp    # Grafana (internal only)
sudo ufw allow 9093/tcp    # Alertmanager (internal only)

# Default deny
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Enable
sudo ufw enable
```

---

## Emergency Procedures

### Complete Site Outage
1. **Verify**: Check if issue is network-wide or service-specific
2. **Prioritize**: API → Database → Nginx → Monitoring
3. **Communicate**: Status page / stakeholder notification
4. **Restore**: Follow restore procedures from latest known-good backup

### Data Corruption Detected
1. **Isolate**: Take database offline (if possible)
2. **Verify**: Check backup integrity from before corruption window
3. **Restore**: Point-in-time restore to clean database
4. **Validate**: Run application smoke tests
5. **Resume**: Switch traffic to restored instance

### Security Breach
1. **Contain**: Suspect API keys, database credentials
2. **Rotate**: All secrets (API keys, DB passwords, JWT secrets)
3. **Audit**: Log review for unauthorized access
4. **Update**: Security patches, dependencies
5. **Monitor**: Enhanced logging and alerting for 72h

### Monitoring Stack Failure
1. **Verify**: Core services (API/DB) still operational
2. **Restart**: Monitoring containers individually
3. **Repair**: Fix configuration issues
4. **Backfill**: Metrics will have gaps but no data loss
5. **Alert**: Use alternative notification if alertmanager down

---

## Contact Information
- **Primary**: DevOps Team (internal)
- **Escalation**: Platform Engineer (on-call)
- **Vendor**: OpenRouter API support (api@openrouter.ai)
- **Infrastructure**: VPS Provider (console access)

## Revision History
| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-05-21 | Initial release |

---
*Keep this runbook updated with system changes. Review quarterly.*