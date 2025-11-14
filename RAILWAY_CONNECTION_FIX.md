# 🔧 Railway PostgreSQL Connection Fix

## Проблема
```
connection to server at "postgres.railway.internal" failed: Connection refused
```

## Причина
`DATABASE_URL` указывает на internal hostname, который недоступен из bot сервиса.

## ✅ Решение 1: Service Reference (Рекомендуется)

### В Railway Dashboard:

1. **Откройте ваш bot service** (fudly-bot)
2. Перейдите в **Variables**
3. Если `DATABASE_URL` уже существует - **удалите его**
4. Нажмите **"+ New Variable"**
5. Выберите **"Add a Reference"**
6. В выпадающем списке выберите ваш **PostgreSQL service**
7. Выберите переменную **`DATABASE_URL`**
8. Сохраните

Это создаст reference вида: `${{Postgres.DATABASE_URL}}`

Railway автоматически подставит правильный URL для связи между сервисами.

## ✅ Решение 2: Public Connection URL

Если Solution 1 не работает:

1. **Откройте PostgreSQL service**
2. Перейдите в **Variables**
3. Найдите переменную **`DATABASE_PUBLIC_URL`** или **`DATABASE_URL`**
4. **Скопируйте** значение (должно выглядеть как):
   ```
   postgresql://postgres:PASSWORD@containers-us-west-XX.railway.app:7432/railway
   ```
   (обратите внимание на `.railway.app`, НЕ `.railway.internal`)

5. Вернитесь в **bot service → Variables**
6. Создайте/обновите `DATABASE_URL` с этим значением

## ✅ Решение 3: Private Networking (если включен)

Если у вас включен Private Networking в Railway:

1. В **bot service → Settings**
2. Проверьте, что **Private Networking** включен
3. Убедитесь, что оба сервиса (bot и PostgreSQL) в одной сети
4. Используйте `DATABASE_PRIVATE_URL` вместо `DATABASE_URL`:
   - В bot service variables добавьте reference на `${{Postgres.DATABASE_PRIVATE_URL}}`

## 🔍 Проверка

После изменения переменных:

1. Railway автоматически перезапустит bot
2. Проверьте логи: **Deployments → View Logs**
3. Должны увидеть:
   ```
   ✅ PostgreSQL connection pool created
   ✅ Database initialized successfully
   ```

## 🆘 Если всё ещё не работает

1. **Проверьте статус PostgreSQL**:
   - PostgreSQL service должен быть "Active" (зелёный индикатор)
   - Проверьте его логи на ошибки

2. **Проверьте формат DATABASE_URL**:
   ```bash
   postgresql://username:password@host:port/database
   ```
   - НЕ должно содержать `.railway.internal` если используете public URL
   - Должно содержать `.railway.app` для публичного подключения

3. **Restart both services**:
   - Settings → Restart для PostgreSQL
   - Settings → Restart для bot service

4. **Check Railway region**:
   - Оба сервиса должны быть в одном регионе (US West, EU, и т.д.)

## 📝 Дополнительная информация

- [Railway Service References](https://docs.railway.app/guides/variables#service-variables)
- [Railway PostgreSQL Plugin](https://docs.railway.app/databases/postgresql)
- [Railway Private Networking](https://docs.railway.app/reference/private-networking)
