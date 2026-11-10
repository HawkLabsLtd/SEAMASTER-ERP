#!/bin/bash
# SSL Certificate setup script for SeaMaster
# Run as root or with sudo

DOMAIN="portal.example.com"  # Change to your domain
EMAIL="admin@example.com"    # Change to your email

# Install certbot
if ! command -v certbot &> /dev/null; then
    echo "Installing certbot..."
    sudo apt update
    sudo apt install -y certbot python3-certbot-nginx
fi

# Stop Nginx temporarily
sudo systemctl stop nginx

# Obtain SSL certificate
echo "Obtaining SSL certificate for $DOMAIN..."
sudo certbot certonly --standalone \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    --domains "$DOMAIN" \
    --preferred-challenges http

# Start Nginx again
sudo systemctl start nginx

# Set up automatic renewal
echo "Setting up automatic certificate renewal..."
# Test renewal
sudo certbot renew --dry-run

# Add cron job for renewal (if not already present)
if ! crontab -l | grep -q "certbot renew"; then
    (crontab -l 2>/dev/null; echo "0 12 * * * /usr/bin/certbot renew --quiet") | crontab -
    echo "Added certbot renewal cron job"
fi

echo "SSL setup complete!"
echo "Certificate location: /etc/letsencrypt/live/$DOMAIN/"
echo "Remember to uncomment SSL sections in Nginx config!"