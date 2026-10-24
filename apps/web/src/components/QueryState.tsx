import { Spinner, View } from '@instructure/ui'
import type { UseQueryResult } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import ApiErrorAlert from '../shell/ApiErrorAlert'

/** Renders loading and error states for a query, and `children(data)` once it has data. */
export default function QueryState<T>({
  query,
  label,
  children,
}: {
  query: UseQueryResult<T>
  label: string
  children: (data: T) => ReactNode
}) {
  if (query.isPending) {
    return (
      <View as="div" padding="large" textAlign="center">
        <Spinner renderTitle={`Loading ${label}`} size="small" />
      </View>
    )
  }
  if (query.isError) return <ApiErrorAlert error={query.error} />
  return <>{children(query.data)}</>
}
