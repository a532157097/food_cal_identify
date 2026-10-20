<template>
  <view class="page">
    <view v-if="errorText" class="banner">{{ errorText }}</view>
    <view class="today-card">
      <text class="today-label">当日合计</text>
      <view class="today-figure">
        <text class="today-kcal" :class="levelOf(totalKcal)">{{ kcalText(totalKcal) }}</text>
        <text class="today-unit">千卡</text>
      </view>
      <view class="macro-row">
        <view class="macro">
          <text class="macro-label">蛋白质</text>
          <text class="macro-value">{{ gramText(protein) }}</text>
        </view>
        <view class="macro macro-gap">
          <text class="macro-label">碳水</text>
          <text class="macro-value">{{ gramText(carb) }}</text>
        </view>
        <view class="macro macro-gap">
          <text class="macro-label">脂肪</text>
          <text class="macro-value">{{ gramText(fat) }}</text>
        </view>
      </view>
    </view>

    <view v-if="!loading && items.length === 0" class="empty">
      <text class="empty-title">这一天没有记录</text>
    </view>

    <view
      v-for="item in items"
      :key="item.id"
      class="card"
      hover-class="pressed"
      @tap="open(item)"
    >
      <image class="thumb" :src="imageOf(item)" mode="aspectFill"></image>
      <view class="meta">
        <text class="names">{{ titleOf(item) }}</text>
        <text class="kcal" :class="lineClass(item)">{{ lineOf(item) }}</text>
        <text class="time">{{ item.created_at }}</text>
      </view>
      <view class="ops" @tap.stop>
        <text v-if="item.status === 'failed'" class="op" @tap="reprocess(item)">{{ reprocessingId === item.id ? '处理中' : '重新处理' }}</text>
        <text class="op" @tap="retake(item)">{{ retakingId === item.id ? '重拍中' : '重拍' }}</text>
        <text class="op op-delete" @tap="remove(item)">删除</text>
      </view>
    </view>
  </view>
</template>

<script>
import { ensureLogin, reprocessRecord, request, resolveUrl, uploadRetake } from '../../utils/api.js'
import { compressPhoto } from '../../utils/image.js'
import { calorieLevel, foodNames, formatGram, formatKcal } from '../../utils/format.js'

export default {
  data() {
    return {
      date: '',
      items: [],
      totalKcal: 0,
      protein: 0,
      carb: 0,
      fat: 0,
      loading: false,
      errorText: '',
      retakingId: 0,
      reprocessingId: 0,
    }
  },
  onLoad(query) {
    if (!ensureLogin()) return
    this.date = (query && query.date) || ''
    if (this.date) {
      uni.setNavigationBarTitle({ title: this.date })
    }
  },
  onShow() {
    if (!ensureLogin()) return
    if (!this.date) return
    this.load()
  },
  methods: {
    load() {
      this.loading = true
      this.errorText = ''
      return request('/api/records?date=' + this.date)
        .then((body) => {
          const items = (body && body.items) || []
          items.sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)))
          const totals = sumNutrition(items)
          this.items = items
          this.totalKcal = body && body.total_calories_kcal ? body.total_calories_kcal : 0
          this.protein = totals.protein
          this.carb = totals.carb
          this.fat = totals.fat
        })
        .catch((err) => {
          if (err && err.statusCode === 401) {
            ensureLogin()
            return
          }
          this.errorText = (err && err.message) || '记录加载失败'
        })
        .then(() => {
          this.loading = false
        })
    },
    levelOf(value) {
      return calorieLevel(value)
    },
    kcalText(value) {
      return formatKcal(value)
    },
    gramText(value) {
      return formatGram(value)
    },
    imageOf(item) {
      return resolveUrl(item.image_url)
    },
    namesOf(item) {
      return foodNames(item.foods)
    },
    titleOf(item) {
      if (item.status === 'processing') return '处理中'
      if (item.status === 'failed') return '识别失败'
      return foodNames(item.foods)
    },
    lineOf(item) {
      if (item.status === 'processing') return '正在识别'
      if (item.status === 'failed') return item.summary || '识别没有完成'
      return this.kcalText(item.total_calories_kcal) + ' 千卡'
    },
    lineClass(item) {
      if (item.status === 'processing') return 'pending'
      if (item.status === 'failed') return 'failed'
      return ''
    },
    open(item) {
      uni.navigateTo({ url: '/pages/result/result?id=' + item.id })
    },
    reprocess(item) {
      if (!item || item.status !== 'failed' || this.reprocessingId) return
      this.reprocessingId = item.id
      reprocessRecord(item.id)
        .then(() => this.load())
        .catch((err) => {
          uni.showToast({ title: (err && err.message) || '重新处理失败', icon: 'none' })
        })
        .then(() => {
          this.reprocessingId = 0
        })
    },
    retake(item) {
      if (this.retakingId) return
      uni.showActionSheet({
        itemList: ['拍照', '从相册选择'],
        success: (res) => {
          this.chooseRetake(item, res.tapIndex === 0 ? 'camera' : 'album')
        },
      })
    },
    chooseRetake(item, source) {
      uni.chooseImage({
        count: 1,
        sizeType: ['compressed'],
        sourceType: [source],
        success: (res) => {
          const paths = res.tempFilePaths || []
          if (!paths.length) return
          this.retakingId = item.id
          uni.showLoading({ title: '正在压缩', mask: true })
          compressPhoto(paths[0])
            .then((path) => {
              uni.hideLoading()
              return uploadRetake(item.id, path)
            })
            .then(() => {
              uni.showToast({ title: '已更新，时间未变', icon: 'none' })
              return this.load()
            })
            .catch((err) => {
              uni.showToast({ title: (err && err.message) || '重拍失败', icon: 'none' })
            })
            .then(() => {
              this.retakingId = 0
            })
        },
        fail: (err) => {
          const msg = (err && err.errMsg) || ''
          if (msg.indexOf('cancel') >= 0 || msg.indexOf('取消') >= 0) return
          uni.showToast({ title: '没有拿到照片，请检查相机或相册权限', icon: 'none' })
        },
      })
    },
    remove(item) {
      uni.showModal({
        title: '删除这条记录？',
        content: '删除后不能恢复。',
        confirmText: '删除',
        confirmColor: '#ff5c5c',
        success: (res) => {
          if (!res.confirm) return
          request('/api/records/' + item.id, { method: 'DELETE' })
            .then(() => this.load())
            .catch((err) => {
              uni.showToast({ title: (err && err.message) || '删除失败', icon: 'none' })
            })
        },
      })
    },
  },
}

function sumNutrition(items) {
  const totals = { protein: 0, carb: 0, fat: 0 }
  ;(items || []).forEach((item) => {
    const foods = item && item.foods
    if (!Array.isArray(foods)) return
    foods.forEach((food) => {
      totals.protein += Number(food && food.protein_g) || 0
      totals.carb += Number(food && food.carb_g) || 0
      totals.fat += Number(food && food.fat_g) || 0
    })
  })
  return totals
}
</script>

<style>
.page {
  min-height: 100vh;
  padding: 24rpx 32rpx 48rpx;
  background: #f5f6f8;
}

.banner {
  margin-bottom: 20rpx;
  padding: 20rpx 24rpx;
  border-radius: 20rpx;
  background: #fff1f0;
  color: #ff5c5c;
  font-size: 26rpx;
}

.today-card {
  margin-bottom: 24rpx;
  padding: 28rpx 32rpx;
  border-radius: 28rpx;
  background: #ffffff;
  box-shadow: 0 8rpx 28rpx rgba(31, 35, 41, 0.05);
}

.today-label {
  display: block;
  font-size: 26rpx;
  color: #8b919a;
}

.today-figure {
  display: flex;
  align-items: flex-end;
  margin-top: 8rpx;
}

.today-kcal {
  font-size: 84rpx;
  line-height: 1;
  font-weight: 800;
}

.today-kcal.ok {
  color: #00c48c;
}

.today-kcal.over {
  color: #ff5c5c;
}

.today-unit {
  margin-left: 10rpx;
  margin-bottom: 8rpx;
  font-size: 26rpx;
  color: #8b919a;
}

.macro-row {
  display: flex;
  margin-top: 20rpx;
}

.macro {
  flex: 1;
}

.macro-gap {
  margin-left: 16rpx;
}

.macro-label {
  display: block;
  font-size: 22rpx;
  color: #a8adb5;
}

.macro-value {
  display: block;
  margin-top: 4rpx;
  font-size: 30rpx;
  font-weight: 600;
  color: #1f2329;
}

.empty {
  padding: 48rpx 32rpx;
  border-radius: 32rpx;
  background: #ffffff;
  text-align: center;
}

.empty-title {
  font-size: 30rpx;
  color: #8b919a;
}

.card {
  display: flex;
  align-items: center;
  margin-bottom: 20rpx;
  padding: 18rpx;
  border-radius: 28rpx;
  background: #ffffff;
  box-shadow: 0 8rpx 28rpx rgba(31, 35, 41, 0.05);
}

.thumb {
  width: 140rpx;
  height: 140rpx;
  border-radius: 22rpx;
  background: #eef8f4;
  flex-shrink: 0;
}

.meta {
  flex: 1;
  margin-left: 20rpx;
  margin-right: 12rpx;
  overflow: hidden;
}

.names {
  display: block;
  font-size: 30rpx;
  font-weight: 600;
  color: #1f2329;
}

.kcal {
  display: block;
  margin-top: 8rpx;
  font-size: 28rpx;
  color: #1f2329;
  font-weight: 600;
}

.pending {
  color: #8b919a;
  font-weight: 500;
}

.failed {
  color: #ff5c5c;
  font-weight: 500;
}

.time {
  display: block;
  margin-top: 6rpx;
  font-size: 22rpx;
  color: #a8adb5;
}

.ops {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.op {
  padding: 8rpx 4rpx;
  font-size: 24rpx;
  color: #00c48c;
}

.op-delete {
  color: #a8adb5;
}

.pressed {
  opacity: 0.75;
}
</style>
