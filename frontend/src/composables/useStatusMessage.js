import { ref } from 'vue'

export function useStatusMessage() {
  const statusMessage = ref('')
  const showStatus = ref(false)

  const showStatusMessage = (message) => {
    statusMessage.value = message
    showStatus.value = true
    setTimeout(() => {
      showStatus.value = false
      setTimeout(() => {
        statusMessage.value = ''
      }, 300)
    }, 3000)
  }

  return { statusMessage, showStatus, showStatusMessage }
} 