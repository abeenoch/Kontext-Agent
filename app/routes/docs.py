from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.rag_pipeline import ingest_file
import tempfile
import os

router = APIRouter()

@router.post("/upload")
async def upload_document(user_id: str, file: UploadFile = File(...)):
    import tempfile, os
    tmp_dir = tempfile.gettempdir()
    safe_filename = file.filename.replace(" ", "_").replace("'", "_")
    tmp_file_path = os.path.join(tmp_dir, safe_filename)

    with open(tmp_file_path, "wb") as f:
        f.write(await file.read())

    chunks_added = ingest_file(tmp_file_path, user_id)
    os.remove(tmp_file_path)

    return {"status": "ok", "chunks_added": chunks_added}
