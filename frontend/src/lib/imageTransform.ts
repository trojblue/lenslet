export type Point = {
  x: number
  y: number
}

export type Size = {
  width: number
  height: number
}

export type ImageTransform = {
  base: number
  scale: number
  tx: number
  ty: number
}

export type ImageTransformClampOptions = {
  panSlack?: boolean
}

export const MIN_IMAGE_SCALE = 0.05
export const MAX_IMAGE_SCALE = 8

function isPositiveFinite(value: number): boolean {
  return Number.isFinite(value) && value > 0
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

export function clampImageScale(value: number): number {
  if (!Number.isFinite(value)) return 1
  return Number(clamp(value, MIN_IMAGE_SCALE, MAX_IMAGE_SCALE).toFixed(4))
}

export function computeImagePanSlack(containerSize: number, renderedSize: number): number {
  if (!isPositiveFinite(containerSize) || !isPositiveFinite(renderedSize)) return 0
  return Math.min(96, Math.max(48, containerSize * 0.10), renderedSize * 0.25)
}

function clampImageOffset(
  containerSize: number,
  renderedSize: number,
  offset: number,
  options?: ImageTransformClampOptions,
): number {
  if (renderedSize <= containerSize) {
    const centered = (containerSize - renderedSize) / 2
    if (!options?.panSlack) return centered
    const slack = computeImagePanSlack(containerSize, renderedSize)
    return clamp(offset, centered - slack, centered + slack)
  }

  const strictMin = containerSize - renderedSize
  const strictMax = 0
  if (!options?.panSlack) return clamp(offset, strictMin, strictMax)
  const slack = computeImagePanSlack(containerSize, renderedSize)
  return clamp(offset, strictMin - slack, strictMax + slack)
}

export function fitImageToContainer(container: Size, image: Size): ImageTransform {
  if (
    !isPositiveFinite(container.width)
    || !isPositiveFinite(container.height)
    || !isPositiveFinite(image.width)
    || !isPositiveFinite(image.height)
  ) {
    return { base: 1, scale: 1, tx: 0, ty: 0 }
  }

  const base = Math.min(1, container.width / image.width, container.height / image.height)
  const renderedWidth = image.width * base
  const renderedHeight = image.height * base
  return {
    base,
    scale: 1,
    tx: (container.width - renderedWidth) / 2,
    ty: (container.height - renderedHeight) / 2,
  }
}

export function clampImageTransform(
  container: Size,
  image: Size,
  transform: ImageTransform,
  options?: ImageTransformClampOptions,
): ImageTransform {
  const base = isPositiveFinite(transform.base) ? transform.base : 1
  const scale = clampImageScale(transform.scale)
  const renderedWidth = image.width * base * scale
  const renderedHeight = image.height * base * scale

  if (
    !isPositiveFinite(container.width)
    || !isPositiveFinite(container.height)
    || !isPositiveFinite(image.width)
    || !isPositiveFinite(image.height)
    || !isPositiveFinite(renderedWidth)
    || !isPositiveFinite(renderedHeight)
  ) {
    return { base, scale, tx: transform.tx, ty: transform.ty }
  }

  const tx = clampImageOffset(container.width, renderedWidth, transform.tx, options)
  const ty = clampImageOffset(container.height, renderedHeight, transform.ty, options)

  return { base, scale, tx, ty }
}

export function zoomImageTransformAroundPoint(params: {
  container: Size
  image: Size
  transform: ImageTransform
  point: Point
  nextScale: number
  clampOptions?: ImageTransformClampOptions
}): ImageTransform {
  const currentScale = clampImageScale(params.transform.scale)
  const nextScale = clampImageScale(params.nextScale)
  if (nextScale === currentScale) {
    return clampImageTransform(params.container, params.image, {
      ...params.transform,
      scale: currentScale,
    }, params.clampOptions)
  }

  const ratio = nextScale / currentScale
  return clampImageTransform(params.container, params.image, {
    ...params.transform,
    scale: nextScale,
    tx: params.point.x - ratio * (params.point.x - params.transform.tx),
    ty: params.point.y - ratio * (params.point.y - params.transform.ty),
  }, params.clampOptions)
}

export function panImageTransform(params: {
  container: Size
  image: Size
  transform: ImageTransform
  dx: number
  dy: number
  clampOptions?: ImageTransformClampOptions
}): ImageTransform {
  return clampImageTransform(params.container, params.image, {
    ...params.transform,
    tx: params.transform.tx + params.dx,
    ty: params.transform.ty + params.dy,
  }, params.clampOptions)
}

export function captureNormalizedImageCenter(params: {
  container: Size
  image: Size
  transform: ImageTransform
}): Point {
  const effectiveScale = params.transform.base * params.transform.scale
  if (
    !isPositiveFinite(params.container.width)
    || !isPositiveFinite(params.container.height)
    || !isPositiveFinite(params.image.width)
    || !isPositiveFinite(params.image.height)
    || !isPositiveFinite(effectiveScale)
  ) {
    return { x: 0.5, y: 0.5 }
  }

  return {
    x: clamp(
      ((params.container.width / 2) - params.transform.tx) / (params.image.width * effectiveScale),
      0,
      1,
    ),
    y: clamp(
      ((params.container.height / 2) - params.transform.ty) / (params.image.height * effectiveScale),
      0,
      1,
    ),
  }
}

export function restoreImageTransformForCenter(params: {
  container: Size
  image: Size
  center: Point
  scale: number
  clampOptions?: ImageTransformClampOptions
}): ImageTransform {
  const fit = fitImageToContainer(params.container, params.image)
  const scale = clampImageScale(params.scale)
  const tx = (params.container.width / 2) - (clamp(params.center.x, 0, 1) * params.image.width * fit.base * scale)
  const ty = (params.container.height / 2) - (clamp(params.center.y, 0, 1) * params.image.height * fit.base * scale)
  return clampImageTransform(params.container, params.image, {
    base: fit.base,
    scale,
    tx,
    ty,
  }, params.clampOptions)
}
