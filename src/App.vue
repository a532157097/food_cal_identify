<script>
import { ensureLogin } from './utils/api.js'

export default {
  onLaunch() {
    ensureLogin()
  },
  onShow() {
    ensureLogin()
  },
  onHide() {},
}
</script>

<style>
page {
  background: #f5f6f8;
  color: #1f2329;
  font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
}

/* #ifdef H5 */
@media screen and (min-width: 768px) {
  uni-page-body {
    display: block;
    max-width: 430px;
    min-height: 100vh;
    margin: 0 auto;
    background: #f5f6f8;
    box-shadow: 0 0 40px rgba(31, 35, 41, 0.06);
  }
}
/* #endif */

view,
text,
input,
image,
button {
  box-sizing: border-box;
}

button::after {
  border: none;
}
</style>
