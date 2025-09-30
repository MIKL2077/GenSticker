export function parseRange(rangeStr) {
  if (!rangeStr || rangeStr === '0-0') return { min: 0, max: 0 }
  const match = String(rangeStr).match(/(\d+)-(\d+)/)
  if (!match) return { min: 0, max: 0 }
  const [, min, max] = match.map(Number)
  return { min, max }
}

export function isWithinRange(count, rangeStr) {
  const { min, max } = parseRange(rangeStr)
  if (max === 0 && min === 0) return true
  return count >= min && count <= max
} 