import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ToolbarMobileDrawer from '../ToolbarMobileDrawer'

vi.mock('../../Dropdown', () => ({
  default: () => <div data-dropdown-mock="1" />,
}))

const baseProps = {
  viewMode: 'grid' as const,
  currentSort: 'builtin:added',
  sortOnlyOptions: [{ label: 'Sort by', options: [{ value: 'builtin:added', label: 'Date added' }] }],
  sortDisabled: false,
  sortControlsDisabled: false,
  sortDir: 'desc' as const,
  isRandom: false,
  showSelectModeToggle: true,
  multiSelectMode: false,
  selectModeLabel: 'Select',
  uploadBusy: false,
  uploadDisabled: false,
  themePreset: 'teal' as const,
  autoloadImageMetadata: false,
  compareOrderMode: 'gallery' as const,
  filtersOpen: false,
  filtersRef: { current: null },
  totalFilterCount: 0,
  starFilterList: [],
  refreshEnabled: true,
  refreshBusy: false,
  leftOpen: true,
  rightOpen: true,
  onToggleSortDir: () => {},
  onToggleFilters: () => {},
  onRefreshRoot: () => {},
  onThemePresetChange: () => {},
  onAutoloadImageMetadataChange: () => {},
  onCompareOrderModeChange: () => {},
}

describe('ToolbarMobileDrawer theme mount', () => {
  it('renders shared ThemeSettingsMenu trigger in mobile drawer row', () => {
    const html = renderToStaticMarkup(
      <ToolbarMobileDrawer
        {...baseProps}
      />,
    )

    expect(html).toContain('theme-settings-menu-trigger-mobile')
    expect(html).toContain('Theme settings (Teal)')
  })

  it('removes unavailable select/upload commands from the drawer grid', () => {
    const html = renderToStaticMarkup(
      <ToolbarMobileDrawer
        {...baseProps}
        showSelectModeToggle={false}
        onUploadClick={undefined}
      />,
    )

    expect(html).not.toContain('data-toolbar-control="drawer-select"')
    expect(html).not.toContain('data-toolbar-control="drawer-upload"')
    expect(html).not.toContain('toolbar-control-hidden')
  })

  it('keeps moved command handlers represented in the wrapped drawer', () => {
    const html = renderToStaticMarkup(
      <ToolbarMobileDrawer
        {...baseProps}
        onUploadClick={() => {}}
        onToggleMultiSelectMode={() => {}}
      />,
    )

    expect(html).toContain('data-toolbar-control="drawer-layout-grid"')
    expect(html).toContain('data-toolbar-control="drawer-layout-masonry"')
    expect(html).toContain('data-toolbar-control="drawer-sort"')
    expect(html).toContain('data-toolbar-control="drawer-filters"')
    expect(html).toContain('data-toolbar-control="drawer-refresh"')
    expect(html).toContain('data-toolbar-control="drawer-select"')
    expect(html).toContain('data-toolbar-control="drawer-upload"')
  })
})
