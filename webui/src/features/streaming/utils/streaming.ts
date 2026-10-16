export const getStreamingErrorMessage = (error: unknown): string => {
  if (error instanceof DOMException) {
    if (error.name === 'NotAllowedError')
      return 'Camera permission was denied. Allow access in your browser and try again.'
    if (error.name === 'NotFoundError')
      return 'No camera was found on this device.'
    if (error.name === 'NotReadableError')
      return 'The camera is unavailable. Close other apps using it and try again.'
    if (error.name === 'OverconstrainedError')
      return 'This camera cannot provide the requested video settings.'
  }
  return error instanceof Error
    ? error.message
    : 'Something interrupted streaming. Please try again.'
}

export const normalizeStreamingError = (cause: unknown): Error => {
  if (cause instanceof Error) return cause
  const message = getStreamingErrorMessage(cause)
  return new Error(message)
}
