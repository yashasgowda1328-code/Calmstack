import uuid
import hashlib
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.models.upload import UploadResponse

router = APIRouter()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


def calculate_sha256(file_path: Path) -> str:
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


@router.post("/upload", response_model=UploadResponse)
async def upload_evidence(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    scan_id = str(uuid.uuid4())
    file_extension = Path(file.filename).suffix
    saved_filename = f"{scan_id}{file_extension}"
    file_path = UPLOAD_DIR / saved_filename

    content = await file.read()
    size = len(content)

    with open(file_path, "wb") as f:
        f.write(content)

    sha256 = calculate_sha256(file_path)

    return UploadResponse(
        scan_id=scan_id,
        filename=file.filename,
        size=size,
        sha256=sha256,
        status="uploaded"
    )