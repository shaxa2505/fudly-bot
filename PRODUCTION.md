# Fudly Bot Production Deployment Guide

## Overview

This guide covers the production deployment of the optimized Fudly Telegram bot with enhanced performance, security, and monitoring capabilities.

## Production Optimizations Implemented

### 1. Database Optimizations
- **Connection Pooling**: SQLite connections are pooled and reused
- **Indexes**: Added indexes on frequently queried columns
- **Query Timeouts**: Configurable timeouts prevent hanging queries
- **WAL Mode**: Write-Ahead Logging for better concurrency

### 2. Performance Improvements
- **Caching**: Redis (with in-memory fallback) for frequently accessed data
- **Background Tasks**: Automated cleanup of expired offers and backups
- **Image Optimization**: Automatic image compression and thumbnail generation

### 3. Security Enhancements
- **Input Validation**: Comprehensive sanitization of user inputs
- **Rate Limiting**: Per-user rate limiting to prevent abuse
- **SQL Injection Prevention**: Parameterized queries throughout
- **Admin Action Logging**: Security events are logged

### 4. Monitoring & Logging
- **Structured Logging**: JSON-formatted logs with context
- **Error Tracking**: Comprehensive error handling and logging
- **Performance Metrics**: Database and system statistics

## Environment Variables

Configure these environment variables for optimal production performance:

```bash
# Database Configuration
DATABASE_PATH=fudly.db
DB_POOL_SIZE=5
DB_TIMEOUT=5

# Caching Configuration
REDIS_URL=redis://localhost:6379/0
CACHE_TTL_SECONDS=300

# Logging Configuration
LOG_LEVEL=INFO

# Background Tasks
CLEANUP_INTERVAL_SECONDS=3600
BACKUP_INTERVAL_SECONDS=86400

# Security
MAX_REQUESTS_PER_MINUTE=30
```

## Installation

### 1. Install Dependencies

```bash
# Install Python dependencies
pip install -r requirements.txt

# Optional: Install Redis for caching
# Ubuntu/Debian: sudo apt install redis-server
# Windows: Download from https://redis.io/docs/getting-started/installation/install-redis-on-windows/
# macOS: brew install redis
```

### 2. Configure Environment

Create a `.env` file in the project directory:

```bash
# Telegram Bot Configuration
BOT_TOKEN=your_bot_token_here
ADMIN_ID=your_telegram_user_id

# Optional Production Settings
LOG_LEVEL=INFO
REDIS_URL=redis://localhost:6379/0
DB_POOL_SIZE=10
CACHE_TTL_SECONDS=300
```

## Running the Bot

### Development Mode

```bash
python bot.py
```

### Production Mode

```bash
# Set production environment
export LOG_LEVEL=INFO
export DB_POOL_SIZE=10

# Run with nohup for background execution
nohup python bot.py > bot.log 2>&1 &
```

## Performance Tuning

### Database Optimization

1. **Connection Pool Size**: Adjust `DB_POOL_SIZE` based on concurrent users
   - Small bots (< 1000 users): 5-10 connections
   - Medium bots (1000-10000 users): 10-20 connections
   - Large bots (> 10000 users): 20-50 connections

2. **Cache TTL**: Adjust `CACHE_TTL_SECONDS` based on data freshness needs
   - User data: 300 seconds (5 minutes)
   - Offers data: 120 seconds (2 minutes)
   - Store data: 600 seconds (10 minutes)

## Monitoring

### Log Files

Logs are output to stdout in JSON format. In production, redirect to files:

```bash
python bot.py 2>&1 | tee -a /var/log/fudly/bot.log
```

### Key Metrics to Monitor

1. **Database Performance**
   - Connection pool usage
   - Query execution times
   - Database file size growth

2. **Cache Performance**
   - Cache hit/miss ratios
   - Memory usage
   - Key expiration patterns

3. **Security Events**
   - Failed admin access attempts
   - Rate limit violations
   - Input validation failures

## Backup Strategy

### Automated Backups

The bot automatically creates daily database backups in the background.

### Manual Backup

```bash
# Backup database
cp fudly.db backups/fudly_$(date +%Y%m%d_%H%M%S).db

# Backup images
tar -czf backups/images_$(date +%Y%m%d_%H%M%S).tar.gz images/
```

## Troubleshooting

### Common Issues

1. **High CPU Usage**
   - Check for infinite loops in background tasks
   - Reduce cache TTL if Redis is overloaded
   - Optimize database queries

2. **Memory Leaks**
   - Monitor connection pool usage
   - Check for unclosed database connections
   - Restart bot periodically if needed

3. **Database Locks**
   - Ensure WAL mode is enabled
   - Check for long-running transactions
   - Monitor connection pool exhaustion