import { onShareAppMessage } from '@dcloudio/uni-app'
import { shareCard } from '@/services/shareCard'

export function useShareCard() {
  onShareAppMessage(()=>shareCard())
}
