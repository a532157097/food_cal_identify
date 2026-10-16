export function formatKcal(value) {
  if (value === null || value === undefined || value === '') return '--'
  const n = Number(value)
  if (Number.isNaN(n)) return '--'
  if (Math.abs(n - Math.round(n)) < 0.05) return String(Math.round(n))
  return (Math.round(n * 10) / 10).toFixed(1)
}

export function formatGram(value) {
  if (value === null || value === undefined || value === '') return '--'
  const n = Number(value)
  if (Number.isNaN(n)) return '--'
  if (Math.abs(n - Math.round(n)) < 0.05) return Math.round(n) + 'g'
  return (Math.round(n * 10) / 10).toFixed(1) + 'g'
}

export function formatConfidence(value) {
  if (value === null || value === undefined || value === '') return ''
  const n = Number(value)
  if (Number.isNaN(n)) return ''
  const percent = n <= 1 ? n * 100 : n
  return Math.round(percent) + '%'
}

export function calorieLevel(value) {
  const n = Number(value)
  if (Number.isNaN(n)) return 'ok'
  return n > 2000 ? 'over' : 'ok'
}

export function foodNames(foods) {
  const list = Array.isArray(foods) ? foods : []
  const names = list.map((item) => item && item.name).filter(Boolean)
  if (!names.length) return '未拆出分项'
  if (names.length <= 3) return names.join(' · ')
  return names.slice(0, 3).join(' · ') + ' 等'
}
