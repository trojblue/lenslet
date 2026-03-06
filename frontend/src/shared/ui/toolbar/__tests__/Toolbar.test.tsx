import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import Toolbar from '../../Toolbar'

const mediaQueryMock = vi.fn<(query: string) => boolean>(() => false)

vi.mock('../../Dropdown', () => ({
  default: () => <div data-dropdown-mock="1" />,
}))

vi.mock('../../SyncIndicator', () => ({
  default: () => <div data-sync-indicator-mock="1" />,
}))

vi.mock('../ToolbarFilterMenu', () => ({
  default: () => <div data-filter-menu-mock="1" />,
}))

vi.mock('../ToolbarMobileDrawer', () => ({
  default: () => <div data-mobile-drawer-mock="1" />,
}))

vi.mock('../../../hooks/useMediaQuery', () => ({
  useMediaQuery: (query: string) => mediaQueryMock(query),
}))

describe('Toolbar refresh trigger', () => {
  beforeEach(() => {
    mediaQueryMock.mockReset()
    mediaQueryMock.mockImplementation(() => false)
  })

  it('renders the root refresh icon button when refresh action is provided', () => {
    const html = renderToStaticMarkup(
      <Toolbar
        onSearch={() => {}}
        onRefreshRoot={() => {}}
        refreshEnabled
        themePreset="teal"
        onThemePresetChange={() => {}}
        autoloadImageMetadata={false}
        onAutoloadImageMetadataChange={() => {}}
        compareOrderMode="gallery"
        onCompareOrderModeChange={() => {}}
      />,
    )

    expect(html).toContain('aria-label="Refresh root folder"')
    expect(html).toContain('title="Refresh root folder"')
  })

  it('shows disabled reason in the refresh button tooltip', () => {
    const html = renderToStaticMarkup(
      <Toolbar
        onSearch={() => {}}
        onRefreshRoot={() => {}}
        refreshEnabled={false}
        refreshDisabledReason="Refresh unavailable in static mode"
        themePreset="teal"
        onThemePresetChange={() => {}}
        autoloadImageMetadata={false}
        onAutoloadImageMetadataChange={() => {}}
        compareOrderMode="gallery"
        onCompareOrderModeChange={() => {}}
      />,
    )

    expect(html).toContain('title="Refresh unavailable in static mode"')
    expect(html).toContain('aria-label="Refresh root folder"')
    expect(html).toContain('disabled=""')
  })

  it('keeps action slots mounted and non-focusable when hidden in viewer mode', () => {
    const html = renderToStaticMarkup(
      <Toolbar
        onSearch={() => {}}
        viewerActive
        onBack={() => {}}
        onRefreshRoot={() => {}}
        onUploadClick={() => {}}
        themePreset="teal"
        onThemePresetChange={() => {}}
        autoloadImageMetadata={false}
        onAutoloadImageMetadataChange={() => {}}
        compareOrderMode="gallery"
        onCompareOrderModeChange={() => {}}
      />,
    )

    expect(html).toContain('data-toolbar-slot="back"')
    expect(html).toMatch(/data-toolbar-control="back"[^>]*aria-hidden="false"/)
    expect(html).toMatch(/data-toolbar-control="refresh"(?=[^>]*aria-hidden="true")(?=[^>]*disabled="")(?=[^>]*tabindex="-1")/)
    expect(html).toMatch(/data-toolbar-control="upload"(?=[^>]*aria-hidden="true")(?=[^>]*disabled="")(?=[^>]*tabindex="-1")/)
    expect(html).toMatch(/data-toolbar-control="search-desktop"(?=[^>]*aria-hidden="true")(?=[^>]*disabled="")(?=[^>]*tabindex="-1")/)
  })

  it('keeps mobile search row mounted but disabled when closed on narrow layouts', () => {
    mediaQueryMock.mockImplementation((query: string) => query.includes('900px'))

    const html = renderToStaticMarkup(
      <Toolbar
        onSearch={() => {}}
        onRefreshRoot={() => {}}
        themePreset="teal"
        onThemePresetChange={() => {}}
        autoloadImageMetadata={false}
        onAutoloadImageMetadataChange={() => {}}
        compareOrderMode="gallery"
        onCompareOrderModeChange={() => {}}
      />,
    )

    expect(html).toContain('data-toolbar-slot="search-row"')
    expect(html).toMatch(/data-toolbar-control="search-mobile"[^>]*disabled=""[^>]*tabindex="-1"/)
  })
})
