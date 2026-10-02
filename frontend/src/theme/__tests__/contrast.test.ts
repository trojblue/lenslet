import { describe, expect, it } from 'vitest'
import { THEME_PRESETS } from '../runtime'

type Rgb = [number, number, number]

function resolveRgb(value: string, tokens: Record<string, string>): Rgb {
  if (value.startsWith('var(')) return resolveRgb(tokens[value.slice(4, -1)], tokens)
  return [1, 3, 5].map((offset) => parseInt(value.slice(offset, offset + 2), 16)) as Rgb
}

function composite(wash: string, background: Rgb): Rgb {
  const [r, g, b, alpha] = wash.match(/[\d.]+/g)!.map(Number)
  return [r, g, b].map((channel, index) => channel * alpha + background[index] * (1 - alpha)) as Rgb
}

function luminance(rgb: Rgb): number {
  const channels = rgb.map((value) => {
    const channel = value / 255
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
  })
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722
}

function contrast(first: Rgb, second: Rgb): number {
  const a = luminance(first)
  const b = luminance(second)
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
}

describe('theme text contrast', () => {
  for (const preset of Object.values(THEME_PRESETS)) {
    it(`${preset.label} keeps control and quiet text legible on resting and selected surfaces`, () => {
      const tokens = preset.tokens
      for (const surface of ['--panel', '--surface']) {
        const background = resolveRgb(tokens[surface], tokens)
        const selected = composite(tokens['--accent-muted'], background)
        for (const role of ['--text', '--text-secondary', '--muted', '--accent-text']) {
          const foreground = resolveRgb(tokens[role], tokens)
          for (const target of [background, selected]) {
            expect(contrast(foreground, target), `${role} on ${surface}`).toBeGreaterThanOrEqual(4.5)
          }
        }
      }
    })
  }
})
