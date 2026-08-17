def upload_file(filename):
    storage_available = False

    if not storage_available:
        raise ConnectionError("Object storage service unavailable")

    return {"status": "UPLOADED", "filename": filename}
