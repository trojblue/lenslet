import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import BootShell from '../BootShell'

describe('BootShell', () => {
  it('keeps the stable shell without early loading copy', () => {
    const html = renderToStaticMarkup(<BootShell showLoadingCopy={false} />)
    expect(html).toContain('data-boot-shell="true"')
    expect(html).toContain('data-loading-copy-visible="false"')
    expect(html).not.toContain('Loading Lenslet...')
  })

  it('adds loading copy without changing shell ownership', () => {
    const html = renderToStaticMarkup(<BootShell showLoadingCopy />)
    expect(html).toContain('data-boot-shell="true"')
    expect(html).toContain('data-loading-copy-visible="true"')
    expect(html).toContain('Loading Lenslet...')
  })
})
