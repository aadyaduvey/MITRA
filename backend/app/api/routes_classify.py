"""Photo -> material SUGGESTION. The collector always confirms; this never sets a material."""
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.classify import model as cv
from app.schemas import ClassifyOut, CvStatus

router = APIRouter(prefix="/api/classify", tags=["classify"])

MAX_BYTES = 10 * 1024 * 1024
NOTE = "Suggestion only: the collector confirms or overrides the material."


@router.get("/status", response_model=CvStatus)
def classifier_status() -> CvStatus:
    return CvStatus(**cv.status())


@router.post("", response_model=ClassifyOut)
async def classify_photo(file: UploadFile = File(..., description="JPEG or PNG photo of the material")) -> ClassifyOut:
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "photo larger than 10 MB")
    try:
        result = await run_in_threadpool(cv.classify, data)
    except cv.Unavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "upload a JPEG or PNG photo") from e
    return ClassifyOut(**result, note=NOTE)
