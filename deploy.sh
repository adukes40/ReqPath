#!/bin/bash
# =============================================================================
# Deploy code to LXC container
# Run this from your local machine where the code lives
# =============================================================================

# Configuration
LXC_IP="${1:-}"
APP_DIR="/opt/procurement-api"

if [ -z "$LXC_IP" ]; then
    echo "Usage: ./deploy.sh <lxc-ip-address>"
    echo "Example: ./deploy.sh 192.168.1.100"
    exit 1
fi

echo "Deploying to $LXC_IP..."

# Create tar of app directory
echo "Creating archive..."
tar -czf /tmp/procurement-app.tar.gz app/

# Copy to server
echo "Copying files..."
scp /tmp/procurement-app.tar.gz root@$LXC_IP:/tmp/

# Extract and restart
echo "Extracting and restarting service..."
ssh root@$LXC_IP << 'ENDSSH'
cd /opt/procurement-api
rm -rf app/
tar -xzf /tmp/procurement-app.tar.gz
chown -R procurement:procurement app/
systemctl restart procurement-api
sleep 2
systemctl status procurement-api --no-pager
ENDSSH

# Cleanup
rm /tmp/procurement-app.tar.gz

echo ""
echo "Deployment complete!"
echo "API: http://$LXC_IP"
echo "Docs: http://$LXC_IP/docs"
