import { useEffect, useState } from 'react'
import { getPollingStatus, subscribePollingStatus } from './client'

export function usePollingEnabled(): boolean {
  const [enabled, setEnabled] = useState(getPollingStatus())

  useEffect(() => {
    return subscribePollingStatus(setEnabled)
  }, [])

  return enabled
}
