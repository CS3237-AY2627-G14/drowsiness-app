import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'

export const useCameraDevices = (hasPreview: boolean) => {
  const devices = navigator.mediaDevices
  const canEnumerate =
    window.isSecureContext &&
    typeof navigator.mediaDevices !== 'undefined' &&
    typeof devices.enumerateDevices === 'function'
  const query = useQuery({
    // Opening a preview grants permission and can reveal more devices.
    queryKey: ['cameraDevices', hasPreview],
    queryFn: async () => {
      const availableDevices = await devices.enumerateDevices()
      return availableDevices.filter(
        (device) => device.kind === 'videoinput' && device.deviceId !== '',
      )
    },
    enabled: canEnumerate,
    retry: false,
  })
  const { refetch } = query

  useEffect(() => {
    if (!canEnumerate) return
    const refresh = () => {
      void refetch()
    }
    devices.addEventListener('devicechange', refresh)
    return () => devices.removeEventListener('devicechange', refresh)
  }, [canEnumerate, devices, refetch])

  return { ...query, canEnumerate }
}
