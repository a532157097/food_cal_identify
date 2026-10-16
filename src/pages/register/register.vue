<template>
  <view class="page">
    <text class="title">注册账号</text>
    <text class="sub">注册后就可以上传食物图片</text>

    <input
      class="field"
      :value="username"
      placeholder="用户名，3 到 20 个字符"
      placeholder-class="placeholder"
      maxlength="20"
      @input="onUsername"
    />
    <input
      class="field"
      :value="password"
      password
      placeholder="密码，至少 6 位"
      placeholder-class="placeholder"
      maxlength="32"
      @input="onPassword"
    />
    <input
      class="field"
      :value="confirmPassword"
      password
      placeholder="再输入一次密码"
      placeholder-class="placeholder"
      maxlength="32"
      @input="onConfirm"
    />
    <text v-if="errorText" class="error">{{ errorText }}</text>

    <view class="primary" :class="{ disabled: loading }" hover-class="pressed" @tap="submit">
      <text class="primary-text">{{ loading ? '正在注册…' : '注册并登录' }}</text>
    </view>
  </view>
</template>

<script>
import { request, setAuth } from '../../utils/api.js'

export default {
  data() {
    return {
      username: '',
      password: '',
      confirmPassword: '',
      errorText: '',
      loading: false,
      redirect: '/pages/index/index',
    }
  },
  onLoad(query) {
    this.redirect = safeRedirect(query && query.redirect)
  },
  methods: {
    onUsername(event) {
      this.username = event.detail.value
    },
    onPassword(event) {
      this.password = event.detail.value
    },
    onConfirm(event) {
      this.confirmPassword = event.detail.value
    },
    submit() {
      if (this.loading) return
      if (this.password !== this.confirmPassword) {
        this.errorText = '两次密码不一致'
        return
      }
      this.errorText = ''
      this.loading = true
      request('/api/register', {
        method: 'POST',
        data: { username: this.username, password: this.password },
      })
        .then((body) => {
          setAuth(body)
          uni.reLaunch({ url: this.redirect })
        })
        .catch((err) => {
          this.errorText = (err && err.message) || '注册失败'
        })
        .then(() => {
          this.loading = false
        })
    },
  },
}

function safeRedirect(value) {
  if (!value) return '/pages/index/index'
  let path = String(value)
  for (let i = 0; i < 3; i += 1) {
    if (path.indexOf('/pages/') === 0) return path
    try {
      const next = decodeURIComponent(path)
      if (next === path) break
      path = next
    } catch (err) {
      break
    }
  }
  if (path.indexOf('/pages/') === 0) return path
  return '/pages/index/index'
}
</script>

<style>
.page {
  min-height: 100vh;
  padding: 48rpx 36rpx;
  background: #f5f6f8;
}

.title {
  display: block;
  font-size: 48rpx;
  font-weight: 700;
  color: #1f2329;
}

.sub {
  display: block;
  margin-top: 12rpx;
  margin-bottom: 36rpx;
  font-size: 26rpx;
  color: #8b919a;
}

.field {
  height: 96rpx;
  margin-bottom: 20rpx;
  padding: 0 28rpx;
  border-radius: 24rpx;
  background: #ffffff;
  box-shadow: 0 8rpx 28rpx rgba(31, 35, 41, 0.05);
  font-size: 30rpx;
  color: #1f2329;
}

.placeholder {
  color: #c5c8ce;
}

.error {
  display: block;
  margin-bottom: 16rpx;
  font-size: 26rpx;
  color: #ff5c5c;
}

.primary {
  height: 96rpx;
  margin-top: 12rpx;
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
}

.pressed {
  opacity: 0.75;
}
</style>
