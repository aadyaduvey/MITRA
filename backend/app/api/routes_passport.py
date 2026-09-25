"""Material passport for one transaction."""
from fastapi import APIRouter, HTTPException, status

from app.api.deps import SessionDep
from app.engine.loaders import passport_for
from app.schemas import PassportOut

router = APIRouter(prefix="/api/passport", tags=["passport"])


@router.get("/{transaction_id}", response_model=PassportOut)
def get_passport(transaction_id: int, session: SessionDep) -> PassportOut:
    p = passport_for(session, transaction_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"transaction {transaction_id} not found")
    return PassportOut(**p)
