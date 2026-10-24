import { Heading, Link, Text, View } from '@instructure/ui'

import { useRouterLink } from '../shell/useRouterLink'
import { useDocumentTitle } from './PlaceholderPage'

export default function NotFound() {
  const link = useRouterLink()
  useDocumentTitle('Page not found')
  return (
    <View as="div" padding="medium large">
      <Heading level="h1" margin="0 0 small">
        Page not found
      </Heading>
      <Text as="p">
        This page doesn't exist.{' '}
        <Link href="/" onClick={link('/')}>
          Go to the Dashboard
        </Link>
      </Text>
    </View>
  )
}
