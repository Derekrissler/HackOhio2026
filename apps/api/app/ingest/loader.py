"""Canonical bundles → database rows. External ids are resolved to database ids here only."""

from pathlib import Path

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from app import models as m
from app.db import Base
from app.ingest.canonical import CourseBundle
from app.ingest.canvas_json_adapter import CanvasJsonAdapter
from app.ingest.manual_adapter import ManualAdapter

# Bump when the schema changes; init_db() rebuilds a database with a different version.
SCHEMA_VERSION = 4


def read_seed(seed_dir: Path) -> list[CourseBundle]:
    canvas = CanvasJsonAdapter(seed_dir / "canvas_json", storage_prefix=f"{seed_dir.name}/")
    manual = ManualAdapter(seed_dir / "manual")
    return [manual.apply(canvas.read_course(cid)) for cid in canvas.course_ids()]


def load(bundle: CourseBundle, session: Session) -> m.Course:
    source = "canvas"

    users: dict[str, int] = {}
    for u in bundle.users:
        row = session.scalar(select(m.User).where(m.User.external_id == u.external_id))
        if row is None:
            row = m.User(external_id=u.external_id, source=source, name=u.name,
                         sortable_name=u.sortable_name, email=u.email)
            session.add(row)
            session.flush()
        users[u.external_id] = row.id

    c = bundle.course
    course = m.Course(external_id=c.external_id, source=source, code=c.code, name=c.name, term=c.term,
                      syllabus_html=c.syllabus_html, apply_group_weights=c.apply_group_weights,
                      start_at=c.start_at, end_at=c.end_at)
    session.add(course)
    session.flush()

    session.add_all(m.Enrollment(external_id=e.external_id, source=source, course_id=course.id,
                                 user_id=users[e.user], role=e.role) for e in bundle.enrollments)
    teacher_id = next((users[e.user] for e in bundle.enrollments if e.role == "teacher"), None)

    outcomes = {}
    for o in bundle.outcomes:
        row = m.LearningOutcome(external_id=o.external_id, source=source, course_id=course.id, code=o.code,
                                title=o.title, description=o.description, position=o.position)
        session.add(row)
        session.flush()
        outcomes[o.external_id] = row.id

    groups = {}
    for g in bundle.groups:
        row = m.AssignmentGroup(external_id=g.external_id, source=source, course_id=course.id, name=g.name,
                                group_weight=g.weight, position=g.position)
        session.add(row)
        session.flush()
        groups[g.external_id] = row.id

    files = {}
    for f in bundle.files:
        row = m.File(external_id=f.external_id, source=source, course_id=course.id,
                     owner_user_id=users.get(f.owner) if f.owner else None, display_name=f.display_name,
                     filename=f.filename, mime=f.mime, storage_path=f.storage_path, size=f.size,
                     sha256=f.sha256, page_count=f.page_count, has_text_layer=f.has_text_layer)
        session.add(row)
        session.flush()
        files[f.external_id] = row.id

    session.add_all(m.CourseMaterial(external_id=x.external_id, source=source, course_id=course.id,
                                     file_id=files[x.file], title=x.title, kind=x.kind,
                                     module_label=x.module_label, module_position=x.module_position,
                                     position=x.position) for x in bundle.materials)

    assessments, questions, criteria = {}, {}, {}
    for a in bundle.assessments:
        row = m.Assessment(external_id=a.external_id, source=source, course_id=course.id,
                           assignment_group_id=groups[a.group], title=a.title, kind=a.kind,
                           points_possible=a.points_possible, due_at=a.due_at, submission_types=a.submission_types,
                           description_html=a.description_html, module_label=a.module_label,
                           position=a.position, quiz_external_id=a.quiz_external_id)
        session.add(row)
        session.flush()
        assessments[a.external_id] = row.id
        for q in a.questions:  # parents precede children in every adapter
            qrow = m.Question(external_id=q.external_id, source=q.source, assessment_id=row.id,
                              parent_question_id=questions[q.parent] if q.parent else None, label=q.label,
                              position=q.position, prompt_html=q.prompt_html, question_type=q.question_type,
                              points_possible=q.points_possible, answer_key=q.answer_key, choices=q.choices,
                              source_page=q.source_page)
            session.add(qrow)
            session.flush()
            questions[q.external_id] = qrow.id
        for r in a.rubric:
            crow = m.RubricCriterion(external_id=r.external_id, source=source, assessment_id=row.id,
                                     description=r.description, long_description=r.long_description,
                                     points=r.points, position=r.position,
                                     learning_outcome_id=outcomes.get(r.outcome) if r.outcome else None)
            session.add(crow)
            session.flush()
            criteria[(a.external_id, r.external_id)] = crow.id

    session.add_all(m.QuestionOutcome(question_id=questions[x.question], outcome_id=outcomes[x.outcome],
                                      weight=x.weight, source=x.source) for x in bundle.alignments)

    q_points = {q.external_id: q.points_possible for a in bundle.assessments for q in a.questions}
    for s in bundle.submissions:
        sub = m.Submission(external_id=s.external_id, source=source, assessment_id=assessments[s.assessment],
                           user_id=users[s.user], attempt=s.attempt, submitted_at=s.submitted_at,
                           graded_at=s.graded_at, score=s.score, grade=s.grade, excused=s.excused, late=s.late,
                           missing=s.missing, workflow_state=s.workflow_state,
                           file_id=files.get(s.file) if s.file else None)
        session.add(sub)
        session.flush()
        responses = {}
        for r in s.responses:
            rrow = m.QuestionResponse(submission_id=sub.id, question_id=questions[r.question], response=r.response,
                                      points_awarded=r.points_awarded,
                                      points_possible=q_points[r.question],
                                      is_correct=r.is_correct, graded_by=r.graded_by)
            session.add(rrow)
            session.flush()
            responses[r.question] = rrow.id
        for rs in s.rubric_scores:
            session.add(m.RubricScore(submission_id=sub.id, criterion_id=criteria[(s.assessment, rs.criterion)],
                                      points=rs.points, comment=rs.comment))
        for f in s.feedback:
            session.add(m.Feedback(external_id=f.external_id, source=f.source, submission_id=sub.id,
                                   question_response_id=responses.get(f.question) if f.question else None,
                                   author_id=users.get(f.author, teacher_id), kind=f.kind, text=f.text,
                                   attempt=f.attempt, created_at=f.created_at,
                                   visible_to_student=f.visible_to_student))
    session.flush()
    return course


def rebuild(engine: Engine, seed_dir: Path) -> None:
    """Drop and recreate every table, then load the seed. Works while the API holds the file open."""
    from app import models  # noqa: F401  (registers tables)

    # drop_all matches tables by name; on the shared Supabase database that would hit the
    # pipeline's courses/feedback/questions tables. The Canvas shell is SQLite only.
    if engine.dialect.name != "sqlite":
        raise RuntimeError(f"rebuild() drops tables; refusing to run on {engine.dialect.name}. Unset DATABASE_URL.")
    bundles = read_seed(seed_dir)  # parse first: a bad seed leaves the old database intact
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for bundle in bundles:
            load(bundle, session)
        session.commit()
    with engine.begin() as conn:
        conn.execute(text(f"PRAGMA user_version = {SCHEMA_VERSION}"))
