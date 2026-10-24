import { Route, Routes } from 'react-router-dom'

import CourseHome from './pages/CourseHome'
import Dashboard from './pages/Dashboard'
import InstructorAnalytics from './pages/InstructorAnalytics'
import NotFound from './pages/NotFound'
import PlaceholderPage from './pages/PlaceholderPage'
import AppLayout from './shell/AppLayout'
import CourseLayout from './shell/CourseLayout'
import { COURSE_TABS, type CourseTab } from './shell/courseTabs'

function tabElement(tab: CourseTab) {
  if (tab.path === '') return <CourseHome />
  if (tab.path === 'analytics') return <InstructorAnalytics />
  return <PlaceholderPage title={tab.label} phase={tab.phase} />
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="courses/:courseId" element={<CourseLayout />}>
          {COURSE_TABS.map((tab) =>
            tab.path === '' ? (
              <Route key="home" index element={tabElement(tab)} />
            ) : (
              <Route key={tab.path} path={tab.path} element={tabElement(tab)} />
            ),
          )}
          <Route path="*" element={<NotFound />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
