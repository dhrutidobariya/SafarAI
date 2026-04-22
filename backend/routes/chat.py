from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ai.chat_orchestrator import ChatOrchestrator
from database import get_db
from models import User
from schemas import ChatRequest, ChatResponse
from services.auth_service import get_current_user

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    orchestrator = ChatOrchestrator(db, user.id)
    result = orchestrator.handle_message(payload.message)
    return ChatResponse(**result)
