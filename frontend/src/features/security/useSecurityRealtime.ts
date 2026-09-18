import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { connectSecurityRealtime, type SecurityRealtimeState } from '@/api/securityRealtime'
import { useCurrentUser } from '@/context/AuthContext'
import { qk } from '@/lib/queryKeys'

export function useSecurityRealtime(): SecurityRealtimeState {
  const user = useCurrentUser()
  const queryClient = useQueryClient()
  const eligible = user.role === 'super_admin' || user.role === 'security_officer'
  const [state, setState] = useState<SecurityRealtimeState>(eligible ? 'connecting' : 'idle')

  useEffect(() => {
    if (!eligible) {
      setState('idle')
      return
    }
    return connectSecurityRealtime({
      onStateChange: setState,
      onMessage: (message) => {
        if (message.type === 'security.connection.ready') return
        void queryClient.invalidateQueries({ queryKey: qk.alerts.all })
        void queryClient.invalidateQueries({ queryKey: qk.cameraEvents.all })
        void queryClient.invalidateQueries({ queryKey: qk.notifications.all })
        void queryClient.invalidateQueries({ queryKey: qk.stats.security })
      },
    })
  }, [eligible, queryClient])

  return state
}
