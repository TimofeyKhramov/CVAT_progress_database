# CVAT Progress Database

Веб-приложение для контроля прогресса разметки видео в CVAT.

## Запуск

```bash
docker compose up --build
```

Открыть: http://localhost:8000

## Остановка

```bash
docker compose down
```

Чтобы удалить и данные PostgreSQL:

```bash
docker compose down -v
```

## Пример CSV

```csv
name,task_id,job_id,stage,assignee
video_001.mp4,101,501,annotation,user1
video_002.mp4,102,502,validation,user2
```
