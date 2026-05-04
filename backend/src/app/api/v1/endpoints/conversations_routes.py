from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logger import log
from app.crud.conversation_crud import (
    add_message,
    create_conversation,
    delete_conversation,
    get_conversation_with_messages,
    list_conversations,
    update_conversation_title,
)
from app.db.session import get_session
from app.schemas.conversation_schema import (
    ConversationExtendedRead,
    ConversationRead,
    CreateConversationRequest,
    CreateConversationResponse,
    RoleEnum,
    UpdateConversationRequest,
)

router = APIRouter()


@router.post("/", response_model=CreateConversationResponse, status_code=201)
async def create_conversation_endpoint(
    req: CreateConversationRequest,
    use_case: str,
    db: Annotated[AsyncSession, Depends(get_session)],
):
    """
    This endpoint creates a new conversation.
    Args:
        req: The request body containing the model, message, and use case.
    Returns:
        A 201 Created response with the created conversation.
        A 500 Internal Server Error response if there is an error creating the conversation.
    """
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
    """
    This endpoint lists all conversations.
    Args:
        use_case: The use case of the conversations to list.
    Returns:
        A 200 OK response with the list of conversations.
        A 500 Internal Server Error response if there is an error listing the conversations.
    """
    try:
        convos = await list_conversations(db=db, use_case=use_case)
        return [
            ConversationRead.model_validate(c, from_attributes=True) for c in convos
        ]

    except SQLAlchemyError as e:
        log.exception("Error listing conversations")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error listing conversations",
        ) from e


@router.get("/{id}")
async def get_conversation_endpoint(
    id: int, db: Annotated[AsyncSession, Depends(get_session)]
):
    """
    This endpoint retrieves a conversation and all its messages.
    Args:
        id: The ID of the conversation to retrieve.
    Returns:
        A 200 OK response with the conversation and its messages.
        A 404 Not Found response if the conversation is not found.
        A 500 Internal Server Error response if there is an error retrieving the conversation.
    """
    try:
        convo = await get_conversation_with_messages(conversation_id=id, db=db)
        if not convo:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return ConversationExtendedRead.model_validate(convo, from_attributes=True)

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving the conversation",
        ) from e


@router.patch("/{id}", response_model=ConversationRead)
async def update_conversation_endpoint(
    id: int,
    req: UpdateConversationRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
):
    """
    This endpoint updates the title of a conversation.
    Args:
        id: The ID of the conversation to update.
        req: The request body containing the new title.
    Returns:
        A 200 OK response with the updated conversation.
        A 404 Not Found response if the conversation is not found.
        A 500 Internal Server Error response if there is an error updating the conversation.
    """
    try:
        convo = await update_conversation_title(
            conversation_id=id, title=req.title.strip(), db=db
        )
        if not convo:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return ConversationRead.model_validate(convo, from_attributes=True)
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating conversation",
        ) from e


@router.delete("/{id}", status_code=204)
async def delete_conversation_endpoint(
    id: int, db: Annotated[AsyncSession, Depends(get_session)]
):
    """
    This endpoint deletes a conversation and all its messages.
    Args:
        id: The ID of the conversation to delete.
    Returns:
        A 204 No Content response if the conversation is deleted successfully.
        A 404 Not Found response if the conversation is not found.
        A 500 Internal Server Error response if there is an error deleting the conversation.
    """
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
