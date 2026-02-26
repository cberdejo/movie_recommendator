from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.session import get_session
from app.schemas.conversation_schema import (
    RoleEnum,
    CreateConversationRequest,
    CreateConversationResponse,
    ConversationRead,
    ConversationExtendedRead,
)
from app.crud.conversation_crud import (
    create_conversation,
    add_message,
    list_conversations,
    get_conversation_with_messages,
    delete_conversation,
)

router = APIRouter()


@router.post("/", response_model=CreateConversationResponse, status_code=201)
async def create_conversation_endpoint(
    req: CreateConversationRequest,
    use_case: str,
    db: Annotated[AsyncSession, Depends(get_session)],
):
    base = (req.message or "").strip()
    title = (base[:30] + "...") if len(base) > 30 else (base or "New Conversation")

    try:
        convo = await create_conversation(
            title=title, model=req.model, use_case=use_case, db=db
        )
        await add_message(
            conversation_id=convo.id,
            role=RoleEnum.user,
            content=req.message,
            raw_content=req.message,
            db=db,
        )
        return CreateConversationResponse(
            id=convo.id, title=convo.title, model=convo.model
        )

    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating conversation",
        ) from e


@router.get("/", response_model=list[ConversationRead])
async def list_conversations_endpoint(
    use_case: str | None,
    db: Annotated[AsyncSession, Depends(get_session)],
):
    try:
        convos = await list_conversations(db=db, use_case=use_case)
        return [
            ConversationRead.model_validate(c, from_attributes=True) for c in convos
        ]

    except SQLAlchemyError as e:
        print(f"Error creating conversation: {e}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error listing conversations",
        ) from e


@router.get("/{id}")
async def get_conversation_endpoint(
    id: int, db: Annotated[AsyncSession, Depends(get_session)]
):
    try:
        convo = await get_conversation_with_messages(conversation_id=id, db=db)
        if not convo:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return ConversationExtendedRead.model_validate(convo, from_attributes=True)

    except HTTPException:
        print(f"Error retrieving the conversation: {e}")
        raise
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving the conversation",
        ) from e


@router.delete("/{id}", status_code=204)
async def delete_conversation_endpoint(
    id: int, db: Annotated[AsyncSession, Depends(get_session)]
):
    try:
        deleted = await delete_conversation(conversation_id=id, db=db)
        if not deleted:
            raise HTTPException(status_code=404, detail="Conversation not found")
        # 204 No Content
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting conversation",
        ) from e
