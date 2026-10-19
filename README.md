# 膳识

上传一张食物图片，识别图里的食物和热量。前端用 uni-app，同一套页面可以发布成 H5 和微信小程序。大模型不写在客户端里，图片由 Python 服务转交给扣子（Coze）工作流。

这是第一版，还没有已发布的旧客户端。后面如果改接口，只增加字段，不要改掉或删掉现有字段：`id`、`image_url`、`foods`、`total_calories_kcal`、`summary`、`tips`、`debug_url`、`created_at`。`foods` 里的字段同样保持：`name`、`weight_g`、`calories_kcal`、`protein_g`、`fat_g`、`carb_g`、`confidence`。

## 目录

- `src/`：uni-app 页面
- `server/`：接收图片、调用 Coze、把结果写入 SQLite
- `tests/test_identify_flow.py`：接口和数据库交叉验证

## 配置 Coze 工作流

1. 在扣子里新建工作流并发布。
2. 开始节点增加一个图片参数，名字要和 `COZE_IMAGE_PARAM` 一致，默认是 `image`。
3. 接一个能看图的模型节点。建议让模型只输出下面这种 JSON：

```json
{
  "foods": [
    {
      "name": "白米饭",
      "weight_g": 200,
      "calories_kcal": 232,
      "protein_g": 5.2,
      "fat_g": 0.6,
      "carb_g": 51.6,
      "confidence": 0.92
    }
  ],
  "total_calories_kcal": 232,
  "summary": "一碗白米饭",
  "tips": "主食可以少盛一点"
}
```

4. 结束节点把这段 JSON 放到输出参数 `output` 或 `result`。服务也会尝试从纯文本、Markdown 代码块和中文字段里解析。
5. 在扣子开放平台创建个人访问令牌，权限需要能上传文件并运行该工作流。
6. 复制 `server/.env.example` 为 `server/.env`，填入 `COZE_API_TOKEN` 和 `COZE_WORKFLOW_ID`。

图片参数默认按字符串传递：`"{\"file_id\":\"...\"}"`。如果工作流要求对象，把 `COZE_IMAGE_VALUE_STYLE` 改成 `object`。工作流运行很久时，把 `COZE_IS_ASYNC` 设为 `1`。

还没配好令牌、只想先看页面时，把 `COZE_MOCK` 设为 `1`。这时不会请求 Coze，接口返回一份固定示例，结果里的建议会标明这是模拟数据。

## 启动服务

在项目根目录执行：

```bash
python3 -m venv server/.venv
source server/.venv/bin/activate
pip install -r server/requirements.txt
cp server/.env.example server/.env
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

令牌只放在服务端。不要写进小程序代码。

## Docker 部署

服务器上需要先装好 Docker，并在项目根目录准备好 `server/.env`。构建镜像时不会把这个文件打进去，启动容器时再用 `--env-file` 读它。

在项目根目录执行：

```bash
docker build -t food-cal-identify:h5 .
docker run -d \
  --name food-cal \
  --restart unless-stopped \
  -p 8080:8000 \
  --env-file server/.env \
  -v food-cal-data:/app/server/data \
  -v food-cal-uploads:/app/server/uploads \
  food-cal-identify:h5
```

浏览器打开 `http://服务器地址:8080`。`-p` 左边的 `8080` 是宿主机端口，容器里的服务仍是 `8000`。宿主机上 8080 已被占用时，只改左边，例如 `-p 38080:8000`。

`food-cal-data` 保存用户和识别记录，`food-cal-uploads` 保存上传的图片。不要删除这两个卷。

## 更新后重新部署

拉到新代码后要重新构建镜像，再换成新容器。只重启原来的容器不会用上新代码，页面也不会更新。

在项目根目录执行：

```bash
git pull
docker build -t food-cal-identify:h5 .
docker stop food-cal
docker rm food-cal
docker run -d \
  --name food-cal \
  --restart unless-stopped \
  -p 8080:8000 \
  --env-file server/.env \
  -v food-cal-data:/app/server/data \
  -v food-cal-uploads:/app/server/uploads \
  food-cal-identify:h5
```

`docker rm` 只删除容器。上面两个卷还在，账号、记录和图片会保留。不要执行 `docker volume rm food-cal-data` 或 `docker volume rm food-cal-uploads`。

如果上次启动时改过宿主机端口，重新运行时继续用同一个 `-p`。

## 启动 H5

```bash
npm install
npm run dev:h5
```

浏览器打开终端里给出的本地地址。开发时页面请求 `/api` 和 `/uploads`，由 Vite 转发到 `127.0.0.1:8000`。

发布：

```bash
npm run build:h5
```

产物在 `dist/build/h5`。页面和接口需要放在同一个域名下。Docker 镜像已经这样做了。

## 发布微信小程序

1. 在 `src/manifest.json` 的 `mp-weixin.appid` 填入小程序 AppID。
2. 小程序固定请求 `http://127.0.0.1:8000`，写在 `src/utils/api.js`。模拟器可以访问这个地址；真机要改成电脑的局域网地址后重新编译。
3. 编译：

```bash
npm run dev:mp-weixin
```

4. 用微信开发者工具导入 `dist/dev/mp-weixin`。开发阶段在「详情 - 本地设置」勾选不校验合法域名。`manifest` 里也把 `urlCheck` 设成了 `false`，方便本地调试。
5. 正式发布前，把接口放到 HTTPS 域名，并在微信公众平台配置 request 合法域名和 uploadFile 合法域名。正式版不能请求任意 HTTP 地址。

上传发布包：

```bash
npm run build:mp-weixin
```

产物在 `dist/build/mp-weixin`。

## 页面

- 识别：拍照或从相册选图，上传后跳到结果。
- 结果：总热量、每种食物的重量、热量、蛋白质、脂肪、碳水。
- 首页：显示今日合计（热量、蛋白质、碳水、脂肪）和当天的识别记录，早的在上面。热量超过 2000 千卡为红色，不超过为绿色。记录可以重拍或删除，重拍后时间不变。
- 本月：按天查看热量，可以往前翻到最近一年，点某一天看当天记录。当天记录可以重拍或删除，重拍后时间不变。

## 测试

```bash
source server/.venv/bin/activate
python3 tests/test_identify_flow.py
```

脚本使用模拟模式，不会请求 Coze。它会写入临时 SQLite，并用另一条 SQL 连接核对接口结果；结束时把数据库文件恢复成运行前的内容。参数写在脚本的默认值里：数据库是 `tests/tmp_food_cal.db`，图片目录是 `tests/tmp_uploads`。
