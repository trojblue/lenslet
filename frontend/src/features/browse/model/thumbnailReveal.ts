export async function decodeThumbnailBeforeReveal(
  image: Pick<HTMLImageElement, 'decode'>,
): Promise<void> {
  await image.decode()
}
