<template>
  <view class="page">
    <view v-if="errorText" class="banner">{{ errorText }}</view>
    <view class="total" :class="levelOf(totalKcal)">{{ kcalText(totalKcal) }} 千卡</view>

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
        <text class="names">{{ namesOf(item) }}</text>
        <text class="kcal">{{ kcalText(item.total_calories_kcal) }} 千卡</text>
        <text class="time">{{ item.created_at }}</text>
      </view>
      <view class="ops" @tap.stop>
        <text class="op" @tap="retake(item)">{{ retakingId === item.id ? '重拍中' : '重拍' }}</text>
        <text class="op op-delete" @tap="remove(item)">删除</text>
      </view>
    </view>
  </view>
</template>

<script>
import { ensureLogin, request, resolveUrl, uploadRetake } from '../../utils/api.js'
import { compressPhoto } from '../../utils/image.js'
import { calorieLevel, foodNames, formatKcal } from '../../utils/format.js'

export default {
  data() {
    return {
      date: '',
      items: [],
      totalKcal: 0,
      loading: false,
      errorText: '',
      retakingId: 0,
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
          this.items = items
          this.totalKcal = body && body.total_calories_kcal ? body.total_calories_kcal : 0
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
    imageOf(item) {
      return resolveUrl(item.image_url)
    },
    namesOf(item) {
      return foodNames(item.foods)
    },
    open(item) {
      uni.navigateTo({ url: '/pages/result/result?id=' + item.id })
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

.total {
  margin-bottom: 24rpx;
  font-size: 48rpx;
  font-weight: 700;
}

.total.ok {
  color: #00c48c;
}

.total.over {
  color: #ff5c5c;
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
