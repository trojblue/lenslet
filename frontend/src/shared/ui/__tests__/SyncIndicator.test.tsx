import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import SyncIndicator from '../SyncIndicator'

const BASE_PROPS = {
  state: 'live' as const,
  syncLabel: 'Synced',
  connectionLabel: 'Connected',
  lastEditedLabel: 'just now',
  hasEdits: true,
  unsaved: false,
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

  it('shows unsaved edits in the same slot without opening the card', () => {
    const html = renderToStaticMarkup(
      <SyncIndicator {...BASE_PROPS} localTypingActive unsaved syncLabel="Not saved — a.jpg, retrying" />,
    )

    expect(html).toContain('>unsaved<')
    expect(html).toContain('data-unsaved="true"')
    expect(html).toContain('title="Not saved — a.jpg, retrying"')
  })
})
