const AUTH_KEY = 'food_cal_auth'

export function getAuth() {
  const saved = uni.getStorageSync(AUTH_KEY)
  if (saved && typeof saved === 'object' && saved.token) {
    return { token: String(saved.token), username: String(saved.username || '') }
  }
  return null
}

export function setAuth(auth) {
  uni.setStorageSync(AUTH_KEY, {
    token: auth.token,
    username: auth.username || '',
  })
}

export function clearAuth() {
  uni.removeStorageSync(AUTH_KEY)
}

function currentPage() {
  const pages = getCurrentPages()
  const page = pages.length ? pages[pages.length - 1] : null
  if (page && page.route) {
    return { route: page.route, options: page.options || {} }
  }
  let route = ''
  const options = {}
  // #ifdef H5
  const hash = typeof location !== 'undefined' && location.hash ? location.hash.replace(/^#/, '') : ''
  const parts = hash.split('?')
  if (parts[0].indexOf('/pages/') === 0) {
    route = parts[0].replace(/^\//, '')
    if (parts[1]) {
      parts[1].split('&').forEach((pair) => {
        const bits = pair.split('=')
        if (!bits[0]) return
        options[decodeURIComponent(bits[0])] = decodeURIComponent(bits[1] || '')
      })
    }
  }
  // #endif
  return { route, options }
}

export function ensureLogin() {
  if (getAuth()) return true
  const current = currentPage()
  const route = current.route
  if (route === 'pages/login/login' || route === 'pages/register/register') return false
  let redirect = '/pages/index/index'
  if (route) {
    redirect = '/' + route
    const query = Object.keys(current.options)
      .map((key) => encodeURIComponent(key) + '=' + encodeURIComponent(current.options[key] || ''))
      .join('&')
    if (query) redirect += '?' + query
  }
  uni.reLaunch({
    url: '/pages/login/login?redirect=' + encodeURIComponent(redirect),
  })
  return false
}

function authHeader() {
  const auth = getAuth()
  if (!auth) return {}
  return { Authorization: 'Bearer ' + auth.token }
}

function getBaseUrl() {
  // #ifdef H5
  return ''
  // #endif
  // #ifndef H5
  return 'http://127.0.0.1:8000'
  // #endif
}

export function resolveUrl(path) {
  if (!path) return ''
  if (/^https?:\/\//.test(path)) return path
  const base = getBaseUrl()
  if (!base) return path
  return base + (path.charAt(0) === '/' ? path : '/' + path)
}

function joinUrl(path) {
  const base = getBaseUrl()
  if (!base) return path
  return base + path
}

function readMessage(body, fallback) {
  if (body && typeof body === 'object' && body.message) return body.message
  return fallback
}

function rejectWithStatus(reject, statusCode, message) {
  if (statusCode === 401) clearAuth()
  const error = new Error(message)
  error.statusCode = statusCode
  reject(error)
}

export function request(path, options) {
  const opts = options || {}
  return new Promise((resolve, reject) => {
    uni.request({
      url: joinUrl(path),
      method: opts.method || 'GET',
      data: opts.data,
      header: authHeader(),
      timeout: opts.timeout || 30000,
      success(res) {
        const body = res.data
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(body)
          return
        }
        rejectWithStatus(reject, res.statusCode, readMessage(body, '请求失败'))
      },
      fail(err) {
        reject(new Error((err && err.errMsg) || '网络请求失败'))
      },
    })
  })
}

export function uploadRetake(recordId, filePath) {
  return uploadFile('/api/records/' + recordId + '/retake', filePath, '重拍失败')
}

export function uploadIdentify(filePath) {
  return uploadFile('/api/identify', filePath, '识别失败')
}

function uploadFile(path, filePath, fallback) {
  return new Promise((resolve, reject) => {
    uni.uploadFile({
      url: joinUrl(path),
      filePath,
      name: 'file',
      header: authHeader(),
      timeout: 180000,
      success(res) {
        let body = {}
        try {
          body = typeof res.data === 'string' ? JSON.parse(res.data || '{}') : res.data || {}
        } catch (err) {
          reject(new Error('服务返回了无法解析的内容'))
          return
        }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(body)
          return
        }
        rejectWithStatus(reject, res.statusCode, readMessage(body, fallback))
      },
      fail(err) {
        reject(new Error((err && err.errMsg) || '上传失败'))
      },
    })
  })
}
