import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import Dropdown, { DropdownMenu, getDropdownPanelClassName } from '../Dropdown'

describe('Dropdown shared panel styling', () => {
  it('includes the Lenslet scrollbar class for searchable and menu panels', () => {
    expect(getDropdownPanelClassName('metric-panel', true).split(/\s+/)).toEqual(
      expect.arrayContaining([
        'dropdown-panel',
        'scrollbar-thin',
        'dropdown-panel-searchable',
        'metric-panel',
      ]),
    )
    expect(getDropdownPanelClassName('menu-panel').split(/\s+/)).toEqual(
      expect.arrayContaining(['dropdown-panel', 'scrollbar-thin', 'menu-panel']),
    )
  })

  it('renders the menu panel through the shared styled path', () => {
    const html = renderToStaticMarkup(
      <DropdownMenu trigger={<button>Open</button>} open panelClassName="custom-panel">
        <button>Item</button>
      </DropdownMenu>,
    )

    expect(html).toContain('dropdown-panel scrollbar-thin')
    expect(html).toContain('custom-panel')
  })

  it('renders one editable app-owned combobox for freeform values', () => {
    const html = renderToStaticMarkup(
      <Dropdown
        value="custom"
        onChange={() => {}}
        options={[{ value: 'known', label: 'Known' }]}
        editable
        aria-label="Categorical value"
      />,
    )

    expect(html).toContain('role="combobox"')
    expect(html).toContain('value="custom"')
    expect(html).not.toContain('<select')
  })
})
