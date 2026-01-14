import schemas
import fastapi
import dependencies
from database import crud, models, session
from sqlalchemy.ext.asyncio import AsyncSession

router = fastapi.APIRouter()


@router.post("/feedback", response_model=schemas.FeedbackResponse)
async def create_feedback(
    feedback: schemas.FeedbackRequest,
    db_session: AsyncSession = fastapi.Depends(session.get_db_session),
    current_user: models.User = fastapi.Depends(dependencies.get_current_active_user),
):

    feedback_create = models.Feedback(user_id=current_user.id, content=feedback.content)

    try:
        result: models.Feedback = await crud.create_feedback(
            feedback=feedback_create, db_session=db_session
        )
        feedback_response = schemas.FeedbackResponse(
            success=True, message=result.content, timestamp=result.created_at
        )
        return feedback_response
    except Exception as e:
        raise fastapi.HTTPException(
            status_code=500,
            detail=f"An error occurred while processing your feedback: {str(e)}",
        )
