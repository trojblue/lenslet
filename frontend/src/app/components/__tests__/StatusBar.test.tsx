import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import StatusBar from '../StatusBar'

const noop = () => {}

function renderStatusBar(
  overrides: Partial<Parameters<typeof StatusBar>[0]> = {},
): string {
  return renderToStaticMarkup(
    <StatusBar
      persistenceEnabled
      indexing={null}
      offViewSummary={null}
      onClearOffView={noop}
      browserZoomPercent={null}
      {...overrides}
    />,
  )
}

describe('StatusBar indexing banner lifecycle', () => {
  it('renders nothing when all banners are inactive', () => {
    expect(renderStatusBar()).toBe('')
  })

  it('shows indexing progress while startup indexing is running', () => {
    const html = renderStatusBar({
      indexing: {
        state: 'running',
        scope: '/shots',
        done: 12,
        total: 48,
      },
    })

    expect(html).toContain('Indexing in progress (/shots).')
    expect(html).toContain('12 / 48 complete.')
  })

  it('hides the indexing banner once indexing is ready', () => {
    const runningHtml = renderStatusBar({
      indexing: { state: 'running', done: 1, total: 2 },
    })
    const readyHtml = renderStatusBar({
      indexing: { state: 'ready', done: 2, total: 2 },
    })

    expect(runningHtml).toContain('Indexing in progress')
    expect(readyHtml).not.toContain('Indexing in progress')
  })

  it('shows a failure banner when indexing errors', () => {
    const html = renderStatusBar({
      indexing: {
        state: 'error',
        error: 'forced warm index failure',
      },
    })

    expect(html).toContain('Indexing failed.')
    expect(html).toContain('forced warm index failure')
  })

  it('shows explicit switch action when scan-stable completion banner is active', () => {
    const html = renderStatusBar({
      showSwitchToMostRecentBanner: true,
      onSwitchToMostRecent: noop,
    })

    expect(html).toContain('Indexing complete.')
    expect(html).toContain('Switch to Most recent')
  })
})
