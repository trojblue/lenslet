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

  it('renders a dismiss action for the browser zoom warning', () => {
    const html = renderStatusBar({
      browserZoomPercent: 110,
      onDismissBrowserZoomWarning: noop,
    })

    expect(html).toContain('Browser zoom 110%.')
    expect(html).toContain('aria-label="Dismiss browser zoom warning"')
  })

  it('renders a dismiss action for the read-only workspace warning', () => {
    const html = renderStatusBar({
      persistenceEnabled: false,
      onDismissPersistenceWarning: noop,
    })

    expect(html).toContain('Not persisted.')
    expect(html).toContain('aria-label="Dismiss persistence warning"')
  })

  it('hides the read-only workspace warning after dismissal', () => {
    const html = renderStatusBar({
      persistenceEnabled: false,
      showPersistenceWarning: false,
    })

    expect(html).not.toContain('Not persisted.')
  })

  it('renders a dismiss action for table source warnings', () => {
    const html = renderStatusBar({
      tableSourceWarning: 'The selected source column produced no loadable gallery entries.',
      onDismissTableSourceWarning: noop,
    })

    expect(html).toContain('Image source warning.')
    expect(html).toContain('no loadable gallery entries')
    expect(html).toContain('aria-label="Dismiss image source warning"')
  })

  it('renders derived metric warnings', () => {
    const html = renderStatusBar({
      derivedMetricWarning: 'Derived score inputs unavailable in this view: q2.',
    })

    expect(html).toContain('Derived score.')
    expect(html).toContain('inputs unavailable')
    expect(html).toContain('q2')
  })
})
