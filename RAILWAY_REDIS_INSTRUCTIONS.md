# 🚀 Railway Deployment Instructions (Redis Setup)

To enable the new Redis features in Railway, follow these steps:

1.  **Add Redis Service**:
    *   Open your project in [Railway Dashboard](https://railway.app).
    *   Click **New** → **Database** → **Redis**.
    *   Wait for the Redis service to deploy.

2.  **Link Redis to Bot**:
    *   Go to your **Bot** service settings.
    *   Open the **Variables** tab.
    *   Add a new variable: `REDIS_URL`.
    *   For the value, type `${{Redis.REDIS_URL}}` (or select the Redis connection string from the dropdown).

3.  **Redeploy**:
    *   Railway should automatically redeploy when you push the code (which I am doing now).
    *   If not, click **Redeploy** on the Bot service.

4.  **Verify**:
    *   Check the **Deploy Logs**.
    *   You should see: `🚀 Using Redis for FSM storage`.

---
**Note**: If you don't add Redis, the bot will fallback to PostgreSQL or Memory storage, but Redis is recommended for production performance.
