<template>
  <view class="page">
    <view v-if="errorText" class="banner">{{ errorText }}</view>

    <view v-if="record" class="body">
      <image class="photo" :src="imageUrl" mode="aspectFill" @tap="preview"></image>

      <view class="total">
        <text class="total-label">这一餐大约</text>
        <view class="total-row">
          <text class="total-num">{{ kcalText }}</text>
          <text class="total-unit">千卡</text>
        </view>
        <text v-if="record.summary" class="summary">{{ record.summary }}</text>
        <text class="time">{{ record.created_at }}</text>
      </view>

      <view v-if="foods.length === 0" class="note">
        <text class="note-text">这次没有拆出分项。如果上面是一段原文，请让 Coze 结束节点按约定输出 JSON。</text>
      </view>

      <view v-for="(food, index) in foods" :key="index" class="food">
        <view class="food-head">
          <text class="food-name">{{ food.name }}</text>
          <text class="food-kcal">{{ kcalOf(food.calories_kcal) }} 千卡</text>
        </view>
        <view class="food-sub">
          <text class="food-weight">约 {{ gramOf(food.weight_g) }}</text>
          <text v-if="food.note" class="food-confidence">{{ food.note }}</text>
          <text v-if="confidenceOf(food.confidence)" class="food-confidence">把握 {{ confidenceOf(food.confidence) }}</text>
        </view>
        <view class="macros">
          <view class="macro">
            <text class="macro-k">蛋白</text>
            <text class="macro-v">{{ gramOf(food.protein_g) }}</text>
          </view>
          <view class="macro macro-gap">
            <text class="macro-k">脂肪</text>
            <text class="macro-v">{{ gramOf(food.fat_g) }}</text>
          </view>
          <view class="macro macro-gap">
            <text class="macro-k">碳水</text>
            <text class="macro-v">{{ gramOf(food.carb_g) }}</text>
          </view>
        </view>
      </view>

      <view v-if="record.tips" class="tips">
        <text class="tips-label">建议</text>
        <text class="tips-text">{{ record.tips }}</text>
      </view>

      <view v-if="record.debug_url" class="debug" hover-class="pressed" @tap="copyDebug">
        <text class="debug-text">复制工作流调试链接</text>
      </view>
    </view>
  </view>
</template>

<script>
import { ensureLogin, request, resolveUrl } from '../../utils/api.js'
import { formatConfidence, formatGram, formatKcal } from '../../utils/format.js'

export default {
  data() {
    return {
      record: null,
      errorText: '',
    }
  },
  computed: {
    foods() {
      return (this.record && this.record.foods) || []
    },
    imageUrl() {
      return this.record ? resolveUrl(this.record.image_url) : ''
    },
    kcalText() {
      return this.record ? formatKcal(this.record.total_calories_kcal) : '--'
    },
  },
  onLoad(query) {
    if (!ensureLogin()) return
    const id = query && query.id
    if (!id) {
      this.errorText = '缺少识别记录'
      return
    }
    this.load(id)
  },
  methods: {
    load(id) {
      request('/api/records/' + id)
        .then((body) => {
          this.record = body
        })
        .catch((err) => {
          if (err && err.statusCode === 401) {
            uni.navigateTo({
              url: '/pages/login/login?redirect=' + encodeURIComponent('/pages/result/result?id=' + id),
            })
            return
          }
          this.errorText = (err && err.message) || '结果加载失败'
        })
    },
    kcalOf(value) {
      return formatKcal(value)
    },
    gramOf(value) {
      return formatGram(value)
    },
    confidenceOf(value) {
      return formatConfidence(value)
    },
    preview() {
      if (!this.imageUrl) return
      uni.previewImage({ urls: [this.imageUrl], current: this.imageUrl })
    },
    copyDebug() {
      if (!this.record || !this.record.debug_url) return
      uni.setClipboardData({ data: this.record.debug_url })
    },
  },
}
</script>

<style>
.page {
  min-height: 100vh;
  padding: 24rpx 36rpx 48rpx;
  background: #f5f6f8;
}

.banner {
  margin-bottom: 20rpx;
  padding: 20rpx 24rpx;
  border-radius: 20rpx;
  background: #fff1f0;
  color: #ff5c5c;
  font-size: 26rpx;
  line-height: 1.5;
}

.photo {
  width: 100%;
  height: 460rpx;
  border-radius: 32rpx;
  background: #ffffff;
  box-shadow: 0 8rpx 28rpx rgba(31, 35, 41, 0.05);
}

.total {
  margin-top: 28rpx;
  padding: 8rpx 8rpx 12rpx;
}

.total-label {
  display: block;
  font-size: 26rpx;
  color: #a8adb5;
}

.total-row {
  display: flex;
  align-items: flex-end;
  margin-top: 8rpx;
}

.total-num {
  font-size: 108rpx;
  line-height: 1;
  font-weight: 700;
  color: #1f2329;
}

.total-unit {
  margin-left: 12rpx;
  margin-bottom: 14rpx;
  font-size: 30rpx;
  color: #00a878;
}

.summary {
  display: block;
  margin-top: 16rpx;
  font-size: 30rpx;
  line-height: 1.6;
  color: #3c424c;
}

.time {
  display: block;
  margin-top: 10rpx;
  font-size: 22rpx;
  color: #a8adb5;
}

.note,
.tips {
  margin-top: 20rpx;
  padding: 24rpx 28rpx;
  border-radius: 24rpx;
  background: #ffffff;
  box-shadow: 0 8rpx 28rpx rgba(31, 35, 41, 0.05);
}

.note-text,
.tips-text {
  display: block;
  font-size: 26rpx;
  line-height: 1.6;
  color: #5c6370;
}

.tips-label {
  display: block;
  margin-bottom: 8rpx;
  font-size: 24rpx;
  color: #00a878;
}

.food {
  margin-top: 20rpx;
  padding: 28rpx;
  border-radius: 28rpx;
  background: #ffffff;
  box-shadow: 0 8rpx 28rpx rgba(31, 35, 41, 0.05);
}

.food-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.food-name {
  flex: 1;
  margin-right: 16rpx;
  font-size: 34rpx;
  font-weight: 600;
  color: #1f2329;
}

.food-kcal {
  font-size: 28rpx;
  color: #00a878;
  font-weight: 600;
}

.food-sub {
  display: flex;
  margin-top: 10rpx;
}

.food-weight,
.food-confidence {
  font-size: 24rpx;
  color: #a8adb5;
}

.food-confidence {
  margin-left: 20rpx;
}

.macros {
  display: flex;
  margin-top: 22rpx;
}

.macro {
  flex: 1;
  padding: 16rpx 0;
  border-radius: 18rpx;
  background: #f4fbf8;
  text-align: center;
}

.macro-gap {
  margin-left: 12rpx;
}

.macro:nth-child(1) {
  background: #eef5ff;
}

.macro:nth-child(2) {
  background: #fff4f6;
}

.macro:nth-child(3) {
  background: #fff8eb;
}

.macros .macro:nth-child(1) .macro-k {
  color: #5b8ff9;
}

.macros .macro:nth-child(2) .macro-k {
  color: #ff6b8a;
}

.macros .macro:nth-child(3) .macro-k {
  color: #f5a623;
}

.macro-k {
  display: block;
  font-size: 22rpx;
  color: #a8adb5;
}

.macro-v {
  display: block;
  margin-top: 6rpx;
  font-size: 28rpx;
  color: #1f2329;
  font-weight: 600;
}

.debug {
  margin-top: 28rpx;
  text-align: center;
}

.debug-text {
  font-size: 24rpx;
  color: #a8adb5;
}

.pressed {
  opacity: 0.75;
}
</style>
