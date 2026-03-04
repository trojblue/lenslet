import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ToolbarMobileDrawer from '../ToolbarMobileDrawer'

vi.mock('../../Dropdown', () => ({
  default: () => <div data-dropdown-mock="1" />,
}))

describe('ToolbarMobileDrawer theme mount', () => {
  it('renders shared ThemeSettingsMenu trigger in mobile drawer row', () => {
    const html = renderToStaticMarkup(
      <ToolbarMobileDrawer
        viewMode="grid"
        currentSort="builtin:added"
        sortOnlyOptions={[{ label: 'Sort by', options: [{ value: 'builtin:added', label: 'Date added' }] }]}
        sortDisabled={false}
        sortControlsDisabled={false}
        sortDir="desc"
        isRandom={false}
        showSelectModeToggle
        multiSelectMode={false}
        selectModeLabel="Select"
        uploadBusy={false}
        uploadDisabled={false}
        themePreset="teal"
        autoloadImageMetadata={false}
        onToggleSortDir={() => {}}
        onThemePresetChange={() => {}}
        onAutoloadImageMetadataChange={() => {}}
      />,
    )

    expect(html).toContain('theme-settings-menu-trigger-mobile')
    expect(html).toContain('Theme settings (Teal)')
  })

  it('keeps select/upload pill slots mounted when actions are unavailable', () => {
    const html = renderToStaticMarkup(
      <ToolbarMobileDrawer
        viewMode="grid"
        currentSort="builtin:added"
        sortOnlyOptions={[{ label: 'Sort by', options: [{ value: 'builtin:added', label: 'Date added' }] }]}
        sortDisabled={false}
        sortControlsDisabled={false}
        sortDir="desc"
        isRandom={false}
        showSelectModeToggle={false}
        multiSelectMode={false}
        selectModeLabel="Select"
        uploadBusy={false}
        uploadDisabled={false}
        themePreset="teal"
        autoloadImageMetadata={false}
        onToggleSortDir={() => {}}
        onThemePresetChange={() => {}}
        onAutoloadImageMetadataChange={() => {}}
      />,
    )

    expect(html).toContain('mobile-pill-slot-select')
    expect(html).toContain('mobile-pill-slot-upload')
    expect(html).toMatch(/mobile-pill-select[^"]*toolbar-control-hidden/)
    expect(html).toMatch(/mobile-pill-upload[^"]*toolbar-control-hidden/)
    expect(html).toContain('disabled=""')
  })
})
