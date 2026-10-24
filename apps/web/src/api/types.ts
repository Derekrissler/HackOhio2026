// Hand-written mirrors of apps/api/app/schemas.py. Timestamps are naive UTC ISO strings;
// parse them with parseUtc() from ../format.

export type Role = 'student' | 'teacher'
export type AssessmentKind = 'homework' | 'quiz' | 'exam'
export type WorkflowState = 'unsubmitted' | 'submitted' | 'graded'

export interface DemoUser {
  id: number
  name: string
  sortable_name: string
  role_summary: 'Teacher' | 'Student'
}

export interface Me {
  id: number
  name: string
  email: string | null
  enrollments: { course_id: number; role: Role }[]
}

export interface Course {
  id: number
  code: string
  name: string
  term: string | null
  role: Role
}

export interface AnalyticsSummary {
  course_id: number
  status: string
}

export interface AnalyticsCourse {
  id: string
  code: string
  title: string
  canvas_id: string | null
  role: 'student' | 'instructor' | 'ta'
}

export interface AnalyticsPerformance {
  id: string
  scope: 'class_outcome' | 'assessment_question' | 'student_outcome'
  outcome_id: string | null
  assessment_id: string | null
  question_id: string | null
  label: string
  mean_student_ratio: number | null
  pooled_score_ratio: number | null
  observed_score_ratio: number | null
  eligible_students: number | null
  assessed_students: number | null
  evidence_coverage_ratio: number | null
  score_observations: number | null
  evidence_count: number | null
  insufficient_evidence: boolean
  suppressed: boolean
}

export interface AnalyticsDashboard {
  course_id: string
  status: 'ready' | 'no_results' | 'stale' | 'incomplete' | 'insufficient_evidence'
  run_id: string | null
  computed_at: string | null
  performance: AnalyticsPerformance[]
  clusters: {
    id: string
    error_code: string
    unique_students: number
    evidence_count: number
    assessment_origin: string
    assistance: string
    interpretation_limit: string
  }[]
  interpretation: string
}

export interface Feedback {
  id: number
  kind: 'submission_comment' | 'question_comment' | 'rubric_comment'
  author_name: string
  text: string
  created_at: string
  visible_to_student: boolean
}

export interface MySubmission {
  id: number
  workflow_state: WorkflowState
  score: number | null
  submitted_at: string | null
  late: boolean
  missing: boolean
  excused: boolean
}

export interface AssessmentSummary {
  id: number
  title: string
  kind: AssessmentKind
  group_id: number
  points_possible: number
  due_at: string | null
  module_label: string | null
  my_submission: MySubmission | null
  submission_counts: { submitted: number; graded: number; total: number } | null
}

export interface AssignmentGroup {
  id: number
  name: string
  weight: number
  assessments: AssessmentSummary[]
}

export interface OutcomeRef {
  id: number
  code: string
  title: string
}

export interface Question {
  id: number
  label: string
  parent_id: number | null
  position: number
  prompt_html: string
  question_type: string
  points_possible: number
  choices: string[] | null
  answer_key: string | null
  outcomes: OutcomeRef[]
  source_page: number | null
}

export interface RubricCriterion {
  id: number
  description: string
  long_description: string | null
  points: number
  outcome: OutcomeRef | null
}

export interface AssessmentDetail {
  id: number
  title: string
  kind: AssessmentKind
  group_name: string
  group_weight: number
  points_possible: number
  due_at: string | null
  module_label: string | null
  description_html: string | null
  submission_types: string[]
  questions: Question[] | null
  questions_hidden_reason: string | null
  rubric: RubricCriterion[]
  my_submission: MySubmission | null
}

export interface SubmissionRow {
  id: number
  user_id: number
  user_name: string
  sortable_name: string
  workflow_state: WorkflowState
  score: number | null
  submitted_at: string | null
  late: boolean
  missing: boolean
  excused: boolean
}

export interface FileRef {
  id: number
  display_name: string
  mime: string
  page_count: number | null
  has_text_layer: boolean
  url: string
}

export interface QuestionResponse {
  question_id: number
  label: string
  parent_label: string | null
  prompt_html: string
  question_type: string
  choices: string[] | null
  response: string | null
  points_awarded: number | null
  points_possible: number
  is_correct: boolean | null
  answer_key: string | null
  graded_by: 'canvas_auto' | 'instructor' | 'manual_entry'
  source_page: number | null
  comments: Feedback[]
}

export interface RubricScore {
  criterion_id: number
  description: string
  points: number | null
  points_possible: number
  comment: string | null
}

export interface SubmissionDetail {
  id: number
  assessment: AssessmentSummary
  user_id: number
  user_name: string
  workflow_state: WorkflowState
  submitted_at: string | null
  graded_at: string | null
  score: number | null
  late: boolean
  missing: boolean
  excused: boolean
  results_visible: boolean
  file: FileRef | null
  responses: QuestionResponse[]
  rubric: RubricScore[]
  comments: Feedback[]
}

export interface GroupGrade {
  id: number
  name: string
  weight: number
  earned: number
  possible: number
  percent: number | null
}

export interface GradeRow {
  assessment_id: number
  title: string
  kind: AssessmentKind
  group_id: number
  due_at: string | null
  points_possible: number
  submission_id: number | null
  workflow_state: WorkflowState
  score: number | null
  late: boolean
  missing: boolean
  excused: boolean
  comments: Feedback[]
  rubric: RubricScore[]
}

export interface Grades {
  user_id: number
  user_name: string
  weighted: boolean
  current_percent: number | null
  groups: GroupGrade[]
  rows: GradeRow[]
}

export interface GradebookCell {
  submission_id: number | null
  workflow_state: WorkflowState
  score: number | null
  late: boolean
  missing: boolean
  excused: boolean
}

export interface Gradebook {
  assessments: AssessmentSummary[]
  students: { id: number; name: string; sortable_name: string; current_percent: number | null; cells: GradebookCell[] }[]
}

export interface Outcome {
  id: number
  code: string
  title: string
  description: string | null
}

export interface Syllabus {
  syllabus_html: string | null
  outcomes: Outcome[]
  summary: AssessmentSummary[]
}

export interface RecentFeedback extends Feedback {
  submission_id: number
  assessment_title: string
}

export interface Home {
  course: Course
  upcoming: AssessmentSummary[]
  recent_feedback: RecentFeedback[]
  needs_grading: { assessment_id: number; title: string; count: number }[]
}

export interface Module {
  label: string
  position: number
  materials: { id: number; title: string; kind: string; file: FileRef }[]
}
