<template>
  <view v-if="username" class="page">
    <view class="status" :style="{ height: statusBarHeight + 'px' }"></view>
    <view class="hero">
      <view class="hero-row">
        <text class="brand">膳识</text>
        <view class="account">
          <text v-if="username" class="account-name">{{ username }}</text>
          <text v-if="username" class="account-action" @tap="logout">退出</text>
          <text v-else class="account-action" @tap="goLogin">登录</text>
          <text v-if="!username" class="account-action account-gap" @tap="goRegister">注册</text>
        </view>
      </view>
      <text class="tagline">拍下这餐，认出每一口的热量</text>
    </view>

    <view class="stage" @tap="preview">
      <image v-if="imagePath" class="photo" :src="imagePath" mode="aspectFill"></image>
      <view v-else class="placeholder">
        <text class="placeholder-mark">食</text>
        <text class="placeholder-title">还没有照片</text>
        <text class="placeholder-sub">拍照，或从相册选一张食物图片</text>
      </view>
    </view>

    <view class="actions">
      <view class="action" hover-class="pressed" @tap="pick('camera')">
        <text class="action-title">拍照</text>
        <text class="action-sub">对着这餐拍一张</text>
      </view>
      <view class="action action-gap" hover-class="pressed" @tap="pick('album')">
        <text class="action-title">相册</text>
        <text class="action-sub">选择已有图片</text>
      </view>
    </view>

    <view
      class="primary"
      :class="{ disabled: !imagePath || loading }"
      hover-class="pressed"
      @tap="submit"
    >
      <text class="primary-text">{{ loading ? '正在识别…' : '识别热量' }}</text>
    </view>
    <text v-if="errorText" class="error">{{ errorText }}</text>
    <text v-else class="hint">图片会交给你配置的 Coze 工作流，由其中的视觉模型估算食物和热量。</text>

    <view class="today-card">
      <text class="today-label">今日合计</text>
      <view class="today-figure">
        <text class="today-kcal" :class="levelOf(todayKcal)">{{ kcalText(todayKcal) }}</text>
        <text class="today-unit">千卡</text>
      </view>
      <view class="macro-row">
        <view class="macro">
          <text class="macro-label">蛋白质</text>
          <text class="macro-value">{{ gramText(todayProtein) }}</text>
        </view>
        <view class="macro macro-gap">
          <text class="macro-label">碳水</text>
          <text class="macro-value">{{ gramText(todayCarb) }}</text>
        </view>
        <view class="macro macro-gap">
          <text class="macro-label">脂肪</text>
          <text class="macro-value">{{ gramText(todayFat) }}</text>
        </view>
      </view>
      <text v-if="burnSaved" class="burn-line">今日消耗 {{ kcalText(burnKcal) }} 千卡</text>
      <text v-if="burnSaved" class="burn-line gap-line">热量缺口 <text :class="gapClass()">{{ kcalText(gapKcal()) }}</text> 千卡</text>
    </view>

    <text class="section-title">今日记录</text>
    <view v-if="todayError" class="banner">{{ todayError }}</view>
    <view v-if="!todayLoading && todayItems.length === 0" class="today-empty">今天还没有识别记录</view>
    <view
      v-for="item in todayItems"
      :key="item.id"
      class="record"
      hover-class="pressed"
      @tap="openRecord(item)"
    >
      <image class="thumb" :src="imageOf(item)" mode="aspectFill"></image>
      <view class="meta">
        <text class="names">{{ titleOf(item) }}</text>
        <text class="kcal" :class="lineClass(item)">{{ lineOf(item) }}</text>
        <text class="time">{{ item.created_at }}</text>
      </view>
      <view class="ops" @tap.stop>
        <text v-if="item.status === 'failed'" class="op" @tap="reprocessRecord(item)">{{ reprocessingId === item.id ? '处理中' : '重新处理' }}</text>
        <text class="op" @tap="retakeRecord(item)">{{ retakingId === item.id ? '重拍中' : '重拍' }}</text>
        <text class="op op-delete" @tap="removeRecord(item)">删除</text>
      </view>
    </view>

    <view class="nav-spacer"></view>
    <bottom-nav current="index"></bottom-nav>
  </view>
</template>

<script>
import BottomNav from '../../components/bottom-nav.vue'
import { clearAuth, ensureLogin, getAuth, reprocessRecord, request, resolveUrl, uploadIdentify, uploadRetake } from '../../utils/api.js'
import { calorieLevel, foodNames, formatGram, formatKcal } from '../../utils/format.js'
import { compressPhoto } from '../../utils/image.js'

export default {
  components: { BottomNav },
  data() {
    const auth = getAuth()
    return {
      statusBarHeight: 20,
      imagePath: '',
      loading: false,
      errorText: '',
      username: auth ? auth.username : '',
      todayKcal: 0,
      todayProtein: 0,
      todayCarb: 0,
      todayFat: 0,
      burnSaved: false,
      burnKcal: 0,
      todayItems: [],
      todayLoading: false,
      todayError: '',
      retakingId: 0,
      reprocessingId: 0,
    }
  },
  onLoad() {
    const info = uni.getSystemInfoSync()
    this.statusBarHeight = info.statusBarHeight || 0
  },
  onShow() {
    if (!ensureLogin()) return
    const auth = getAuth()
    this.username = auth ? auth.username : ''
    this.loadToday()
  },
  methods: {
    pick(source) {
      if (this.loading) return
      uni.chooseImage({
        count: 1,
        sizeType: ['compressed'],
        sourceType: [source],
        success: (res) => {
          const paths = res.tempFilePaths || []
          if (!paths.length) return
          this.errorText = ''
          uni.showLoading({ title: '正在压缩', mask: true })
          compressPhoto(paths[0])
            .then((path) => {
              this.imagePath = path
            })
            .then(() => {
              uni.hideLoading()
            })
        },
        fail: (err) => {
          const msg = (err && err.errMsg) || ''
          if (msg.indexOf('cancel') >= 0 || msg.indexOf('取消') >= 0) return
          this.errorText = '没有拿到照片，请检查相机或相册权限'
        },
      })
    },
    preview() {
      if (!this.imagePath) return
      uni.previewImage({ urls: [this.imagePath], current: this.imagePath })
    },
    goLogin() {
      uni.navigateTo({ url: '/pages/login/login?redirect=' + encodeURIComponent('/pages/index/index') })
    },
    goRegister() {
      uni.navigateTo({ url: '/pages/register/register?redirect=' + encodeURIComponent('/pages/index/index') })
    },
    logout() {
      request('/api/logout', { method: 'POST' })
        .catch(() => {})
        .then(() => {
          clearAuth()
          this.username = ''
          uni.reLaunch({ url: '/pages/login/login' })
        })
    },
    loadToday() {
      this.todayLoading = true
      this.todayError = ''
      return request('/api/records?date=' + todayText())
        .then((body) => {
          const items = (body && body.items) || []
          items.sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)))
          const totals = sumNutrition(items)
          this.todayItems = items
          this.todayKcal = body && body.total_calories_kcal ? body.total_calories_kcal : 0
          this.todayProtein = totals.protein
          this.todayCarb = totals.carb
          this.todayFat = totals.fat
          return request('/api/energy?date=' + todayText())
        })
        .then((body) => {
          if (!body) return
          this.burnSaved = !!body.saved
          this.burnKcal = body.total_kcal || 0
        })
        .catch((err) => {
          if (err && err.statusCode === 401) {
            ensureLogin()
            return
          }
          this.todayError = (err && err.message) || '今日记录加载失败'
        })
        .then(() => {
          this.todayLoading = false
        })
    },
    levelOf(value) {
      return calorieLevel(value)
    },
    kcalText(value) {
      return formatKcal(value)
    },
    gapKcal() {
      const burn = Number(this.burnKcal) || 0
      const intake = Number(this.todayKcal) || 0
      return Math.round((burn - intake) * 10) / 10
    },
    gapClass() {
      return this.gapKcal() < 0 ? 'gap-over' : 'gap-ok'
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
      return this.levelOf(item.total_calories_kcal)
    },
    openRecord(item) {
      uni.navigateTo({ url: '/pages/result/result?id=' + item.id })
    },
    reprocessRecord(item) {
      if (!item || item.status !== 'failed' || this.reprocessingId) return
      this.reprocessingId = item.id
      reprocessRecord(item.id)
        .then(() => this.loadToday())
        .catch((err) => {
          uni.showToast({ title: (err && err.message) || '重新处理失败', icon: 'none' })
        })
        .then(() => {
          this.reprocessingId = 0
        })
    },
    retakeRecord(item) {
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
              return this.loadToday()
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
    removeRecord(item) {
      uni.showModal({
        title: '删除这条记录？',
        content: '删除后不能恢复。',
        confirmText: '删除',
        confirmColor: '#ff5c5c',
        success: (res) => {
          if (!res.confirm) return
          request('/api/records/' + item.id, { method: 'DELETE' })
            .then(() => this.loadToday())
            .catch((err) => {
              uni.showToast({ title: (err && err.message) || '删除失败', icon: 'none' })
            })
        },
      })
    },
    clearPreview() {
      // #ifdef H5
      if (this.imagePath && this.imagePath.indexOf('blob:') === 0) {
        URL.revokeObjectURL(this.imagePath)
      }
      // #endif
      this.imagePath = ''
    },
    submit() {
      if (!getAuth()) {
        this.goLogin()
        return
      }
      if (!this.imagePath || this.loading) {
        if (!this.imagePath) this.errorText = '请先选择一张食物图片'
        return
      }
      this.loading = true
      this.errorText = ''
      uploadIdentify(this.imagePath)
        .then((record) => {
          this.clearPreview()
          uni.navigateTo({ url: '/pages/result/result?id=' + record.id })
        })
        .catch((err) => {
          this.errorText = (err && err.message) || '识别失败'
        })
        .then(() => {
          this.loading = false
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

function todayText() {
  const now = new Date()
  return now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate())
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

.hero-row {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
}

.brand {
  display: block;
  font-size: 64rpx;
  line-height: 1.15;
  font-weight: 700;
  letter-spacing: 0;
  color: #1f2329;
}

.account {
  display: flex;
  align-items: center;
  margin-bottom: 8rpx;
}

.account-name {
  max-width: 180rpx;
  font-size: 26rpx;
  color: #5c6370;
  overflow: hidden;
}

.account-action {
  font-size: 26rpx;
  color: #00c48c;
}

.account-gap {
  margin-left: 20rpx;
}

.tagline {
  display: block;
  margin-top: 12rpx;
  font-size: 28rpx;
  line-height: 1.5;
  color: #8b919a;
}

.stage {
  height: 560rpx;
  border-radius: 36rpx;
  overflow: hidden;
  background: #ffffff;
  box-shadow: 0 8rpx 28rpx rgba(31, 35, 41, 0.05);
}

.photo {
  width: 100%;
  height: 560rpx;
}

.placeholder {
  height: 560rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #ffffff;
}

.placeholder-mark {
  width: 112rpx;
  height: 112rpx;
  line-height: 112rpx;
  text-align: center;
  border-radius: 36rpx;
  background: #e8f8f3;
  color: #00c48c;
  font-size: 48rpx;
  font-weight: 700;
}

.placeholder-title {
  margin-top: 28rpx;
  font-size: 34rpx;
  color: #1f2329;
  font-weight: 600;
}

.placeholder-sub {
  margin-top: 10rpx;
  font-size: 26rpx;
  color: #a8adb5;
}

.actions {
  display: flex;
  margin-top: 24rpx;
}

.action {
  flex: 1;
  padding: 26rpx 28rpx;
  border-radius: 28rpx;
  background: #ffffff;
  box-shadow: 0 8rpx 28rpx rgba(31, 35, 41, 0.05);
}

.action-gap {
  margin-left: 20rpx;
}

.action-title {
  display: block;
  font-size: 32rpx;
  font-weight: 600;
  color: #1f2329;
}

.action-sub {
  display: block;
  margin-top: 8rpx;
  font-size: 24rpx;
  color: #a8adb5;
}

.primary {
  margin-top: 28rpx;
  height: 96rpx;
  border-radius: 999rpx;
  background: #00c48c;
  display: flex;
  align-items: center;
  justify-content: center;
}

.primary.disabled {
  background: #7ed9c0;
}

.primary-text {
  color: #ffffff;
  font-size: 32rpx;
  font-weight: 600;
  letter-spacing: 2rpx;
}

.hint,
.error {
  display: block;
  margin-top: 18rpx;
  padding: 0 12rpx;
  font-size: 24rpx;
  line-height: 1.6;
}

.hint {
  color: #a8adb5;
}

.error {
  color: #ff5c5c;
}

.today-card {
  margin-top: 28rpx;
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

.burn-line {
  display: block;
  margin-top: 18rpx;
  font-size: 26rpx;
  color: #5c6370;
}

.gap-line {
  margin-top: 8rpx;
}

.gap-ok {
  color: #00c48c;
}

.gap-over {
  color: #ff5c5c;
}

.today-unit {
  margin-left: 10rpx;
  margin-bottom: 8rpx;
  font-size: 26rpx;
  color: #8b919a;
}

.today-kcal.ok,
.kcal.ok {
  color: #00c48c;
}

.today-kcal.over,
.kcal.over {
  color: #ff5c5c;
}

.section-title {
  display: block;
  margin: 32rpx 8rpx 16rpx;
  font-size: 32rpx;
  font-weight: 600;
  color: #1f2329;
}

.banner {
  margin-bottom: 16rpx;
  padding: 20rpx 24rpx;
  border-radius: 20rpx;
  background: #fff1f0;
  color: #ff5c5c;
  font-size: 26rpx;
}

.today-empty {
  padding: 36rpx 28rpx;
  border-radius: 28rpx;
  background: #ffffff;
  color: #a8adb5;
  font-size: 26rpx;
  text-align: center;
}

.record {
  display: flex;
  align-items: center;
  margin-bottom: 20rpx;
  padding: 18rpx;
  border-radius: 28rpx;
  background: #ffffff;
  box-shadow: 0 8rpx 28rpx rgba(31, 35, 41, 0.05);
}

.thumb {
  width: 120rpx;
  height: 120rpx;
  border-radius: 20rpx;
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

.nav-spacer {
  height: 180rpx;
}

.pressed {
  opacity: 0.75;
}
</style>
