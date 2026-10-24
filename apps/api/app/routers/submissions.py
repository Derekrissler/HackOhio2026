from fastapi import APIRouter

from app.auth import DbSession, Enrolled, get_submission, results_visible
from app.models import Assessment, File, User
from app.schemas import SubmissionDetailOut
from app.views import assessment_summary, file_ref, responses_out, rubric_scores_out, submission_comments

router = APIRouter(prefix="/api/courses/{course_id}", tags=["submissions"])


@router.get("/submissions/{submission_id}", response_model=SubmissionDetailOut)
def get_submission_detail(submission_id: int, enrollment: Enrolled, db: DbSession) -> SubmissionDetailOut:
    sub = get_submission(db, enrollment, submission_id)
    show = results_visible(enrollment, sub)
    return SubmissionDetailOut(
        id=sub.id,
        assessment=assessment_summary(db, enrollment, db.get(Assessment, sub.assessment_id)),
        user_id=sub.user_id,
        user_name=db.get(User, sub.user_id).name,
        workflow_state=sub.workflow_state,
        submitted_at=sub.submitted_at,
        graded_at=sub.graded_at if show else None,
        score=sub.score if show else None,
        late=sub.late,
        missing=sub.missing,
        excused=sub.excused,
        results_visible=show,
        file=file_ref(db.get(File, sub.file_id) if sub.file_id else None),
        responses=responses_out(db, enrollment, sub),
        rubric=rubric_scores_out(db, enrollment, sub),
        comments=submission_comments(db, enrollment, sub),
    )
