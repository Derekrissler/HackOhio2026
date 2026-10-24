import { useParams } from 'react-router-dom'

import { useMe } from '../api/hooks'
import { useCurrentCourse } from '../shell/CourseLayout'
import Gradebook from './Gradebook'
import StudentGrades from './StudentGrades'

/** Grades tab: teachers get the gradebook (or one student's summary at grades/:userId),
 * students get their own grade summary. */
export default function Grades() {
  const course = useCurrentCourse()
  const { userId } = useParams()
  const { data: me } = useMe()
  if (course.role === 'teacher') return userId ? <StudentGrades userId={Number(userId)} /> : <Gradebook />
  return me ? <StudentGrades userId={me.id} /> : null
}
