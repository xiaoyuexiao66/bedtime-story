# 睡前故事机

借鉴 [mommy-story-on-device](https://github.com/qhvssonic/mommy-story-on-device) 的思路，用 **Python + 网页** 重新实现的本地睡前故事应用：

- 录 3~8 秒你的声音
- 调云端大模型生成温馨的睡前故事
- 用 **ZipVoice 声音克隆**（本地推理）把故事读出来
- 故事保存在本地 SQLite，电脑和 iPhone 都能打开听

和原项目的区别：原项目是 Flutter 安卓 App（MNN + 安卓 arm64，只能在手机上跑）；这个版本是网页应用，服务跑在一台电脑上，手机用浏览器访问。

## 运行在哪台机器

| 机器 | 能做什么 |
|------|----------|
| **Linux 笔记本（推荐）** | 完整功能：故事生成 + 声音克隆（ZipVoice 本地推理） |
| macOS 13+ | 完整功能 |
| **macOS 12 及以下** | 只能调试界面：声音克隆引擎要求 macOS 13+，会自动退回系统语音 |

## 目录结构

```
bedtime-story/
├── app.py                  # 网页服务（FastAPI）
├── story_llm.py            # 调用云端大模型写故事
├── tts_engine.py           # 语音合成：ZipVoice 克隆 / 系统语音
├── db.py                   # SQLite 故事库
├── config.py               # 配置与环境变量
├── scripts/
│   ├── download_models.py  # 下载 ZipVoice 模型（约 194 MB）
│   └── test_tts.py         # 合成测试
├── templates/              # 网页模板
├── static/                 # 前端样式和录音 JS
├── models/                 # 模型（下载后出现，勿提交）
└── data/                   # 故事库和音频（自动生成）
```

## 一、在 Mac 上调试界面（今天就能跑）

```bash
cd ~/bedtime-story
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# 编辑 .env，填入 ANTHROPIC_API_KEY（可以从 ~/.claude/settings.json 里复制）

python app.py
```

浏览器打开 <http://localhost:8000>。

Mac 上会自动使用系统语音（没有克隆能力），用来验证录音、生成故事、播放、故事库这些流程。

> 如果 Mac 的虚拟环境里装过 sherpa-onnx（之前测试留下的），先卸载避免干扰：
> `pip uninstall -y sherpa-onnx sherpa-onnx-core`

## 二、在 Linux 笔记本上跑完整功能

### 1. 安装系统依赖

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

### 2. 把项目复制过去

在 Mac 上执行（把路径换成你的）：

```bash
rsync -av --exclude .venv --exclude models --exclude data \
  ~/bedtime-story/ xiaobo@10.97.204.65:~/bedtime-story/
```

### 3. 安装 Python 依赖

```bash
cd ~/bedtime-story
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-tts.txt
```

### 4. 下载模型并测试

```bash
python scripts/download_models.py    # 约 194 MB，支持断点续传
python scripts/test_tts.py           # 用示例声音合成一句话
```

`test_tts.py` 跑通后，会生成 `data/audio/test.wav`，听一下确认效果。

### 5. 启动服务

```bash
python app.py
```

- Mac 浏览器：<http://10.97.204.65:8000>
- iPhone Safari：<http://10.97.204.65:8000>

> 如果打不开，检查 Linux 防火墙：`sudo ufw allow 8000/tcp`

## 三、在 Mac / iPhone 上录音（需要 HTTPS）

浏览器只在 **HTTPS 或 localhost** 下允许使用麦克风。服务跑在 Linux 上时，Mac 用 `http://10.97.204.65:8000` 打开会无法录音。

解决办法：给服务加一个自签 HTTPS 证书。

在 Linux 上：

```bash
cd ~/bedtime-story
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout certs/key.pem -out certs/cert.pem -days 3650 \
  -subj "/CN=10.97.204.65"

BEDTIME_SSL_CERT=certs/cert.pem BEDTIME_SSL_KEY=certs/key.pem \
BEDTIME_PORT=8443 python app.py
```

然后：

- Mac/Chrome：打开 <https://10.97.204.65:8443>，提示“不安全”时点“高级 → 继续前往”
- iPhone/Safari：打开同一地址，点“显示详细信息 → 访问此网站”

浏览器信任证书后，录音按钮就能用了。

> iPhone 只是听故事的话，用 HTTP 就够了，不需要 HTTPS。

## 四、常见问题

**Q：合成很慢？**
ZipVoice 在 CPU 上跑，8GB 的 i5 笔记本预计每字 0.5~1.5 秒。故事是按句合成的，第一句出来就能开始播。如果太慢，可以把 `BEDTIME_TTS_THREADS` 调大（不超过 CPU 核心数），或把故事长度改短。

**Q：合成失败/进程退出？**
先确认 `python scripts/test_tts.py` 能跑通。模型文件不完整时 sherpa-onnx 可能直接退出，重新运行 `download_models.py` 校验。

**Q：iPhone 打不开？**
确认手机和电脑在同一个 Wi-Fi；ZeroTier 的地址在手机上也一样能用（手机装 ZeroTier 并加入同一网络）。

**Q：故事生成报错？**
检查 `.env` 里的 `ANTHROPIC_BASE_URL`、`ANTHROPIC_API_KEY`、`ANTHROPIC_MODEL` 是否和 `~/.claude/settings.json` 里一致。

## 安全提醒

- `.env` 里有你的 API Key，权限设为 600：`chmod 600 .env`
- 不要提交 `.env`、`data/`、`models/`（`.gitignore` 已排除）
- 服务监听 `0.0.0.0`，同一局域网的人都能访问；在家用没问题，公共网络请改成 `BEDTIME_HOST=127.0.0.1`

## 后续可以加的功能

- 流式合成：合成一句播一句，首句更快
- 睡眠定时、背景音
- 故事收藏/删除/搜索
- 多声音管理（奶奶、爸爸）
- PWA：在 iPhone 上“添加到主屏幕”，像 App 一样打开