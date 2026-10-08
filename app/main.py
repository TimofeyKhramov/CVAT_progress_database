from __future__ import annotations

import csv
import io
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import AnnotationColumn, AnnotationValue, VideoTask


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="CVAT Progress")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

REQUIRED_COLUMNS = {
    "ID",
    "Task ID",
    "Task Name",
    "Project Name",
    "Assignee",
    "State",
}

EXTRA_COLUMN_MAP = {
    "Scope": "scope",
    "Localization": "localization",
    "Lab": "lab",
    "Visual": "visual",
}

EDITABLE_FIELDS = {
    "visual",
    "lab",
    "localization",
    "scope",
}


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def parse_dataset_info(filename: str, content: bytes) -> list[dict[str, str]]:
    if Path(filename or "").suffix.lower() != ".csv":
        raise ValueError("jobs_info должен быть CSV-файлом")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV-файл должен быть в кодировке UTF-8") from exc

    header_line = text.splitlines()[0]

    if ";" in header_line:
        delimiter = ";"
    elif "," in header_line:
        delimiter = ","
    else:
        raise ValueError(
            "Не удалось определить разделитель CSV. "
            "Поддерживаются ';' и ','"
        )

    reader = csv.DictReader(
        io.StringIO(text),
        delimiter=delimiter
    )

    if not reader.fieldnames:
        raise ValueError("CSV-файл не содержит заголовков")

    reader.fieldnames = [column.strip() for column in reader.fieldnames]
    

    missing_columns = REQUIRED_COLUMNS - set(reader.fieldnames)
    if missing_columns:
        missing = ";".join(sorted(missing_columns))
        raise ValueError(f"В CSV отсутствуют обязательные столбцы: {missing}")

    result: list[dict[str, str]] = []

    for row in reader:
        item = {
            "name": (row.get("Task Name") or "").strip(),
            "task_id": (row.get("Task ID") or "").strip(),
            "job_id": (row.get("ID") or "").strip(),
            "project": (row.get("Project Name") or "").strip(),
            "state": (row.get("State") or "").strip(),
            "assignee": (row.get("Assignee") or "").strip(),
        }

        if item["name"] and item["task_id"] and item["job_id"]:
            result.append(item)

    if not result:
        raise ValueError(
            "В CSV не найдено строк с заполненными ID, Task ID и Task Name"
        )

    return result


class RowUpdate(BaseModel):
    row_id: int
    field: str
    value: str | None = None


class BulkRowUpdate(BaseModel):
    updates: list[RowUpdate]


def update_editable_field(row: VideoTask, field: str, value: str | None) -> None:
    if field not in EDITABLE_FIELDS:
        raise HTTPException(status_code=400, detail="Недопустимое поле")

    normalized_value = (value or "").strip()
    setattr(row, field, normalized_value or None)


def get_project_options(db: Session) -> list[dict[str, str]]:
    projects = db.scalars(
        select(VideoTask.project)
        .where(
            VideoTask.project.is_not(None),
            VideoTask.project != "",
        )
        .distinct()
        .order_by(VideoTask.project)
    ).all()

    return [
        {
            "name": project,
            "url": "/project?" + urlencode({"project": project}),
        }
        for project in projects
    ]


def render_index(
    request: Request,
    db: Session,
    *,
    message: str = "",
    error: str = "",
    current_project: str | None = None,
):
    rows_query = select(VideoTask)

    if current_project is not None:
        rows_query = rows_query.where(VideoTask.project == current_project)

    rows = db.scalars(rows_query.order_by(VideoTask.id.desc())).all()

    annotation_columns = []
    annotation_values: dict[int, dict[int, str]] = {}

    if current_project is not None:
        annotation_columns = db.scalars(
            select(AnnotationColumn)
            .where(AnnotationColumn.project == current_project)
            .order_by(AnnotationColumn.position)
        ).all()

        if annotation_columns and rows:
            values = db.scalars(
                select(AnnotationValue).where(
                    AnnotationValue.video_task_id.in_([row.id for row in rows]),
                    AnnotationValue.column_id.in_([
                        column.id for column in annotation_columns
                    ]),
                )
            ).all()

            for value in values:
                annotation_values.setdefault(value.video_task_id, {})[
                    value.column_id
                ] = value.value

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "rows": rows,
            "projects": get_project_options(db),
            "current_project": current_project,
            "annotation_columns": annotation_columns,
            "annotation_values": annotation_values,
            "message": message,
            "error": error,
        },
    )


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    db: Session = Depends(get_db),
    message: str = "",
    error: str = "",
):
    return render_index(
        request,
        db,
        message=message,
        error=error,
    )


@app.get("/project", response_class=HTMLResponse, name="project_page")
def project_page(
    request: Request,
    project: str,
    db: Session = Depends(get_db),
    message: str = "",
    error: str = "",
):
    project_exists = db.scalar(
        select(VideoTask.id)
        .where(VideoTask.project == project)
        .limit(1)
    )

    if project_exists is None:
        raise HTTPException(status_code=404, detail="Проект не найден")

    return render_index(
        request,
        db,
        current_project=project,
        message=message,
        error=error,
    )


@app.post("/upload/dataset")
async def upload_dataset(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        content = await file.read()
        items = parse_dataset_info(file.filename or "", content)

        created = 0
        updated = 0

        for item in items:
            existing = db.scalar(
                select(VideoTask).where(
                    VideoTask.task_id == item["task_id"],
                    VideoTask.job_id == item["job_id"],
                )
            )

            if existing:
                existing.name = item["name"]
                existing.project = item["project"]
                existing.state = item["state"]
                existing.assignee = item["assignee"]
                updated += 1
            else:
                db.add(VideoTask(**item))
                created += 1

        db.commit()

        return RedirectResponse(
            url="/?"
            + urlencode(
                {
                    "message": (
                        f"Импорт завершён: добавлено {created}, "
                        f"обновлено {updated}"
                    )
                }
            ),
            status_code=303,
        )

    except Exception as exc:
        db.rollback()

        return RedirectResponse(
            url="/?" + urlencode({"error": str(exc)}),
            status_code=303,
        )


@app.post("/api/rows/update")
def update_row(
    data: RowUpdate,
    db: Session = Depends(get_db),
):
    row = db.get(VideoTask, data.row_id)

    if row is None:
        raise HTTPException(status_code=404, detail="Строка не найдена")

    try:
        update_editable_field(row, data.field, data.value)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Не удалось сохранить значение: {exc}",
        ) from exc

    return {
        "status": "ok",
        "row_id": data.row_id,
        "field": data.field,
        "value": getattr(row, data.field),
    }


@app.post("/api/rows/bulk-update")
def bulk_update_rows(
    data: BulkRowUpdate,
    db: Session = Depends(get_db),
):
    updated = 0

    try:
        for item in data.updates:
            if item.field not in EDITABLE_FIELDS:
                continue

            row = db.get(VideoTask, item.row_id)
            if row is None:
                continue

            update_editable_field(row, item.field, item.value)
            updated += 1

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "status": "ok",
        "updated": updated,
    }


@app.post("/rows/{row_id}/delete")
def delete_row(
    row_id: int,
    db: Session = Depends(get_db),
):
    row = db.get(VideoTask, row_id)

    if row is not None:
        db.execute(
            delete(AnnotationValue).where(
                AnnotationValue.video_task_id == row.id
            )
        )
        db.delete(row)
        db.commit()

    return RedirectResponse(url="/", status_code=303)


@app.post("/upload/annotations")
async def upload_annotations(
    file: UploadFile = File(...),
    project: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        project_exists = db.scalar(
            select(VideoTask.id)
            .where(VideoTask.project == project)
            .limit(1)
        )
        if project_exists is None:
            raise ValueError("Проект не найден")

        content = await file.read()
        column_names, items = parse_annotations_info(
            file.filename or "",
            content,
        )

        updated = 0
        skipped = 0

        project_rows = db.scalars(
            select(VideoTask).where(VideoTask.project == project)
        ).all()
        rows_by_job_id = {row.job_id: row for row in project_rows}

        old_column_ids = select(AnnotationColumn.id).where(
            AnnotationColumn.project == project
        )
        db.execute(
            delete(AnnotationValue).where(
                AnnotationValue.column_id.in_(old_column_ids)
            )
        )
        db.execute(
            delete(AnnotationColumn).where(
                AnnotationColumn.project == project
            )
        )

        columns = [
            AnnotationColumn(project=project, name=name, position=position)
            for position, name in enumerate(column_names)
        ]
        db.add_all(columns)
        db.flush()

        for item in items:
            row = rows_by_job_id.get(item["job_id"])
            if row is None:
                skipped += 1
                continue

            db.add_all([
                AnnotationValue(
                    video_task_id=row.id,
                    column_id=column.id,
                    value=item["values"][column.name],
                )
                for column in columns
            ])

            updated += 1

        db.commit()

        return RedirectResponse(
            url="/project?"
            + urlencode(
                {
                    "project": project,
                    "message": (
                        f"annotations_info загружен: строк {updated}, "
                        f"меток {len(column_names)}, "
                        f"не найдено Job ID: {skipped}"
                    ),
                }
            ),
            status_code=303,
        )

    except Exception as exc:
        db.rollback()

        return RedirectResponse(
            url="/project?"
            + urlencode(
                {
                    "project": project,
                    "error": str(exc)
                }
            ),
            status_code=303,
        )


def parse_annotations_info(
    filename: str,
    content: bytes,
) -> tuple[list[str], list[dict[str, object]]]:

    if Path(filename or "").suffix.lower() != ".csv":
        raise ValueError(
            "Дополнительные параметры должны быть CSV-файлом"
        )

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("cp1251")
        except UnicodeDecodeError as exc:
            raise ValueError(
                "Не удалось определить кодировку CSV"
            ) from exc

    if not text.strip():
        raise ValueError("CSV-файл пуст")

    # Берём первую непустую строку — заголовок
    header_line = next(
        (
            line
            for line in text.splitlines()
            if line.strip()
        ),
        None,
    )

    if not header_line:
        raise ValueError("CSV-файл пуст")

    # Для файла 2 поддерживаем ; и ,
    if ";" in header_line:
        delimiter = ";"
    elif "," in header_line:
        delimiter = ","
    else:
        raise ValueError(
            "Не удалось определить разделитель CSV. "
            "Поддерживаются ';' и ','"
        )

    reader = csv.DictReader(
        io.StringIO(text),
        delimiter=delimiter,
    )

    if not reader.fieldnames:
        raise ValueError(
            "CSV-файл не содержит заголовков"
        )

    # Нормализуем названия столбцов
    reader.fieldnames = [
        column.strip()
        for column in reader.fieldnames
    ]

    if "Job_id" not in reader.fieldnames:
        raise ValueError(
            "В CSV отсутствует обязательный столбец Job_id. "
            f"Найдены столбцы: {reader.fieldnames}"
        )

    job_id_index = reader.fieldnames.index("Job_id")
    column_names = reader.fieldnames[job_id_index + 1:]

    if not column_names:
        raise ValueError("После столбца Job_id отсутствуют столбцы с метками")

    if any(not name for name in column_names):
        raise ValueError("Названия столбцов с метками не могут быть пустыми")

    if len(column_names) != len(set(column_names)):
        raise ValueError("Названия столбцов с метками не должны повторяться")

    rows = []
    seen_job_ids: set[str] = set()

    for row_number, csv_row in enumerate(reader, start=2):
        job_id = (csv_row.get("Job_id") or "").strip()

        if not job_id:
            raise ValueError(f"Пустой Job_id в строке {row_number}")

        if job_id in seen_job_ids:
            raise ValueError(f"Job_id {job_id} повторяется в строке {row_number}")
        seen_job_ids.add(job_id)

        values = {
            column_name: (csv_row.get(column_name) or "").strip()
            for column_name in column_names
        }
        empty_columns = [
            column_name
            for column_name, value in values.items()
            if not value
        ]
        if empty_columns:
            raise ValueError(
                f"Пустые значения в строке {row_number}: "
                + ", ".join(empty_columns)
            )

        rows.append({"job_id": job_id, "values": values})

    if not rows:
        raise ValueError(
            "CSV не содержит строк с заполненным Job_id"
        )

    return column_names, rows
