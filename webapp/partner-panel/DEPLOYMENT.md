# Partner Panel Mini App - Deployment Checklist

## ✅ Pre-Deployment Checklist

### 1. Code Review
- [x] HTML structure complete (`index.html`)
- [x] CSS styling with Telegram theme (`styles.css`)
- [x] JavaScript logic implemented (`app.js`)
- [x] API endpoints created (`app/api/partner_panel.py`)
- [x] API registered in `app/api/api_server.py`
- [x] Bot keyboard updated (`app/keyboards/seller.py`)
- [x] Helper function added (`handlers/common/webapp.py`)

### 2. Backend Integration
- [x] Partner panel router imported
- [x] Router included in FastAPI app
- [x] WebAppInfo button added to seller keyboard
- [x] Environment variable helper created (`get_partner_panel_url()`)
- [ ] Test API endpoints locally
- [ ] Verify Telegram auth works
- [ ] Check CORS settings

### 3. Files Created
```
webapp/partner-panel/
├── index.html              ✅ Created (280 lines)
├── styles.css              ✅ Created (450 lines)
├── app.js                  ✅ Created (630 lines)
├── README.md              ✅ Created (documentation)
└── example-products.csv    ✅ Created (sample data)

app/api/
└── partner_panel.py        ✅ Created (580 lines, 11 endpoints)

vercel.json                 ✅ Created (deployment config)
```

## 🚀 Deployment Steps

### Step 1: Local Testing (Before Deploy)

#### Test Backend API:
```bash
# 1. Start bot with API server
python bot.py

# 2. Check API is running
curl http://localhost:8000/

# 3. Check Swagger docs
# Open: http://localhost:8000/api/docs

# 4. Test partner endpoints (with fake auth for now)
curl -X GET "http://localhost:8000/api/partner/profile" \
     -H "Authorization: tma test_data"
```

#### Test Frontend Locally:
```bash
# Option A: Python simple server
cd webapp/partner-panel
python -m http.server 8080
# Open: http://localhost:8080

# Option B: VS Code Live Server extension
# Right-click index.html → Open with Live Server
```

#### Test with ngrok (for Telegram testing):
```bash
# Terminal 1: Run bot
python bot.py

# Terminal 2: Tunnel frontend
ngrok http 8080

# Use ngrok HTTPS URL in Telegram Bot Father:
# /setmenubutton
# Web App URL: https://xxxxx.ngrok.io
```

### Step 2: Deploy to Vercel

#### Install Vercel CLI:
```bash
npm install -g vercel
```

#### Deploy:
```bash
# From project root
cd c:\Users\User\Desktop\fudly-bot-main

# Deploy
vercel --prod

# Follow prompts:
# - Link to existing project? No
# - Project name: fudly-partner-panel
# - Directory: webapp/partner-panel
# - Build command: (leave empty)
# - Output directory: (leave empty)
```

#### Set Environment Variables:
```bash
# Via Vercel CLI
vercel env add API_URL production
# Value: https://fudly-bot-production.up.railway.app

# Or in Vercel Dashboard:
# Project → Settings → Environment Variables
# Key: API_URL
# Value: https://fudly-bot-production.up.railway.app
```

### Step 3: Update Bot Configuration

#### Railway Environment Variables:
```bash
# In Railway dashboard or CLI:
PARTNER_PANEL_URL=https://fudly-partner-panel.vercel.app
BOT_TOKEN=<your_bot_token>  # Must be set for WebApp auth
```

#### Local .env:
```bash
# Add to .env file
PARTNER_PANEL_URL=https://fudly-partner-panel.vercel.app
```

### Step 4: Update Backend CORS

Edit `app/api/api_server.py` CORS settings to include deployed URL:
```python
allow_origins=[
    "https://fudly-partner-panel.vercel.app",  # Add this
    "https://fudly-webapp.vercel.app",
    "https://web.telegram.org",
    "https://telegram.org",
    # ... rest
],
```

### Step 5: Deploy Backend Changes

```bash
# Commit changes
git add .
git commit -m "feat: Add partner panel Mini App"

# Push to Railway (auto-deploys)
git push origin main

# Or manual Railway CLI:
railway up
```

### Step 6: Test in Production

#### Test API:
```bash
# Check API health
curl https://fudly-bot-production.up.railway.app/

# Check partner endpoints (need real Telegram auth)
# Can't test without real Telegram WebApp initData
```

#### Test Mini App in Telegram:

1. **Send /start to your bot**
2. **Switch to seller mode** (if you have seller role)
3. **Click "🖥 Веб-панель" button**
4. **Mini App should open**
5. **Test features:**
   - View products list
   - Add new product
   - Edit product
   - Delete product
   - Import CSV (use example-products.csv)
   - View orders
   - Check stats
   - Update settings

## 🧪 Testing Checklist

### Frontend Tests:
- [ ] Mini App opens in Telegram
- [ ] Theme matches Telegram (light/dark)
- [ ] Tabs switch correctly
- [ ] Product list loads
- [ ] Add product modal opens/closes
- [ ] Form validation works
- [ ] Photo preview works
- [ ] CSV modal opens
- [ ] Drag-and-drop works
- [ ] Orders list loads
- [ ] Stats display correctly
- [ ] Settings form loads

### Backend Tests:
- [ ] GET /api/partner/profile returns data
- [ ] GET /api/partner/products returns list
- [ ] POST /api/partner/products creates product
- [ ] PUT /api/partner/products/:id updates
- [ ] DELETE /api/partner/products/:id deletes
- [ ] POST /api/partner/products/import processes CSV
- [ ] GET /api/partner/orders returns list
- [ ] POST /api/partner/orders/:id/confirm works
- [ ] POST /api/partner/orders/:id/cancel works
- [ ] GET /api/partner/stats returns data
- [ ] PUT /api/partner/store updates settings

### Security Tests:
- [ ] Invalid initData rejected (401)
- [ ] Non-seller users blocked (403)
- [ ] Can't access other partner's data
- [ ] CORS blocks unauthorized origins
- [ ] SQL injection prevented (SQLAlchemy ORM)

### UX Tests:
- [ ] Loading states show correctly
- [ ] Empty states show friendly messages
- [ ] Error alerts display
- [ ] Success feedback shows
- [ ] Responsive on mobile
- [ ] Touch targets large enough (44px)
- [ ] Scrolling smooth
- [ ] Modals scroll if content long

## 🐛 Troubleshooting

### Problem: Mini App button doesn't appear
**Solution:**
- Check `PARTNER_PANEL_URL` is set in Railway
- Verify `get_partner_panel_url()` imported in `commands.py`
- Confirm `webapp_url=get_partner_panel_url()` passed to `main_menu_seller()`
- Restart bot after env changes

### Problem: 401 Authentication Failed
**Solution:**
- Check `BOT_TOKEN` environment variable is set
- Verify `init_data` is being sent in Authorization header
- Test signature validation with known-good data
- Check bot token matches your bot

### Problem: 403 Not a partner
**Solution:**
- User must have `role='seller'` in database
- Check user role: `SELECT role FROM users WHERE telegram_id=123456;`
- Update role if needed: `UPDATE users SET role='seller' WHERE telegram_id=123456;`

### Problem: 404 Product not found
**Solution:**
- Verify product belongs to current partner
- Check `seller_id` matches `user_id`
- Test with correct `offer_id`

### Problem: CORS error in browser console
**Solution:**
- Add Mini App URL to CORS origins in `api_server.py`
- Redeploy backend
- Clear browser cache
- Test in incognito mode

### Problem: CSV import fails
**Solution:**
- Check CSV encoding (UTF-8 with BOM supported)
- Verify column headers match expected names
- Ensure required fields (title, discount_price, quantity) present
- Check date format (YYYY-MM-DD)
- Look at backend logs for specific error

### Problem: Stats show zero
**Solution:**
- Check if any orders exist in database
- Verify `status IN ('completed', 'confirmed')` filter
- Check date range matches order dates
- Test with `period=all` first

## 📊 Monitoring

### Check Deployment Status:
```bash
# Vercel
vercel list
vercel logs fudly-partner-panel

# Railway
railway logs
railway status
```

### Monitor API:
```bash
# Check API health
watch -n 60 "curl -s https://fudly-bot-production.up.railway.app/ | jq"

# Check specific endpoint
curl -X GET "https://fudly-bot-production.up.railway.app/api/partner/profile" \
     -H "Authorization: tma ${INIT_DATA}"
```

### Analytics:
- Vercel Analytics (automatic)
- Railway Metrics (CPU, Memory)
- Bot analytics (user interactions)

## 🎉 Post-Deployment

### Announce to Partners:
```
📢 Новая функция: Веб-панель!

Теперь управлять товарами стало проще:
✅ Удобные формы добавления
✅ Массовый импорт из CSV
✅ Визуальные карточки товаров
✅ Статистика с графиками

Нажмите кнопку "🖥 Веб-панель" в главном меню!
```

### Collect Feedback:
- Create feedback form in Mini App
- Monitor error logs
- Track usage metrics
- Ask partners for improvements

### Next Steps:
1. Add Chart.js for stats visualization
2. Implement photo uploads via Telegram
3. Add push notifications for new orders
4. Export functionality (Excel/PDF)
5. Bulk edit operations
6. Product templates/duplication

## 📝 Rollback Plan

If something breaks:

### Rollback Frontend:
```bash
# Vercel keeps history
vercel rollback

# Or redeploy previous version
git checkout HEAD~1 -- webapp/partner-panel/
vercel --prod
```

### Rollback Backend:
```bash
# Railway keeps history
railway rollback

# Or git revert
git revert HEAD
git push origin main
```

### Emergency: Disable Feature:
```python
# In app/keyboards/seller.py
# Remove webapp_url parameter temporarily:
menu = main_menu_seller(lang)  # Without webapp_url
```

## ✅ Success Criteria

Deployment successful when:
- [x] Code complete and reviewed
- [ ] Local testing passed
- [ ] Frontend deployed to Vercel
- [ ] Backend deployed to Railway
- [ ] Environment variables set
- [ ] Mini App opens in Telegram
- [ ] All CRUD operations work
- [ ] CSV import processes successfully
- [ ] Stats display correctly
- [ ] No critical errors in logs
- [ ] At least 3 partners tested successfully

## 📚 Documentation

- User guide: `webapp/partner-panel/README.md`
- API docs: http://localhost:8000/api/docs (Swagger)
- Bot flows: `docs/BOT_FLOW_OVERVIEW_RU.md`
- Mini App spec: `docs/MINI_APP_ORDER_SYSTEM.md`

---

**Status**: Ready for deployment ✅
**Estimated time**: 30-60 minutes
**Risk level**: Low (new feature, doesn't affect existing flows)
