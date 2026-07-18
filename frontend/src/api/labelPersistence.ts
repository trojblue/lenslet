import type {
  AcceptedEventIdentity,
  LabelPersistenceState,
  SidecarMutationResponse,
} from '../lib/types'

export type LabelPersistenceSnapshot = {
  state: 'saved' | 'saving' | 'failed'
  pendingCount: number
  bootEpoch: string | null
  error: string | null
}

type PendingAcceptedEvent = {
  identity: AcceptedEventIdentity
  path: string
}

export type LabelPersistenceRepair = {
  path: string
  token: number
}

export type LabelPersistenceStatusSource = 'sync' | 'health' | 'event'

function identityKey(identity: AcceptedEventIdentity): string {
  return `${identity.boot_epoch}:${identity.event_id}`
}

const refreshListeners = new Set<() => void>()

export function requestLabelPersistenceRefresh(): void {
  for (const listener of refreshListeners) listener()
}

export function subscribeLabelPersistenceRefresh(listener: () => void): () => void {
  refreshListeners.add(listener)
  return () => refreshListeners.delete(listener)
}

export class LabelPersistenceTracker {
  private readonly pending = new Map<string, PendingAcceptedEvent>()
  private readonly uncertain = new Map<string, string>()
  private readonly repairs = new Map<string, number>()
  private readonly retiredEpochs = new Set<string>()
  private readonly listeners = new Set<(snapshot: LabelPersistenceSnapshot) => void>()
  private bootEpoch: string | null = null
  private durableEventId = 0
  private error: string | null = null
  private repairSequence = 0

  observeMutation(path: string, response: SidecarMutationResponse): void {
    const accepted = response.accepted_event
    if (!accepted) {
      const responseEpoch = response.durable_watermark.boot_epoch
      if (this.bootEpoch === null) this.bootEpoch = responseEpoch
      if (responseEpoch !== this.bootEpoch) {
        this.addRepair(path)
      } else if (response.persistence === 'pending') {
        this.uncertain.set(path, responseEpoch)
      } else {
        this.uncertain.delete(path)
      }
      this.notify()
      return
    }
    this.observeAccepted(path, accepted, response.persistence, response.durable_watermark)
  }

  observeAccepted(
    path: string,
    accepted: AcceptedEventIdentity,
    _persistence: 'pending' | 'saved',
    watermark: AcceptedEventIdentity,
  ): void {
    if (this.bootEpoch === null) this.bootEpoch = accepted.boot_epoch
    if (accepted.boot_epoch !== this.bootEpoch || this.retiredEpochs.has(accepted.boot_epoch)) {
      this.addRepair(path)
      requestLabelPersistenceRefresh()
      this.notify()
      return
    }
    if (watermark.boot_epoch === this.bootEpoch) {
      this.durableEventId = Math.max(this.durableEventId, watermark.event_id)
    }
    const alreadyDurable = (
      accepted.event_id <= this.durableEventId
      || (
        watermark.boot_epoch === accepted.boot_epoch
        && accepted.event_id <= watermark.event_id
      )
    )
    if (!alreadyDurable) {
      this.pending.set(identityKey(accepted), { identity: accepted, path })
    }
    this.notify()
  }

  observeStatus(
    status: LabelPersistenceState,
    source: LabelPersistenceStatusSource = 'sync',
  ): LabelPersistenceRepair[] {
    if (
      this.bootEpoch !== null
      && this.bootEpoch !== status.boot_epoch
      && (source !== 'sync' || this.retiredEpochs.has(status.boot_epoch))
    ) {
      requestLabelPersistenceRefresh()
      return Array.from(this.repairs, ([path, token]) => ({ path, token }))
    }
    if (this.error !== null && status.state !== 'failed' && source !== 'sync') {
      requestLabelPersistenceRefresh()
      return Array.from(this.repairs, ([path, token]) => ({ path, token }))
    }
    if (this.bootEpoch !== null && this.bootEpoch !== status.boot_epoch) {
      this.retireEpoch(this.bootEpoch)
      for (const pending of this.pending.values()) this.addRepair(pending.path)
      for (const path of this.uncertain.keys()) this.addRepair(path)
      this.pending.clear()
      this.uncertain.clear()
      this.durableEventId = 0
    }
    this.bootEpoch = status.boot_epoch
    this.durableEventId = Math.max(this.durableEventId, status.durable_watermark.event_id)
    for (const [key, pending] of this.pending) {
      if (pending.identity.boot_epoch !== status.boot_epoch) {
        this.addRepair(pending.path)
        this.pending.delete(key)
        continue
      }
      if (pending.identity.event_id <= status.durable_watermark.event_id) {
        this.pending.delete(key)
      }
    }
    for (const [path, bootEpoch] of this.uncertain) {
      if (bootEpoch !== status.boot_epoch) {
        this.addRepair(path)
        this.uncertain.delete(path)
      } else if (status.state === 'saved' && status.pending_count === 0) {
        this.uncertain.delete(path)
      }
    }
    this.error = status.state === 'failed'
      ? status.error || 'Label storage is unavailable. Retry after storage recovers.'
      : null
    if (status.state === 'failed' && source !== 'sync') {
      requestLabelPersistenceRefresh()
    }
    this.notify()
    return Array.from(this.repairs, ([path, token]) => ({ path, token }))
  }

  acknowledgeRepairs(repairs: readonly LabelPersistenceRepair[]): void {
    let changed = false
    for (const repair of repairs) {
      if (this.repairs.get(repair.path) !== repair.token) continue
      changed = this.repairs.delete(repair.path) || changed
    }
    if (changed) this.notify()
  }

  snapshot(): LabelPersistenceSnapshot {
    return {
      state: this.error
        ? 'failed'
        : this.pending.size > 0 || this.uncertain.size > 0 || this.repairs.size > 0
          ? 'saving'
          : 'saved',
      pendingCount: this.pending.size + this.uncertain.size + this.repairs.size,
      bootEpoch: this.bootEpoch,
      error: this.error,
    }
  }

  subscribe(listener: (snapshot: LabelPersistenceSnapshot) => void): () => void {
    this.listeners.add(listener)
    listener(this.snapshot())
    return () => this.listeners.delete(listener)
  }

  reset(): void {
    this.pending.clear()
    this.uncertain.clear()
    this.repairs.clear()
    this.bootEpoch = null
    this.durableEventId = 0
    this.error = null
    this.repairSequence = 0
    this.retiredEpochs.clear()
    this.notify()
  }

  private addRepair(path: string): void {
    this.repairSequence += 1
    this.repairs.set(path, this.repairSequence)
  }

  private retireEpoch(bootEpoch: string): void {
    this.retiredEpochs.add(bootEpoch)
    while (this.retiredEpochs.size > 8) {
      const oldest = this.retiredEpochs.values().next().value as string | undefined
      if (oldest === undefined) break
      this.retiredEpochs.delete(oldest)
    }
  }

  private notify(): void {
    const snapshot = this.snapshot()
    for (const listener of this.listeners) listener(snapshot)
  }
}

export const labelPersistenceTracker = new LabelPersistenceTracker()
