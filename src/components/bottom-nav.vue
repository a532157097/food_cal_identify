<template>
  <view class="bottom-nav">
    <view
      class="nav-item"
      :class="{ active: current === 'index' }"
      hover-class="pressed"
      @tap="go('/pages/index/index')"
    >
      <text class="nav-mark">拍</text>
      <text class="nav-label">识别</text>
    </view>
    <view
      class="nav-item"
      :class="{ active: current === 'month' }"
      hover-class="pressed"
      @tap="go('/pages/month/month')"
    >
      <text class="nav-mark">历</text>
      <text class="nav-label">历史</text>
    </view>
  </view>
</template>

<script>
export default {
  props: {
    current: {
      type: String,
      default: 'index',
    },
  },
  methods: {
    go(url) {
      const pages = getCurrentPages()
      const route = pages.length ? pages[pages.length - 1].route : ''
      const target = url.replace(/^\//, '')
      if (route === target) return
      uni.reLaunch({ url })
    },
  },
}
</script>

<style>
.bottom-nav {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 20;
  display: flex;
  background: #ffffff;
  border-top: 1px solid rgba(31, 35, 41, 0.06);
  box-shadow: 0 -8rpx 24rpx rgba(31, 35, 41, 0.04);
  padding-bottom: constant(safe-area-inset-bottom);
  padding-bottom: env(safe-area-inset-bottom);
}

.nav-item {
  flex: 1;
  height: 112rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.nav-mark {
  width: 44rpx;
  height: 44rpx;
  line-height: 44rpx;
  text-align: center;
  border-radius: 22rpx;
  font-size: 22rpx;
  color: #a8adb5;
  background: #f2f4f7;
}

.nav-label {
  margin-top: 6rpx;
  font-size: 22rpx;
  color: #a8adb5;
}

.nav-item.active .nav-mark {
  color: #ffffff;
  background: #00c48c;
}

.nav-item.active .nav-label {
  color: #00c48c;
  font-weight: 600;
}

.pressed {
  opacity: 0.7;
}

/* #ifdef H5 */
@media screen and (min-width: 768px) {
  .bottom-nav {
    width: 430px;
    left: 50%;
    right: auto;
    margin-left: -215px;
  }
}
/* #endif */
</style>
