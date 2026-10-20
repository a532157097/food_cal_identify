<template>
  <view class="page">
    <view class="status" :style="{ height: statusBarHeight + 'px' }"></view>
    <view class="hero">
      <view class="month-row">
        <text class="switch" :class="{ disabled: !canPrev }" @tap="shift(-1)">上个月</text>
        <text class="brand">{{ title }}</text>
        <text class="switch" :class="{ disabled: !canNext }" @tap="shift(1)">下个月</text>
      </view>
      <text class="tagline">超过 2000 千卡为红色。最多回看一年</text>
    </view>

    <view v-if="errorText" class="banner">{{ errorText }}</view>

    <view class="calendar">
      <view class="week">
        <text v-for="label in weekLabels" :key="label" class="week-label">{{ label }}</text>
      </view>
      <view class="grid">
        <view v-for="(cell, index) in cells" :key="index" class="cell-wrap">
          <view v-if="cell" class="cell" hover-class="pressed" @tap="open(cell)">
            <text class="kcal" :class="levelOf(cell.total_calories_kcal)">{{ kcalText(cell.total_calories_kcal) }}</text>
            <text class="day">{{ cell.day }}</text>
          </view>
        </view>
      </view>
    </view>

    <view class="nav-spacer"></view>
    <bottom-nav current="month"></bottom-nav>
  </view>
</template>

<script>
import BottomNav from '../../components/bottom-nav.vue'
import { ensureLogin, request } from '../../utils/api.js'
import { calorieLevel, formatKcal } from '../../utils/format.js'

export default {
  components: { BottomNav },
  data() {
    return {
      statusBarHeight: 20,
      month: '',
      cells: [],
      errorText: '',
      weekLabels: ['一', '二', '三', '四', '五', '六', '日'],
    }
  },
  computed: {
    title() {
      return monthTitle(this.month)
    },
    canPrev() {
      return withinYear(addMonths(this.month, -1))
    },
    canNext() {
      return withinYear(addMonths(this.month, 1))
    },
  },
  onLoad() {
    const info = uni.getSystemInfoSync()
    this.statusBarHeight = info.statusBarHeight || 0
    this.month = currentMonth()
  },
  onShow() {
    if (!ensureLogin()) return
    if (!this.month) this.month = currentMonth()
    this.load()
  },
  methods: {
    shift(step) {
      const next = addMonths(this.month, step)
      if (!withinYear(next)) return
      this.month = next
      this.load()
    },
    load() {
      this.errorText = ''
      return request('/api/calendar?month=' + this.month)
        .then((body) => {
          this.cells = buildCells(body && body.days)
        })
        .catch((err) => {
          if (err && err.statusCode === 401) {
            ensureLogin()
            return
          }
          this.errorText = (err && err.message) || '本月热量加载失败'
        })
    },
    levelOf(value) {
      return calorieLevel(value)
    },
    kcalText(value) {
      return formatKcal(value)
    },
    open(cell) {
      uni.navigateTo({ url: '/pages/day/day?date=' + cell.date })
    },
  },
}

function buildCells(days) {
  const list = Array.isArray(days) ? days : []
  if (!list.length) return []
  const first = list[0].date.split('-')
  const weekday = new Date(Number(first[0]), Number(first[1]) - 1, 1).getDay()
  const padCount = weekday === 0 ? 6 : weekday - 1
  const cells = []
  for (let i = 0; i < padCount; i += 1) cells.push(null)
  list.forEach((item) => {
    cells.push({
      date: item.date,
      day: Number(item.date.slice(8)),
      total_calories_kcal: item.total_calories_kcal || 0,
    })
  })
  return cells
}

function currentMonth() {
  const now = new Date()
  return now.getFullYear() + '-' + pad(now.getMonth() + 1)
}

function addMonths(month, step) {
  if (!month) return ''
  const parts = month.split('-')
  let year = Number(parts[0])
  let mon = Number(parts[1]) + step
  while (mon > 12) {
    mon -= 12
    year += 1
  }
  while (mon < 1) {
    mon += 12
    year -= 1
  }
  return year + '-' + pad(mon)
}

function withinYear(month) {
  if (!month) return false
  const current = monthIndex(currentMonth())
  const asked = monthIndex(month)
  return asked <= current && asked >= current - 11
}

function monthIndex(month) {
  const parts = month.split('-')
  return Number(parts[0]) * 12 + Number(parts[1]) - 1
}

function monthTitle(month) {
  if (!month) return ''
  const parts = month.split('-')
  return Number(parts[0]) + '年' + Number(parts[1]) + '月'
}

function pad(value) {
  return value < 10 ? '0' + value : '' + value
}
</script>

<style>
.page {
  min-height: 100vh;
  padding: 12rpx 32rpx 0;
  background: #f5f6f8;
}

.hero {
  padding: 12rpx 8rpx 28rpx;
}

.month-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.brand {
  font-size: 44rpx;
  font-weight: 700;
  color: #1f2329;
}

.switch {
  min-width: 120rpx;
  padding: 8rpx 0;
  font-size: 26rpx;
  color: #00c48c;
  font-weight: 600;
}

.switch.disabled {
  color: #d0d4da;
}

.tagline {
  display: block;
  margin-top: 10rpx;
  font-size: 26rpx;
  color: #8b919a;
}

.banner {
  margin-bottom: 20rpx;
  padding: 20rpx 24rpx;
  border-radius: 20rpx;
  background: #fff1f0;
  color: #ff5c5c;
  font-size: 26rpx;
}

.calendar {
  padding: 24rpx 12rpx 12rpx;
  border-radius: 32rpx;
  background: #ffffff;
  box-shadow: 0 8rpx 28rpx rgba(31, 35, 41, 0.05);
}

.week,
.grid {
  display: flex;
  flex-wrap: wrap;
}

.week-label,
.cell-wrap {
  width: 14.28%;
  text-align: center;
}

.week-label {
  padding-bottom: 12rpx;
  font-size: 22rpx;
  color: #a8adb5;
}

.cell {
  margin: 6rpx 4rpx 10rpx;
  padding: 10rpx 0 12rpx;
  border-radius: 16rpx;
  background: #f7f8fa;
}

.day {
  display: block;
  margin-top: 2rpx;
  font-size: 26rpx;
  font-weight: 600;
  color: #1f2329;
}

.kcal {
  display: block;
  font-size: 18rpx;
  font-weight: 600;
}

.kcal.ok {
  color: #00c48c;
}

.kcal.over {
  color: #ff5c5c;
}

.nav-spacer {
  height: 180rpx;
}

.pressed {
  opacity: 0.75;
}
</style>
