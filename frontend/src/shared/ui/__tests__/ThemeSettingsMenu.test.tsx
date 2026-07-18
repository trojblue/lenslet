import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { TableLaunchStatusPayload } from '../../../lib/types'
import ThemeSettingsMenu, {
  LaunchSessionMenuSection,
  copyLaunchCommandToClipboard,
  formatSourceRefresh,
  getThemeMenuPanelMaxHeight,
  getThemeMenuPanelPosition,
  reduceThemeSettingsMenuOpenState,
  resolveSourceColumnMenuState,
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

  it('resolves source column selector state from table source options', () => {
    const state = resolveSourceColumnMenuState({
      enabled: true,
      current: 'image_url',
      columns: [
        {
          name: 'image_url',
          selected: true,
          sample_total: 100,
          sample_loadable: 0,
          sample_usable: 0,
        },
        {
          name: 'candidate',
          selected: false,
          sample_total: 100,
          sample_loadable: 100,
          sample_usable: 100,
        },
      ],
      warning: 'The selected source column produced no loadable gallery entries.',
    })

    expect(state.enabled).toBe(true)
    expect(state.selectedSourceColumn).toBe('image_url')
    expect(state.selectedSourceStatus?.sample_usable).toBe(0)
  })

  it('formats current and restart-required table source state', () => {
    const base: TableLaunchStatusPayload = {
      path_mode: 'explicit',
      root_policy: 'none',
      source_table_rows: 1,
      gallery_rows: 1,
      skipped_rows: { total: 0 },
      media_source_kind: 'http',
      dimension_coverage: { known: 0, missing: 1, total: 1 },
      dimension_cache_policy: 'none',
      dimension_write_policy: 'none',
      original_media_policy: {
        mode: 'backend_proxy_required',
        source_kind: 'http',
        proxy_available: true,
      },
      warnings: [],
    }

    expect(formatSourceRefresh({
      ...base,
      source_refresh: { state: 'current', generation: 'generation-a' },
    })).toBe('Source snapshot: current')
    expect(formatSourceRefresh({
      ...base,
      source_refresh: {
        state: 'restart-required',
        generation: 'generation-a',
        message: 'The source table changed; restart Lenslet to load the new snapshot.',
      },
    })).toBe('The source table changed; restart Lenslet to load the new snapshot.')
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

  it('pins an oversized async panel to every viewport edge', () => {
    const pos = getThemeMenuPanelPosition({
      placement: 'mobile',
      anchorRect: { left: 380, right: 420, top: 790, bottom: 830 },
      panelSize: { width: 500, height: 900 },
      viewport: { left: 0, top: 0, width: 390, height: 844, right: 390, bottom: 844 },
    })

    expect(pos).toEqual({ x: 8, y: 8 })
  })

  it('caps async growth at the trigger-anchored bottom edge', () => {
    const viewport = { left: 0, top: 0, width: 1440, height: 920, right: 1440, bottom: 920 }

    expect(getThemeMenuPanelMaxHeight(
      'sidebar',
      { left: 8, right: 48, top: 868, bottom: 908 },
      viewport,
    )).toBe(900)
    expect(getThemeMenuPanelMaxHeight(
      'mobile',
      { left: 12, right: 120, top: 820, bottom: 864 },
      viewport,
    )).toBe(804)
  })
})

describe('ThemeSettingsMenu mounts', () => {
  const noop = () => {}

  it('renders sidebar trigger variant', () => {
    const html = renderToStaticMarkup(
      <ThemeSettingsMenu value="default" onChange={noop} placement="sidebar" />,
    )

    expect(html).toContain('theme-settings-menu-trigger-sidebar')
    expect(html).toContain('Settings (Original)')
  })

  it('renders mobile trigger variant', () => {
    const html = renderToStaticMarkup(
      <ThemeSettingsMenu value="charcoal" onChange={noop} placement="mobile" />,
    )

    expect(html).toContain('theme-settings-menu-trigger-mobile')
    expect(html).toContain('Settings (Charcoal)')
    expect(html).toContain('>Settings</span>')
  })
})

describe('LaunchSessionMenuSection', () => {
  it('renders remote HF launch provenance with copy command', () => {
    const html = renderToStaticMarkup(
      <LaunchSessionMenuSection
        launchSession={{
          kind: 'hf_dataset',
          loaded_from_label: 'Hugging Face dataset',
          target_label: 'incantor/aes-composite-x0.2-additional-images',
          title_label: 'incantor/aes-composite-x0.2-additional-images',
          detail_label: 'Remote table · read-only',
          copy_command: 'lenslet incantor/aes-composite-x0.2-additional-images',
        }}
      />,
    )

    expect(html).toContain('Session')
    expect(html).toContain('Loaded from')
    expect(html).toContain('Hugging Face dataset')
    expect(html).toContain('incantor/aes-composite-x0.2-additional-images')
    expect(html).toContain('Remote table · read-only')
    expect(html).toContain('Copy command')
  })

  it('omits copy command when backend marks the session unsafe to copy', () => {
    const html = renderToStaticMarkup(
      <LaunchSessionMenuSection
        launchSession={{
          kind: 'local_parquet',
          loaded_from_label: 'Local Parquet',
          target_label: '.../items.parquet',
          title_label: 'items.parquet',
          detail_label: 'Table · writable sidecar',
          copy_command: null,
        }}
      />,
    )

    expect(html).toContain('Local Parquet')
    expect(html).toContain('.../items.parquet')
    expect(html).not.toContain('Copy command')
  })

  it('returns false instead of throwing when clipboard copy fails', async () => {
    const clipboard = {
      writeText: vi.fn(async () => {
        throw new Error('denied')
      }),
    }

    await expect(copyLaunchCommandToClipboard('lenslet owner/repo', clipboard)).resolves.toBe(false)
    expect(clipboard.writeText).toHaveBeenCalledWith('lenslet owner/repo')
  })
})
