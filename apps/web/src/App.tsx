import { Route, Routes } from 'react-router-dom'

import AssessmentDetail from './pages/AssessmentDetail'
import Assignments from './pages/Assignments'
import CourseHome from './pages/CourseHome'
import Dashboard from './pages/Dashboard'
import Files from './pages/Files'
import Grades from './pages/Grades'
import InstructorAnalytics from './pages/InstructorAnalytics'
import NotFound from './pages/NotFound'
import PlaceholderPage from './pages/PlaceholderPage'
import SubmissionDetail from './pages/SubmissionDetail'
import Syllabus from './pages/Syllabus'
import AppLayout from './shell/AppLayout'
import CourseLayout from './shell/CourseLayout'

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="courses/:courseId" element={<CourseLayout />}>
          <Route index element={<CourseHome />} />
          <Route path="syllabus" element={<Syllabus />} />
          <Route path="assignments" element={<Assignments />} />
          <Route path="assignments/:assessmentId" element={<AssessmentDetail />} />
          <Route path="quizzes" element={<Assignments title="Quizzes" kinds={['quiz']} />} />
          <Route path="quizzes/:assessmentId" element={<AssessmentDetail />} />
          <Route path="submissions/:submissionId" element={<SubmissionDetail />} />
          <Route path="grades" element={<Grades />} />
          <Route path="grades/:userId" element={<Grades />} />
          <Route path="files" element={<Files />} />
          <Route path="insights" element={<PlaceholderPage title="Learning Insights" phase={6} />} />
          <Route path="analytics" element={<InstructorAnalytics />} />
          <Route path="*" element={<NotFound />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
