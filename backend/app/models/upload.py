from pydantic import BaseModel
from typing import Optional


class UploadResponse(BaseModel):
    scan_id: str
    filename: str
    size: int
    sha256: str
    status: str