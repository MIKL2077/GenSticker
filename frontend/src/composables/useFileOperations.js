import { useMemeGeneration } from '@/composables/useMemeGeneration'

export function useFileOperations(showStatusMessage) {
  const { saveMeme, shareMeme } = useMemeGeneration(showStatusMessage)
  return { saveMeme, shareMeme }
} 