import { Spinner, View } from '@instructure/ui'

import { useAnalyticsSummary } from '../api/hooks'
import ApiErrorAlert from '../shell/ApiErrorAlert'
import { useCurrentCourse } from '../shell/CourseLayout'
import PlaceholderPage, { useDocumentTitle } from './PlaceholderPage'

/** Access is decided by the API (teacher only), not by the nav, so a typed-in URL is covered too. */
export default function InstructorAnalytics() {
  const course = useCurrentCourse()
  const { error, isPending } = useAnalyticsSummary(course.id)
  useDocumentTitle('Instructor Analytics')

  if (isPending) {
    return (
      <View as="div" padding="large" textAlign="center">
        <Spinner renderTitle="Loading analytics" />
      </View>
    )
  }
  if (error) return <ApiErrorAlert error={error} />
  return <PlaceholderPage title="Instructor Analytics" phase={7} />
}
