# 🚀 Quick Start - Partner Panel Mini App

## For Local Testing (Right Now)

### 1. Start the Bot
```bash
# Make sure you're in the project root
cd c:\Users\User\Desktop\fudly-bot-main

# Start bot with API server
python bot.py
```

### 2. Test Frontend Locally
```bash
# Open new terminal
cd webapp\partner-panel

# Start simple HTTP server
python -m http.server 8080
```

### 3. Update .env (Temporary for Testing)
```bash
# Edit .env file
PARTNER_PANEL_URL=http://localhost:8080
BOT_TOKEN=<your_actual_bot_token>  # Must be set for auth
```

### 4. Test in Telegram
1. Send `/start` to your bot
2. If you're a seller, you'll see "🖥 Веб-панель" button
3. Click it - Mini App will open
4. Test features

---

## For Production Deployment

### Prerequisites
- Vercel account (free)
- Railway deployment (already set up)
- Git repository (already set up)

### Step 1: Deploy Frontend to Vercel
```bash
# Install Vercel CLI
npm install -g vercel

# Login to Vercel
vercel login

# Deploy from project root
cd c:\Users\User\Desktop\fudly-bot-main
vercel --prod

# Follow prompts:
# - Project name: fudly-partner-panel
# - Directory: webapp/partner-panel
```

### Step 2: Set Vercel Environment Variable
In Vercel Dashboard:
1. Go to project settings
2. Environment Variables
3. Add: `API_URL` = `https://fudly-bot-production.up.railway.app`

### Step 3: Update Railway Environment
In Railway Dashboard:
1. Go to your bot service
2. Variables tab
3. Add: `PARTNER_PANEL_URL` = `https://fudly-partner-panel.vercel.app`
4. Confirm `BOT_TOKEN` is set (required for auth)

### Step 4: Update CORS in Code
Edit `app/api/api_server.py`, line ~70:
```python
allow_origins=[
    "https://fudly-partner-panel.vercel.app",  # Add this
    "https://fudly-webapp.vercel.app",
    "https://web.telegram.org",
    "https://telegram.org",
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8080",  # For local testing
    "*",  # Remove this in production for security
],
```

### Step 5: Deploy Backend Changes
```bash
# Commit all changes
git add .
git commit -m "feat: Add partner panel Mini App with API endpoints"
git push origin main

# Railway will auto-deploy
# Wait ~2-3 minutes for deployment
```

### Step 6: Verify Deployment
```bash
# Test API health
curl https://fudly-bot-production.up.railway.app/

# Test frontend loads
curl https://fudly-partner-panel.vercel.app/
```

### Step 7: Test in Telegram
1. Send `/start` to bot
2. Click "🖥 Веб-панель"
3. Mini App opens with your deployed version
4. Test all features

---

## Testing Checklist

### Manual Testing
- [ ] Bot starts without errors
- [ ] "🖥 Веб-панель" button appears for sellers
- [ ] Mini App opens in Telegram
- [ ] Products list loads
- [ ] Can add new product
- [ ] Can edit existing product
- [ ] Can delete product
- [ ] CSV import works with example-products.csv
- [ ] Orders list loads
- [ ] Can confirm/cancel order
- [ ] Stats display correctly
- [ ] Settings form saves

### API Testing
```bash
# Get profile (replace <INIT_DATA> with real Telegram initData)
curl -X GET "https://fudly-bot-production.up.railway.app/api/partner/profile" \
     -H "Authorization: tma <INIT_DATA>"

# List products
curl -X GET "https://fudly-bot-production.up.railway.app/api/partner/products" \
     -H "Authorization: tma <INIT_DATA>"

# Check Swagger docs
# Open: https://fudly-bot-production.up.railway.app/api/docs
```

---

## Troubleshooting

### Bot doesn't show Web Panel button
**Check:**
```bash
# Verify env variable is set
railway variables

# Should see:
# PARTNER_PANEL_URL=https://fudly-partner-panel.vercel.app
# BOT_TOKEN=<your_token>

# Restart bot if needed
railway restart
```

### 401 Authentication Failed
**Check:**
- `BOT_TOKEN` environment variable is set in Railway
- Bot token matches your actual bot
- `init_data` is being sent correctly

### 403 Not a partner
**Fix user role in database:**
```sql
-- Connect to Railway PostgreSQL
railway connect

-- Check user role
SELECT telegram_id, name, role FROM users WHERE telegram_id=YOUR_TELEGRAM_ID;

-- Update to seller if needed
UPDATE users SET role='seller' WHERE telegram_id=YOUR_TELEGRAM_ID;
```

### CORS Error
**Update CORS in `app/api/api_server.py`:**
```python
allow_origins=[
    "https://fudly-partner-panel.vercel.app",  # Make sure this is added
    # ...
]
```
Then redeploy backend:
```bash
git add app/api/api_server.py
git commit -m "fix: Update CORS for partner panel"
git push origin main
```

### CSV Import Not Working
**Check CSV format:**
```csv
title,category,original_price,discount_price,quantity,unit,expiry_date,description
Test Product,fruits,10000,8000,50,кг,2024-12-31,Test description
```
- Must have header row
- Required: title, discount_price, quantity
- Date format: YYYY-MM-DD
- Encoding: UTF-8

---

## Environment Variables Reference

### Railway (Backend)
```bash
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz  # Your bot token
DATABASE_URL=postgresql://...                      # Auto-set by Railway
PARTNER_PANEL_URL=https://fudly-partner-panel.vercel.app
WEBAPP_URL=https://fudly-webapp.vercel.app        # Main customer webapp
```

### Vercel (Frontend)
```bash
API_URL=https://fudly-bot-production.up.railway.app
```

---

## Quick Commands

### Development
```bash
# Start bot locally
python bot.py

# Start frontend locally
cd webapp\partner-panel
python -m http.server 8080

# Check Python syntax
python -m py_compile app\api\partner_panel.py

# Run tests (if you have them)
pytest tests/
```

### Deployment
```bash
# Deploy frontend
vercel --prod

# Deploy backend (via git)
git push origin main

# Check Railway logs
railway logs

# Check Vercel logs
vercel logs
```

### Monitoring
```bash
# Watch API health
watch -n 30 "curl -s https://fudly-bot-production.up.railway.app/ | jq"

# Check Vercel deployment
vercel list

# Check Railway status
railway status
```

---

## Files Reference

### Created Files
- `webapp/partner-panel/index.html` - HTML structure
- `webapp/partner-panel/styles.css` - CSS styling
- `webapp/partner-panel/app.js` - JavaScript logic
- `webapp/partner-panel/README.md` - User documentation
- `webapp/partner-panel/DEPLOYMENT.md` - Deployment guide
- `webapp/partner-panel/QUICK_START.md` - This file
- `webapp/partner-panel/IMPLEMENTATION_SUMMARY.md` - Technical summary
- `webapp/partner-panel/example-products.csv` - CSV template
- `app/api/partner_panel.py` - API endpoints

### Modified Files
- `app/keyboards/seller.py` - Added WebApp button
- `handlers/common/webapp.py` - Added URL helper
- `handlers/common/commands.py` - Added integration
- `app/api/api_server.py` - Registered router
- `vercel.json` - Updated deployment config

---

## Support

- **Documentation**: See README.md in same folder
- **Deployment**: See DEPLOYMENT.md
- **Implementation**: See IMPLEMENTATION_SUMMARY.md
- **Issues**: Check logs (Railway, Vercel, bot console)
- **API Docs**: https://your-api.railway.app/api/docs

---

**Ready to go!** 🎉
Start with local testing, then deploy to production when everything works.
