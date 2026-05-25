import { describe, expect, it } from 'vitest'
import {
  captureNormalizedImageCenter,
  clampImageScale,
  clampImageTransform,
  computeImagePanSlack,
  fitImageToContainer,
  panImageTransform,
  restoreImageTransformForCenter,
  zoomImageTransformAroundPoint,
} from '../imageTransform'

describe('image transform math', () => {
  it('fits wide, tall, and square images inside the container without upscaling', () => {
    expect(fitImageToContainer({ width: 800, height: 600 }, { width: 1600, height: 400 })).toMatchObject({
      base: 0.5,
      tx: 0,
      ty: 200,
    })
    expect(fitImageToContainer({ width: 800, height: 600 }, { width: 200, height: 1200 })).toMatchObject({
      base: 0.5,
      tx: 350,
      ty: 0,
    })
    expect(fitImageToContainer({ width: 800, height: 600 }, { width: 300, height: 300 })).toMatchObject({
      base: 1,
      tx: 250,
      ty: 150,
    })
  })

  it('clamps scale and offsets so the rendered image cannot leave blank space while zoomed', () => {
    expect(clampImageScale(100)).toBe(8)
    expect(clampImageScale(0.001)).toBe(0.05)

    const transform = clampImageTransform(
      { width: 500, height: 400 },
      { width: 1000, height: 800 },
      { base: 1, scale: 1, tx: 120, ty: -900 },
    )

    expect(transform.tx).toBe(0)
    expect(transform.ty).toBe(-400)
  })

  it('keeps strict clamping as the default for centered and zoomed images', () => {
    expect(clampImageTransform(
      { width: 500, height: 400 },
      { width: 100, height: 100 },
      { base: 1, scale: 1, tx: 260, ty: 10 },
    )).toMatchObject({ tx: 200, ty: 150 })

    expect(panImageTransform({
      container: { width: 500, height: 400 },
      image: { width: 1000, height: 800 },
      transform: { base: 1, scale: 1, tx: 0, ty: 0 },
      dx: 160,
      dy: -900,
    })).toMatchObject({ tx: 0, ty: -400 })
  })

  it('allows bounded slack when the rendered image matches the container', () => {
    const next = clampImageTransform(
      { width: 500, height: 400 },
      { width: 500, height: 400 },
      { base: 1, scale: 1, tx: 120, ty: -120 },
      { panSlack: true },
    )

    expect(computeImagePanSlack(500, 500)).toBe(50)
    expect(next.tx).toBe(50)
    expect(next.ty).toBe(-48)
  })

  it('allows bounded slack when the rendered image is smaller than the container', () => {
    const next = clampImageTransform(
      { width: 500, height: 400 },
      { width: 100, height: 100 },
      { base: 1, scale: 1, tx: 260, ty: 110 },
      { panSlack: true },
    )

    expect(computeImagePanSlack(500, 100)).toBe(25)
    expect(next.tx).toBe(225)
    expect(next.ty).toBe(125)
  })

  it('allows bounded slack beyond strict zoomed-image edges', () => {
    const right = clampImageTransform(
      { width: 500, height: 400 },
      { width: 1000, height: 800 },
      { base: 1, scale: 1, tx: 90, ty: 80 },
      { panSlack: true },
    )
    const left = clampImageTransform(
      { width: 500, height: 400 },
      { width: 1000, height: 800 },
      { base: 1, scale: 1, tx: -590, ty: -480 },
      { panSlack: true },
    )

    expect(computeImagePanSlack(500, 1000)).toBe(50)
    expect(right.tx).toBe(50)
    expect(right.ty).toBe(48)
    expect(left.tx).toBe(-550)
    expect(left.ty).toBe(-448)
  })

  it('zooms around the pointer while preserving the pointed image pixel', () => {
    const current = { base: 0.5, scale: 1, tx: 0, ty: 100 }
    const next = zoomImageTransformAroundPoint({
      container: { width: 800, height: 600 },
      image: { width: 1600, height: 800 },
      transform: current,
      point: { x: 300, y: 250 },
      nextScale: 2,
    })

    expect(next.scale).toBe(2)
    expect((300 - next.tx) / (current.base * next.scale)).toBeCloseTo(
      (300 - current.tx) / (current.base * current.scale),
    )
    expect((250 - next.ty) / (current.base * next.scale)).toBeCloseTo(
      (250 - current.ty) / (current.base * current.scale),
    )
  })

  it('captures and restores normalized center across container resize', () => {
    const image = { width: 1600, height: 900 }
    const beforeContainer = { width: 1000, height: 700 }
    const before = {
      ...fitImageToContainer(beforeContainer, image),
      scale: 2,
      tx: -300,
      ty: -120,
    }
    const center = captureNormalizedImageCenter({
      container: beforeContainer,
      image,
      transform: before,
    })
    const after = restoreImageTransformForCenter({
      container: { width: 640, height: 420 },
      image,
      center,
      scale: before.scale,
    })
    const restoredCenter = captureNormalizedImageCenter({
      container: { width: 640, height: 420 },
      image,
      transform: after,
    })

    expect(restoredCenter.x).toBeCloseTo(center.x, 4)
    expect(restoredCenter.y).toBeCloseTo(center.y, 4)
  })

  it('preserves compared-image centers independently when aspect ratios differ', () => {
    const container = { width: 900, height: 600 }
    const nextContainer = { width: 520, height: 360 }
    const wideImage = { width: 1800, height: 600 }
    const tallImage = { width: 500, height: 1400 }
    const wide = { ...fitImageToContainer(container, wideImage), scale: 2, tx: -260, ty: 0 }
    const tall = { ...fitImageToContainer(container, tallImage), scale: 2, tx: 180, ty: -460 }
    const wideCenter = captureNormalizedImageCenter({ container, image: wideImage, transform: wide })
    const tallCenter = captureNormalizedImageCenter({ container, image: tallImage, transform: tall })

    const nextWide = restoreImageTransformForCenter({
      container: nextContainer,
      image: wideImage,
      center: wideCenter,
      scale: 2,
    })
    const nextTall = restoreImageTransformForCenter({
      container: nextContainer,
      image: tallImage,
      center: tallCenter,
      scale: 2,
    })

    expect(captureNormalizedImageCenter({
      container: nextContainer,
      image: wideImage,
      transform: nextWide,
    }).x).toBeCloseTo(wideCenter.x, 4)
    expect(captureNormalizedImageCenter({
      container: nextContainer,
      image: tallImage,
      transform: nextTall,
    }).y).toBeCloseTo(tallCenter.y, 4)
  })
})
