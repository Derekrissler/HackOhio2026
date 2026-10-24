// Hand-written mirrors of apps/api/app/schemas.py. Phase 3 can generate these from /openapi.json.

export type Role = 'student' | 'teacher'

export interface DemoUser {
  id: number
  name: string
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
