const MAX_EDGE = 1280
const JPEG_QUALITY = 0.7

export function compressPhoto(src) {
  if (!src) return Promise.resolve(src)
  // #ifdef H5
  return compressOnH5(src)
  // #endif
  // #ifndef H5
  return compressOnMiniProgram(src)
  // #endif
}

// #ifndef H5
function compressOnMiniProgram(src) {
  return new Promise((resolve) => {
    uni.getImageInfo({
      src,
      success(info) {
        const options = { src, quality: 60 }
        const width = info.width || 0
        const height = info.height || 0
        if (width >= height && width > MAX_EDGE) {
          options.compressedWidth = MAX_EDGE
        } else if (height > MAX_EDGE) {
          options.compressedHeight = MAX_EDGE
        }
        uni.compressImage({
          ...options,
          success(res) {
            resolve((res && res.tempFilePath) || src)
          },
          fail() {
            resolve(src)
          },
        })
      },
      fail() {
        resolve(src)
      },
    })
  })
}
// #endif

// #ifdef H5
function compressOnH5(src) {
  return new Promise((resolve) => {
    const image = new Image()
    image.onload = () => {
      const sourceWidth = image.naturalWidth || image.width
      const sourceHeight = image.naturalHeight || image.height
      if (!sourceWidth || !sourceHeight) {
        resolve(src)
        return
      }
      const fitted = fitEdge(sourceWidth, sourceHeight, MAX_EDGE)
      const canvas = document.createElement('canvas')
      canvas.width = fitted.width
      canvas.height = fitted.height
      const context = canvas.getContext('2d')
      if (!context) {
        resolve(src)
        return
      }
      context.drawImage(image, 0, 0, fitted.width, fitted.height)
      canvas.toBlob(
        (blob) => {
          if (!blob) {
            resolve(src)
            return
          }
          resolve(URL.createObjectURL(blob))
        },
        'image/jpeg',
        JPEG_QUALITY,
      )
    }
    image.onerror = () => resolve(src)
    image.src = src
  })
}

// #endif

// #ifdef H5
function fitEdge(width, height, maxEdge) {
  const longEdge = Math.max(width, height)
  if (longEdge <= maxEdge) {
    return { width, height }
  }
  const scale = maxEdge / longEdge
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  }
}
// #endif
