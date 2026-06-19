#!/bin/bash
# ============================================================================
# Chatbot Core — SSL Setup with Let's Encrypt
# ============================================================================
# Usage: sudo ./setup-ssl.sh chatbot.tu-dominio.com your@email.com
# ============================================================================

set -euo pipefail

DOMAIN="${1:?Error: Domain required. Usage: $0 <domain> <email>}"
EMAIL="${2:?Error: Email required. Usage: $0 <domain> <email>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[SSL]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── Pre-flight checks ──────────────────────────────────────────────────────
log "Checking prerequisites..."

command -v docker &>/dev/null || error "Docker not found."
command -v certbot &>/dev/null || {
    log "Installing Certbot..."
    sudo apt update && sudo apt install -y certbot python3-certbot-nginx
}

# ── Stop Nginx container temporarily ───────────────────────────────────────
log "Stopping Nginx container..."
docker compose -f docker-compose.prod.yml stop nginx 2>/dev/null || true

# ── Get SSL Certificate ────────────────────────────────────────────────────
log "Requesting SSL certificate for $DOMAIN..."

sudo certbot certonly \
    --standalone \
    --preferred-challenges http \
    -d "$DOMAIN" \
    -m "$EMAIL" \
    --agree-tos \
    --non-interactive \
    --keep-until-expiring

log "Certificate obtained successfully!"

# ── Update Nginx Configuration ─────────────────────────────────────────────
log "Updating Nginx configuration..."

# Uncomment SSL lines in nginx.conf
sed -i 's/# listen 443 ssl http2;/listen 443 ssl http2;/' nginx.conf
sed -i "s/# server_name chatbot.tu-dominio.com;/server_name $DOMAIN;/" nginx.conf
sed -i "s|# ssl_certificate /etc/letsencrypt/live/chatbot.tu-dominio.com/fullchain.pem;|ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;|" nginx.conf
sed -i "s|# ssl_certificate_key /etc/letsencrypt/live/chatbot.tu-dominio.com/privkey.pem;|ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;|" nginx.conf

# Uncomment HTTP → HTTPS redirect block
sed -i 's/# server {/server {/' nginx.conf
sed -i "s/#     listen 80;/    listen 80;/" nginx.conf
sed -i "s/#     server_name chatbot.tu-dominio.com;/    server_name $DOMAIN;/" nginx.conf
sed -i 's/#     location \/\.well-known/    location \/\.well-known/' nginx.conf
sed -i 's/#         root \/var\/www\/certbot;/        root \/var\/www\/certbot;/' nginx.conf
sed -i 's/#     }/    }/' nginx.conf
sed -i 's/#     location \/ {/    location \/ {/' nginx.conf
sed -i 's/#         return 301/        return 301/' nginx.conf
sed -i 's/#     }/    }/' nginx.conf

log "Nginx configuration updated."

# ── Create certbot volume mount ────────────────────────────────────────────
log "Setting up certificate permissions..."
sudo mkdir -p /etc/letsencrypt/live/$DOMAIN
sudo chmod -R 755 /etc/letsencrypt

# ── Update docker-compose for SSL ──────────────────────────────────────────
log "Updating Docker Compose for SSL..."

# Add certbot volume mount to nginx service
if ! grep -q "letsencrypt" docker-compose.prod.yml; then
    sed -i '/nginx_cache:\/var\/cache\/nginx/a\      - /etc/letsencrypt:/etc/letsencrypt:ro' docker-compose.prod.yml
    log "Docker Compose updated with SSL volume mount."
fi

# ── Restart Services ───────────────────────────────────────────────────────
log "Restarting services..."
docker compose -f docker-compose.prod.yml up -d nginx

# ── Verify SSL ─────────────────────────────────────────────────────────────
log "Verifying SSL..."
sleep 5

if curl -sf "https://$DOMAIN/health" > /dev/null 2>&1; then
    log "✅ SSL is working! https://$DOMAIN"
else
    warn "⚠️  SSL verification failed. Check logs: docker compose logs nginx"
fi

# ── Auto-renewal Setup ─────────────────────────────────────────────────────
log "Setting up auto-renewal..."

# Create renewal script
cat > /usr/local/bin/chatbot-certbot-renew.sh << 'EOF'
#!/bin/bash
certbot renew --quiet --deploy-hook "docker compose -f /opt/chatbot/docker-compose.prod.yml restart nginx"
EOF

chmod +x /usr/local/bin/chatbot-certbot-renew.sh

# Add to crontab (runs daily at 3am)
(crontab -l 2>/dev/null; echo "0 3 * * * /usr/local/bin/chatbot-certbot-renew.sh") | crontab -

log "Auto-renewal configured (daily at 3:00 AM)"

# ── Summary ────────────────────────────────────────────────────────────────
echo ""
log "SSL Setup Complete!"
echo ""
log "Access your site at:"
log "  https://$DOMAIN/tenant/"
log "  https://$DOMAIN/admin/"
log "  https://$DOMAIN/health"
echo ""
log "Certificate expires on:"
sudo certbot certificates | grep "Expiry Date"
echo ""
warn "Note: HTTP requests will redirect to HTTPS automatically."
