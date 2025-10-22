from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.rag_pipeline import ingest_file

router = APIRouter()

@router.post("/upload", summary="Upload a document for ingestion")
async def upload_document(file: UploadFile = File(...), user_id:str="demo"):
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded")
    contents = await file.read()
    tmp_file_path = f"/tmp/{file.filename}"
    with open(tmp_file_path, "wb") as f:
        f.write(contents)
    result = ingest_file(tmp_file_path, user_id=user_id)
    return {"status": "ok", "chunks_added":result["inserted_chunks"]}
