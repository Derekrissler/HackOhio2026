import { Flex, IconExternalLinkLine, Link, Text } from '@instructure/ui'

import type { FileRef } from '../api/types'

/** The browser's own PDF viewer in an iframe. Auth comes from the demo_user cookie. */
export default function PdfViewer({ file, page, height = '75vh' }: { file: FileRef; page?: number | null; height?: string }) {
  const src = `${file.url}#${page ? `page=${page}&` : ''}view=FitH`
  return (
    <div className="pdf-viewer">
      <Flex justifyItems="space-between" alignItems="center" margin="0 0 x-small" wrap="wrap" gap="x-small">
        <Text size="small" weight="bold">
          {file.display_name}
          {file.page_count ? ` · ${file.page_count} page${file.page_count === 1 ? '' : 's'}` : ''}
          {!file.has_text_layer && ' · scanned (no text layer)'}
        </Text>
        <Link href={file.url} target="_blank" renderIcon={<IconExternalLinkLine />} iconPlacement="end">
          Open in new tab
        </Link>
      </Flex>
      <iframe key={src} src={src} title={`PDF: ${file.display_name}`} style={{ height }} />
    </div>
  )
}
