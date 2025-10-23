# simple placeholder - you can later wire Google Drive API here
def upload_to_drive(payload: dict):
    filename = payload.get("filename", "file.txt")
    content = payload.get("content", "")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    return {"ok": True, "saved_to": filename}
