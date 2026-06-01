import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ThemeSettingsMenu, {
  getThemeMenuPanelPosition,
  reduceThemeSettingsMenuOpenState,
  resolveThemeMenuSelection,
} from '../ThemeSettingsMenu'

describe('ThemeSettingsMenu open-state model', () => {
  it('toggles open state from trigger intent', () => {
    const opened = reduceThemeSettingsMenuOpenState(false, 'toggle')
    const closed = reduceThemeSettingsMenuOpenState(opened, 'toggle')

    expect(opened).toBe(true)
    expect(closed).toBe(false)
  })

  it('closes menu on close intents', () => {
    expect(reduceThemeSettingsMenuOpenState(true, 'escape')).toBe(false)
    expect(reduceThemeSettingsMenuOpenState(true, 'outside_click')).toBe(false)
    expect(reduceThemeSettingsMenuOpenState(true, 'select')).toBe(false)
    expect(reduceThemeSettingsMenuOpenState(true, 'close')).toBe(false)
  })
})

describe('ThemeSettingsMenu selection model', () => {
  it('normalizes unknown selection to default', () => {
    expect(resolveThemeMenuSelection('teal')).toBe('teal')
    expect(resolveThemeMenuSelection('not-a-theme')).toBe('default')
  })
})

describe('ThemeSettingsMenu panel positioning', () => {
  it('clamps mobile panel into viewport above trigger', () => {
    const pos = getThemeMenuPanelPosition({
      placement: 'mobile',
      anchorRect: { left: 380, right: 420, top: 790, bottom: 830 },
      panelSize: { width: 200, height: 260 },
      viewport: { left: 0, top: 0, width: 390, height: 844, right: 390, bottom: 844 },
    })

    expect(pos.x).toBe(182)
    expect(pos.y).toBe(522)
  })

  it('positions sidebar panel to the right with vertical clamp', () => {
    const pos = getThemeMenuPanelPosition({
      placement: 'sidebar',
      anchorRect: { left: 12, right: 50, top: 730, bottom: 760 },
      panelSize: { width: 120, height: 300 },
      viewport: { left: 0, top: 0, width: 390, height: 800, right: 390, bottom: 800 },
    })

    expect(pos.x).toBe(60)
    expect(pos.y).toBe(460)
  })

  it('keeps the panel inside an offset visual viewport', () => {
    const pos = getThemeMenuPanelPosition({
      placement: 'sidebar',
      anchorRect: { left: 8, right: 42, top: 318, bottom: 348 },
      panelSize: { width: 160, height: 180 },
      viewport: { left: 32, top: 96, width: 300, height: 260, right: 332, bottom: 356 },
    })

    expect(pos.x).toBe(52)
    expect(pos.y).toBe(168)
  })
})

describe('ThemeSettingsMenu mounts', () => {
  const noop = () => {}

  it('renders sidebar trigger variant', () => {
    const html = renderToStaticMarkup(
      <ThemeSettingsMenu value="default" onChange={noop} placement="sidebar" />,
    )

    expect(html).toContain('theme-settings-menu-trigger-sidebar')
    expect(html).toContain('Theme settings (Original)')
  })

  it('renders mobile trigger variant', () => {
    const html = renderToStaticMarkup(
      <ThemeSettingsMenu value="charcoal" onChange={noop} placement="mobile" />,
    )

    expect(html).toContain('theme-settings-menu-trigger-mobile')
    expect(html).toContain('Theme settings (Charcoal)')
  })
})
