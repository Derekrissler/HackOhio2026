import { Flex, Heading, IconInfoLine, Text, View } from '@instructure/ui'
import { useEffect, type ReactNode } from 'react'

export function useDocumentTitle(title: string) {
  useEffect(() => {
    document.title = title
  }, [title])
}

export default function PlaceholderPage({
  title,
  phase,
  children,
}: {
  title: string
  phase: number
  children?: ReactNode
}) {
  useDocumentTitle(title)
  return (
    <>
      <Heading level="h1" margin="0 0 medium">
        {title}
      </Heading>
      {children}
      <View as="div" borderWidth="small" borderRadius="medium" padding="medium" margin="medium 0 0">
        <Flex gap="small" alignItems="start">
          <Flex.Item>
            <IconInfoLine size="x-small" color="secondary" />
          </Flex.Item>
          <Flex.Item shouldShrink>
            <Heading level="h2" variant="titleCardMini">
              Coming in Phase {phase}
            </Heading>
            <Text color="secondary">This page is a placeholder in the current build.</Text>
          </Flex.Item>
        </Flex>
      </View>
    </>
  )
}
