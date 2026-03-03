import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import Toolbar from '../../Toolbar'

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
  useMediaQuery: () => false,
}))

describe('Toolbar refresh trigger', () => {
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
      />,
    )

    expect(html).toContain('title="Refresh unavailable in static mode"')
    expect(html).toContain('aria-label="Refresh root folder"')
    expect(html).toContain('disabled=""')
  })
})
