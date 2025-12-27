#!/bin/bash
# Build script for Vercel deployment
# Generates config.js with proper API base URL

PARTNER_API_BASE="${PARTNER_API_BASE:-https://fudly-bot-production.up.railway.app}"

echo "Building partner panel..."
echo "API Base URL: $PARTNER_API_BASE"

# Generate config.js
cat > config.js << EOF
window.PARTNER_API_BASE = window.PARTNER_API_BASE || '$PARTNER_API_BASE';
EOF

echo "✅ Build complete!"
