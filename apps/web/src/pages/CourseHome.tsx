import { Text } from '@instructure/ui'

import { useCurrentCourse } from '../shell/CourseLayout'
import PlaceholderPage from './PlaceholderPage'

export default function CourseHome() {
  const course = useCurrentCourse()
  return (
    <PlaceholderPage title={course.name} phase={3}>
      <Text as="p" color="secondary">
        {[course.code, course.term, `Enrolled as ${course.role}`].filter(Boolean).join(' · ')}
      </Text>
    </PlaceholderPage>
  )
}
