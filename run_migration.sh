#!/bin/bash
# Railway migration script
# This will be executed inside Railway container

echo "============================================"
echo "   UNIFIED OFFERS SCHEMA MIGRATION"
echo "============================================"

# Step 1: Check current version
echo ""
echo "📋 Step 1: Checking current version..."
alembic current || echo "⚠️  No current version (first migration?)"

# Step 2: Show migration plan
echo ""
echo "📝 Step 2: Showing migration SQL..."
alembic upgrade 003_unified_schema --sql | head -100

# Step 3: Apply migration
echo ""
echo "🚀 Step 3: Applying migration..."
alembic upgrade head

# Step 4: Verify
echo ""
echo "🔍 Step 4: Verifying..."
alembic current

echo ""
echo "✅ Done!"
