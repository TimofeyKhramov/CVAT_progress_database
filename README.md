# CVAT Progress

Минимальное веб-приложение для контроля прогресса разметки видео в CVAT.

## Что реализовано на этапе 1

- загрузка `dataset_info`;
- сохранение в PostgreSQL полей `name`, `task_id`, `job_id`, `stage`, `assignee`;
- обновление существующей записи по паре `(task_id, job_id)`;
- таблица с поиском и фильтрами по статусу и разметчику;
- колонка «Метки по классам» присутствует, но пока пустая;
- окно загрузки `annotations_info` присутствует, обработка запланирована на этап 2;
- запуск через Docker Compose.

## Поддерживаемый dataset_info

Форматы: CSV, JSON, XLSX/XLSM.

Ожидаемые поля:
- `name`
- `task_id`
- `job_id`
- `stage`
- `assignee`

Также распознаются некоторые альтернативы, например `video_name`, `filename`, `status`, `annotator`.

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
