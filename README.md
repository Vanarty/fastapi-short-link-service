# URL Shortener API

API-сервис сокращения ссылок на FastAPI с PostgreSQL и Redis.

## Возможности

- Создание коротких ссылок (с автогенерацией или кастомным alias)
- Перенаправление по короткой ссылке
- Обновление и удаление ссылок (только для авторизованных владельцев)
- Статистика по ссылке (количество переходов, дата создания, последнее использование)
- Поиск ссылки по оригинальному URL
- Время жизни ссылки (expires_at)
- Автоматическая очистка истекших и неиспользуемых ссылок
- История удаленных/истекших ссылок
- Кэширование через Redis (редиректы, статистика, поиск)
- JWT-авторизация
- Миграции базы данных через Alembic

## Структура проекта

```
.
├── migrations/                   # Миграции Alembic
│   ├── env.py                    # Конфигурация Alembic (async)
│   ├── script.py.mako            # Шаблон для генерации миграций
│   └── versions/
│       └── 001_initial_tables.py
├── src/                          # Исходный код приложения
│   ├── __init__.py
│   ├── main.py                   # Точка входа, lifespan, фоновая очистка
│   ├── config.py                 # Настройки (pydantic-settings)
│   ├── database.py               # Подключение к PostgreSQL (async)
│   ├── cache.py                  # Обертка над Redis
│   ├── models.py                 # SQLAlchemy-модели
│   ├── schemas.py                # Pydantic-схемы запросов/ответов
│   ├── auth.py                   # JWT-аутентификация
│   └── routers/
│       ├── __init__.py
│       ├── users.py              # Регистрация, вход
│       └── links.py              # CRUD, статистика, поиск
├── tests/                        # Тесты (пока нет, но планирую внести при выполнении 4-го проекта)
├── .dockerignore
├── .env.example
├── .gitignore
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── README.md
└── requirements.txt
```

## Запуск

### Через Docker Compose

```bash
docker-compose up --build
```

При запуске контейнера миграции применяются автоматически (`alembic upgrade head`).

Сервис будет доступен по адресу: `http://localhost:8000`

Swagger UI: `http://localhost:8000/docs`

### Локальный запуск (без Docker)

```bash
# Создать виртуальное окружение и установить зависимости
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows
pip install -r requirements.txt

# Настроить переменные окружения
cp .env.example .env
# Отредактировать .env -- указать свои DATABASE_URL и REDIS_URL

# Применить миграции
alembic upgrade head

# Запустить сервер
uvicorn src.main:app --reload
```

## Миграции (Alembic)

```bash
# Применить все миграции
alembic upgrade head

# Откатить последнюю миграцию
alembic downgrade -1

# Создать новую миграцию (autogenerate)
alembic revision --autogenerate -m "описание изменений"

# Посмотреть текущую ревизию
alembic current
```

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@db:5432/linkshortener` | Строка подключения к PostgreSQL |
| `REDIS_URL` | `redis://redis:6379/0` | Строка подключения к Redis |
| `SECRET_KEY` | `change-me-to-random-secret-key` | Секретный ключ для JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Время жизни токена (минуты) |
| `SHORT_CODE_LENGTH` | `6` | Длина генерируемого короткого кода |
| `CACHE_TTL_SECONDS` | `3600` | TTL кэша Redis (секунды) |
| `UNUSED_LINK_DAYS` | `90` | Порог неактивности ссылки (дни) |
| `CLEANUP_INTERVAL_MINUTES` | `60` | Интервал фоновой очистки (минуты) |

## API-эндпоинты

### Пользователи

| Метод | Путь | Описание | Авторизация |
|---|---|---|---|
| `POST` | `/users/register` | Регистрация | Нет |
| `POST` | `/users/login` | Вход (получение JWT-токена) | Нет |

### Ссылки

| Метод | Путь | Описание | Авторизация |
|---|---|---|---|
| `POST` | `/links/shorten` | Создать короткую ссылку | Опционально |
| `GET` | `/links/search?original_url={url}` | Найти ссылку по оригинальному URL | Нет |
| `GET` | `/links/expired` | История истекших/удаленных ссылок | Да |
| `PUT` | `/links/unused-threshold?days=N` | Установить порог неактивности | Да |
| `GET` | `/links/{short_code}` | Перенаправление на оригинальный URL | Нет |
| `PUT` | `/links/{short_code}` | Обновить оригинальный URL | Да (владелец) |
| `DELETE` | `/links/{short_code}` | Удалить ссылку | Да (владелец) |
| `GET` | `/links/{short_code}/stats` | Статистика по ссылке | Нет |
| `GET` | `/{short_code}` | Перенаправление (корневой путь) | Нет |

## Примеры запросов

### Регистрация

```bash
curl -X POST http://localhost:8000/users/register \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "password": "secret123"}'
```

### Получение токена

```bash
curl -X POST http://localhost:8000/users/login \
  -d "username=testuser&password=secret123"
```

### Создание короткой ссылки

```bash
# Без авторизации (анонимная ссылка)
curl -X POST http://localhost:8000/links/shorten \
  -H "Content-Type: application/json" \
  -d '{"original_url": "https://example.com/very/long/path"}'

# С авторизацией и кастомным alias
curl -X POST http://localhost:8000/links/shorten \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"original_url": "https://example.com", "custom_alias": "my-link", "expires_at": "2025-12-31T23:59"}'
```

### Переход по короткой ссылке

```bash
curl -L http://localhost:8000/links/my-link
# или
curl -L http://localhost:8000/my-link
```

### Статистика

```bash
curl http://localhost:8000/links/my-link/stats
```

### Поиск по URL

```bash
curl "http://localhost:8000/links/search?original_url=https://example.com"
```

### Обновление ссылки

```bash
curl -X PUT http://localhost:8000/links/my-link \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"original_url": "https://new-example.com"}'
```

### Удаление ссылки

```bash
curl -X DELETE http://localhost:8000/links/my-link \
  -H "Authorization: Bearer <token>"
```

### Установка порога не активности

```bash
curl -X PUT "http://localhost:8000/links/unused-threshold?days=30" \
  -H "Authorization: Bearer <token>"
```

### История истекших ссылок

```bash
curl http://localhost:8000/links/expired \
  -H "Authorization: Bearer <token>"
```

## Описание базы данных

### Таблица `users`

| Поле | Тип | Описание |
|---|---|---|
| `id` | `Integer` (PK) | Идентификатор |
| `username` | `String(50)` | Имя пользователя (уникальное) |
| `password_hash` | `String(255)` | Хэш пароля (bcrypt) |
| `created_at` | `DateTime` | Дата регистрации |

### Таблица `links`

| Поле | Тип | Описание |
|---|---|---|
| `id` | `Integer` (PK) | Идентификатор |
| `short_code` | `String(20)` | Короткий код (уникальный, индекс) |
| `original_url` | `Text` | Оригинальный URL |
| `user_id` | `Integer` (FK -> users.id) | Владелец (NULL для анонимных) |
| `created_at` | `DateTime` | Дата создания |
| `updated_at` | `DateTime` | Дата обновления |
| `expires_at` | `DateTime` | Дата истечения (NULL = бессрочная) |
| `last_used_at` | `DateTime` | Дата последнего перехода |
| `click_count` | `Integer` | Количество переходов |

### Таблица `link_history`

| Поле | Тип | Описание |
|---|---|---|
| `id` | `Integer` (PK) | Идентификатор |
| `short_code` | `String(20)` | Короткий код |
| `original_url` | `Text` | Оригинальный URL |
| `user_id` | `Integer` | Владелец |
| `created_at` | `DateTime` | Дата создания ссылки |
| `deleted_at` | `DateTime` | Дата удаления |
| `reason` | `String(50)` | Причина: `expired`, `unused`, `deleted_by_user` |
| `click_count` | `Integer` | Количество переходов на момент удаления |

## Кэширование (Redis)

| Ключ | TTL | Описание |
|---|---|---|
| `link:{short_code}` | 1 час | Оригинальный URL для быстрого редиректа |
| `stats:{short_code}` | 5 мин | Статистика по ссылке |
| `search:{original_url}` | 5 мин | Результат поиска по URL |
| `config:unused_link_days` | 1 час | Текущий порог неактивности |

Кэш автоматически инвалидируется при обновлении или удалении ссылки.

## Технологии

- **FastAPI** -- веб-фреймворк
- **SQLAlchemy 2.0** (async) -- ORM
- **Alembic** -- миграции базы данных
- **PostgreSQL** -- основная база данных
- **Redis** -- кэширование
- **python-jose** -- JWT-токены
- **passlib** -- хэширование паролей
- **pytest** -- тестирование
- **Docker / Docker Compose** -- контейнеризация

*Разработал: Иванов Артём*
*В рамках курса "Прикладной Python" в магистратуре ВШЭ "Искусственный интеллект"*