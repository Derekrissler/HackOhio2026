from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.auth import CurrentUser, DbSession, require_file_access
from app.db import DATA_DIR

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/{file_id}/content", response_class=FileResponse)
def get_file_content(file_id: int, user: CurrentUser, db: DbSession) -> FileResponse:
    """Served inline so the browser's own PDF viewer can show it in an <iframe>."""
    file = require_file_access(db, user, file_id)
    path = (DATA_DIR / file.storage_path).resolve()
    if not path.is_relative_to(DATA_DIR.resolve()) or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File content missing")
    return FileResponse(path, media_type=file.mime, filename=file.display_name, content_disposition_type="inline")
