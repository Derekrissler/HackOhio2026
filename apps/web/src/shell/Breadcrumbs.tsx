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

  // Breadcrumb draws a separator after every child but the last, so pass no `false` children.
  const crumbs = tab
    ? [
        <BreadcrumbLink key="course" href={home} onClick={link(home)}>
          {course.code}
        </BreadcrumbLink>,
        <BreadcrumbLink key="tab" isCurrentPage>
          {tab.label}
        </BreadcrumbLink>,
      ]
    : [
        <BreadcrumbLink key="course" isCurrentPage>
          {course.code}
        </BreadcrumbLink>,
      ]

  return <Breadcrumb label="You are here:">{crumbs}</Breadcrumb>
}
