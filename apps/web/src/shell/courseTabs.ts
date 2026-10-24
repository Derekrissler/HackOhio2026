import type { Role } from '../api/types'

export interface CourseTab {
  /** Route segment under /courses/:courseId ('' is the course home). */
  path: string
  label: string
  /** Roadmap phase that builds the real page (docs/PHASE1_PLAN.md §6). */
  phase: number
  onlyFor?: Role
}

export const COURSE_TABS: CourseTab[] = [
  { path: '', label: 'Home', phase: 3 },
  { path: 'syllabus', label: 'Syllabus', phase: 3 },
  { path: 'assignments', label: 'Assignments', phase: 3 },
  { path: 'quizzes', label: 'Quizzes', phase: 3 },
  { path: 'grades', label: 'Grades', phase: 3 },
  { path: 'files', label: 'Files', phase: 3 },
  { path: 'insights', label: 'Learning Insights', phase: 6, onlyFor: 'student' },
  { path: 'analytics', label: 'Instructor Analytics', phase: 7, onlyFor: 'teacher' },
]

export function getCourseNavItems(role: Role): CourseTab[] {
  return COURSE_TABS.filter((tab) => !tab.onlyFor || tab.onlyFor === role)
}
