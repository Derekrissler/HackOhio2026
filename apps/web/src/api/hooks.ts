import { useQuery } from '@tanstack/react-query'

import { useDemoUser } from '../shell/demoUser'
import { apiGet } from './client'
import type {
  AnalyticsSummary,
  AssessmentDetail,
  AssignmentGroup,
  Course,
  DemoUser,
  Gradebook,
  Grades,
  Home,
  Me,
  Module,
  SubmissionDetail,
  SubmissionRow,
  Syllabus,
} from './types'

// The demo user id is part of every query key, so switching users can never show
// another user's cached response.
function useUserQuery<T>(path: string, enabled = true) {
  const { userId } = useDemoUser()
  return useQuery({ queryKey: [path, userId], queryFn: () => apiGet<T>(path, userId), enabled })
}

export const useDemoUsers = () =>
  useQuery({ queryKey: ['/demo/users'], queryFn: () => apiGet<DemoUser[]>('/demo/users') })

export const useMe = () => useUserQuery<Me>('/me')
export const useCourses = () => useUserQuery<Course[]>('/courses')
export const useCourse = (courseId: string) => useUserQuery<Course>(`/courses/${courseId}`)
export const useAnalyticsSummary = (courseId: number) =>
  useUserQuery<AnalyticsSummary>(`/courses/${courseId}/analytics/summary`)

export const useHome = (courseId: number) => useUserQuery<Home>(`/courses/${courseId}/home`)
export const useSyllabus = (courseId: number) => useUserQuery<Syllabus>(`/courses/${courseId}/syllabus`)
export const useAssignmentGroups = (courseId: number) =>
  useUserQuery<AssignmentGroup[]>(`/courses/${courseId}/assignment_groups`)
export const useAssessment = (courseId: number, assessmentId: string) =>
  useUserQuery<AssessmentDetail>(`/courses/${courseId}/assessments/${assessmentId}`)
export const useAssessmentSubmissions = (courseId: number, assessmentId: string, enabled: boolean) =>
  useUserQuery<SubmissionRow[]>(`/courses/${courseId}/assessments/${assessmentId}/submissions`, enabled)
export const useSubmission = (courseId: number, submissionId: number | string | undefined) =>
  useUserQuery<SubmissionDetail>(`/courses/${courseId}/submissions/${submissionId}`, submissionId !== undefined)
export const useGrades = (courseId: number, userId: number, enabled = true) =>
  useUserQuery<Grades>(`/courses/${courseId}/users/${userId}/grades`, enabled)
export const useGradebook = (courseId: number) => useUserQuery<Gradebook>(`/courses/${courseId}/gradebook`)
export const useMaterials = (courseId: number) => useUserQuery<Module[]>(`/courses/${courseId}/materials`)
