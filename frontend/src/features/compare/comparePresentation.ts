export type CompareResource = {
  identity: string
  kind: 'full' | 'thumbnail'
  path: string
  url: string
}

export function compareResource(
  path: string | null,
  url: string | null,
  kind: CompareResource['kind'],
): CompareResource | null {
  if (!path || !url) return null
  return {
    identity: `${kind}\u0000${path}\u0000${url}`,
    kind,
    path,
    url,
  }
}

export function selectDecodedCompareResource(
  full: CompareResource | null,
  thumbnail: CompareResource | null,
  decodedIdentities: ReadonlySet<string>,
): CompareResource | null {
  if (full && decodedIdentities.has(full.identity)) return full
  if (thumbnail && decodedIdentities.has(thumbnail.identity)) return thumbnail
  return null
}

export function retainCurrentDecodedResourceIdentities(
  resources: readonly (CompareResource | null)[],
  decodedIdentities: ReadonlySet<string>,
): Set<string> {
  const retained = new Set<string>()
  for (const resource of resources) {
    if (resource && decodedIdentities.has(resource.identity)) {
      retained.add(resource.identity)
    }
  }
  return retained
}

export function comparePairCanCommit(
  aResource: CompareResource | null,
  bResource: CompareResource | null,
  aTerminal: boolean,
  bTerminal: boolean,
): boolean {
  return Boolean((aResource || aTerminal) && (bResource || bTerminal))
}
