import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import SyncIndicator from '../SyncIndicator'

const BASE_PROPS = {
  state: 'live' as const,
  syncLabel: 'Synced',
  connectionLabel: 'Connected',
  lastEditedLabel: 'just now',
  hasEdits: true,
  recentTouches: [{ path: '/sample.jpg', label: 'sample.jpg', timeLabel: '1m ago' }],
  isNarrow: false,
}

describe('SyncIndicator stable text slots', () => {
  it('reserves typing copy while local typing is inactive', () => {
    const html = renderToStaticMarkup(
      <SyncIndicator {...BASE_PROPS} localTypingActive={false} />,
    )

    expect(html).toContain('class="sync-indicator-local"')
    expect(html).toContain('data-active="false"')
  })

  it('fills the same slots while local typing is active', () => {
    const html = renderToStaticMarkup(
      <SyncIndicator {...BASE_PROPS} localTypingActive />,
    )

    expect(html).toContain('typing…')
    expect(html).toContain('data-active="true"')
  })
})
