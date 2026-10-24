import { Alert } from '@instructure/ui'

import { ApiError } from '../api/client'

const MESSAGES: Record<number, string> = {
  401: 'No demo user is selected. Choose one from Account in the left navigation.',
  403: "Access denied. You don't have permission to view this page.",
  404: 'Not found. This page or course does not exist.',
}

export default function ApiErrorAlert({ error }: { error: unknown }) {
  const status = error instanceof ApiError ? error.status : undefined
  const message = (status && MESSAGES[status]) ?? 'Something went wrong. Is the API server running?'
  return (
    <Alert variant={status === 403 ? 'warning' : 'error'} margin="medium 0">
      {message}
    </Alert>
  )
}
