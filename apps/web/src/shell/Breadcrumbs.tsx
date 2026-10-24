import { Breadcrumb, BreadcrumbLink } from '@instructure/ui'
import { useLocation } from 'react-router-dom'

import type { Course } from '../api/types'
import { COURSE_TABS } from './courseTabs'
import { useRouterLink } from './useRouterLink'

export default function Breadcrumbs({ course }: { course: Course }) {
  const { pathname } = useLocation()
  const link = useRouterLink()
  const segment = pathname.split('/')[3] ?? ''
  const tab = segment ? COURSE_TABS.find((t) => t.path === segment) : undefined
  const home = `/courses/${course.id}`

  return (
    <Breadcrumb label="You are here:">
      {tab ? (
        <BreadcrumbLink href={home} onClick={link(home)}>
          {course.code}
        </BreadcrumbLink>
      ) : (
        <BreadcrumbLink isCurrentPage>{course.code}</BreadcrumbLink>
      )}
      {tab && <BreadcrumbLink isCurrentPage>{tab.label}</BreadcrumbLink>}
    </Breadcrumb>
  )
}
