"""Supabase access for the tutor.

Uses the service-role client, which bypasses row-level security, so every query here filters by the learner's
course (and learner, for personal data) explicitly. Retrieval always runs with p_student_safe=true, so unreleased
material and answer keys can't reach the tutor model.
"""

from datetime import datetime, timedelta, timezone

from tutor.models import Assessment, Chunk, Learner, Mode, Session, Turn

WEAK_RATIO = 0.7  # observed_score_ratio below this marks an outcome to boost in retrieval
# A bulk insert sends the union of the rows' keys and nulls the gaps, skipping column defaults.
TURN_DEFAULTS = {"pedagogical_move": None, "hint_level": None, "cited_chunk_ids": [], "policy_decision": None}


class SupabaseTutorRepo:
    def __init__(self, client):
        self.db = client

    def learner(self, canvas_course_id: str, pseudonym: str) -> Learner | None:
        course = self.db.table("courses").select("id").eq("canvas_id", canvas_course_id).limit(1).execute().data
        if not course:
            return None
        rows = (self.db.table("learners").select("id").eq("course_id", course[0]["id"])
                .eq("pseudonym", pseudonym).limit(1).execute().data)
        return Learner(course[0]["id"], rows[0]["id"], pseudonym) if rows else None

    def assessments(self, course_id: str) -> list[Assessment]:
        rows = (self.db.table("assessments").select("id,code,title,integrity_status,answers_released,canvas_id")
                .eq("course_id", course_id).order("code").execute().data)
        texts: dict[str, list[str]] = {}
        for q in (self.db.table("questions").select("assessment_id,text").eq("course_id", course_id)
                  .order("position").execute().data):
            texts.setdefault(q["assessment_id"], []).append(q["text"] or "")
        return [Assessment(r["id"], r["code"], r["title"], r["integrity_status"], r["answers_released"],
                           "\n".join(texts.get(r["id"], [])), r["canvas_id"]) for r in rows]

    def outcome_ids(self, course_id: str) -> set[str]:
        return {r["id"] for r in self.db.table("outcomes").select("id").eq("course_id", course_id).execute().data}

    def answer_texts(self, course_id: str, assessment_ids: list[str]) -> list[str]:
        if not assessment_ids:
            return []
        rows = (self.db.table("question_answer_keys").select("answer,solution,questions!inner(assessment_id)")
                .eq("course_id", course_id).in_("questions.assessment_id", assessment_ids).execute().data)
        return [t for r in rows for t in (r["answer"], r["solution"]) if t]

    def weak_outcomes(self, course_id: str, learner_id: str) -> list[str]:
        rows = (self.db.table("analytics_results").select("outcome_id,metrics").eq("course_id", course_id)
                .eq("scope", "student_outcome").eq("subject_learner_id", learner_id).eq("is_stale", False)
                .execute().data)
        return [r["outcome_id"] for r in rows if r["outcome_id"]
                and (r["metrics"] or {}).get("observed_score_ratio") is not None
                and r["metrics"]["observed_score_ratio"] < WEAK_RATIO]

    def search(self, course_id: str, query: str, outcome_ids: list[str], k: int) -> list[Chunk]:
        rows = self.db.rpc("search_resource_chunks", {
            "p_course_id": course_id, "p_query": query, "p_embedding": None,
            "p_outcome_ids": outcome_ids, "p_k": k, "p_student_safe": True,
        }).execute().data
        return [Chunk(r["chunk_id"], r["title"] or "", r["content"], r["doc_type"], r["page"], r["slide"],
                      r["deep_link"]) for r in rows]

    def get_session(self, session_id: str) -> Session | None:
        rows = (self.db.table("tutor_sessions")
                .select("id,course_id,learner_id,assessment_id,outcome_id,assistance_mode")
                .eq("id", session_id).limit(1).execute().data)
        if not rows:
            return None
        r = rows[0]
        return Session(r["id"], r["course_id"], r["learner_id"], r["assessment_id"], r["outcome_id"],
                       r["assistance_mode"])

    def set_session_mode(self, session_id: str, mode: Mode) -> None:
        self.db.table("tutor_sessions").update({"assistance_mode": str(mode)}).eq("id", session_id).execute()

    def create_session(self, learner: Learner, mode: Mode, assessment_id: str | None,
                       outcome_id: str | None) -> Session:
        row = self.db.table("tutor_sessions").insert({
            "course_id": learner.course_id, "learner_id": learner.learner_id, "assessment_id": assessment_id,
            "outcome_id": outcome_id, "assistance_mode": str(mode),
        }).execute().data[0]
        return Session(row["id"], row["course_id"], row["learner_id"], row["assessment_id"], row["outcome_id"],
                       row["assistance_mode"])

    def history(self, session_id: str, limit: int) -> list[Turn]:
        rows = (self.db.table("tutor_turns").select("speaker,content,hint_level").eq("session_id", session_id)
                .order("created_at", desc=True).limit(limit).execute().data)
        return [Turn(r["speaker"], r["content"], r["hint_level"]) for r in reversed(rows)]

    def session_turns(self, session_id: str) -> list[dict]:
        return (self.db.table("tutor_turns")
                .select("speaker,content,pedagogical_move,hint_level,cited_chunk_ids,created_at")
                .eq("session_id", session_id).order("created_at").execute().data)

    def add_turns(self, session_id: str, turns: list[dict]) -> None:
        # Explicit, increasing timestamps: rows inserted together would otherwise share now() and lose their order.
        start = datetime.now(timezone.utc)
        self.db.table("tutor_turns").insert([
            {**TURN_DEFAULTS, **t, "session_id": session_id,
             "created_at": (start + timedelta(milliseconds=i)).isoformat()}
            for i, t in enumerate(turns)
        ]).execute()
