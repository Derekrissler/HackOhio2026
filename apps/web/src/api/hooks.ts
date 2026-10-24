import { useQuery } from '@tanstack/react-query'

import { useDemoUser } from '../shell/demoUser'
import { apiGet } from './client'
import type { AnalyticsSummary, Course, DemoUser, Me } from './types'

// The demo user id is part of every query key, so switching users can never show
// another user's cached response.
function useUserQuery<T>(path: string) {
  const { userId } = useDemoUser()
  return useQuery({ queryKey: [path, userId], queryFn: () => apiGet<T>(path, userId) })
}

export const useDemoUsers = () =>
  useQuery({ queryKey: ['/demo/users'], queryFn: () => apiGet<DemoUser[]>('/demo/users') })

export const useMe = () => useUserQuery<Me>('/me')
export const useCourses = () => useUserQuery<Course[]>('/courses')
export const useCourse = (courseId: string) => useUserQuery<Course>(`/courses/${courseId}`)
export const useAnalyticsSummary = (courseId: number) =>
  useUserQuery<AnalyticsSummary>(`/courses/${courseId}/analytics/summary`)
