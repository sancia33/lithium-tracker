# 🔋 碳酸锂日报 — Lithium Tracker

> 每个工作日自动推送碳酸锂期货/现货价格 + 行业资讯到飞书/企业微信/个人微信。

## ✨ 特性

- 📊 **多数据源兜底**：东方财富 + 新浪财经 + 生意社，单个挂了不影响整体
- 📈 **期货 + 现货**：广期所碳酸锂期货主力 + 现货报价
- 📰 **行业资讯**：自动检索当日碳酸锂相关重要新闻
- 🕐 **智能工作日判断**：自动识别法定节假日和调休补班，非工作日不推送
- 📢 **三通道推送**：飞书 / 企业微信 / Server酱(个人微信)，按需配置
- 🚀 **一键部署**：Fork 仓库 → 填 Secrets → 完事，不需要服务器

## 🚀 一键部署（给别人用）

### 第一步：Fork 仓库

点击右上角 **Fork** 按钮将仓库 Fork 到自己的 GitHub。

### 第二步：配置推送通道（至少选一个）

#### 方案 A：飞书机器人（推荐）
1. 打开飞书群 → 设置 → **群机器人** → 添加自定义机器人
2. 复制 **Webhook 地址**（形如 `https://open.feishu.cn/open-apis/bot/v2/hook/xxx`）
3. 如启用了**加签**，复制 **签名密钥**（SEC 开头）

#### 方案 B：企业微信群机器人
1. 打开企微群 → 右上角 → **群机器人** → 添加机器人
2. 复制 **Webhook 地址**

#### 方案 C：Server酱（个人微信）
1. 打开 https://sct.ftqq.com/ → 用微信扫码登录
2. 绑定公众号后，复制 **SendKey**

### 第三步：填入 GitHub Secrets

进入你的 Fork 仓库 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret 名称 | 填什么 | 是否必填 |
|---|---|---|
| `FEISHU_WEBHOOKS` | 飞书 Webhook 地址 | 二选一 |
| `FEISHU_SECRETS` | 飞书签名密钥（无加签则留空） | 否 |
| `WECOM_WEBHOOKS` | 企微 Webhook 地址 | 二选一 |
| `SERVERCHAN_KEYS` | Server酱 SendKey | 二选一 |
| `DEBUG` | `true`（调试）/ `false`（静默） | 否 |

> 💡 多个 Webhook 用逗号分隔，可同时推送到多个群。

### 第四步：测试运行

进入 **Actions** 标签页 → **碳酸锂日报** → **Run workflow**

勾选「强制运行」，点击绿色按钮。几秒后你的群就会收到消息。

### 完成！

之后每个工作日北京时间 **9:00** 会自动推送。不需要服务器，不需要开电脑。

---

## 🖥️ 本地运行（开发调试）

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
export FEISHU_WEBHOOKS="你的飞书webhook"
export DEBUG=true
export FORCE_RUN=true   # 跳过工作日判断

# 运行
python run.py
```

## 📁 项目结构

```
lithium-tracker/
├── .github/workflows/daily.yml   # GitHub Actions 定时任务
├── src/
│   ├── config.py                 # 配置（环境变量）
│   ├── holiday.py                # 工作日判断
│   ├── datasource.py             # 价格数据源（多源兜底）
│   ├── news.py                   # 行业资讯抓取
│   ├── formatter.py              # 消息格式化
│   └── notify.py                 # 推送模块（飞书/企微/Server酱）
├── run.py                        # 主入口
├── requirements.txt
└── README.md
```

## ❓ 常见问题

**Q: 推送失败怎么办？**
A: GitHub Actions → 你的 workflow run → 点进去看日志。常见原因：Webhook 地址填错了、机器人被移除。

**Q: 节假日也推送了？**
A: 节假日判断依赖第三方 API，极少数情况 API 不可用时会回退到周一~周五。建议关注推送内容自行判断。

**Q: 想改推送时间？**
A: 编辑 `.github/workflows/daily.yml` 中的 `cron` 表达式。`0 1 * * 1-5` 表示 UTC 1:00（北京时间 9:00）周一到周五。

**Q: 想推送更多信息？**
A: 编辑 `src/datasource.py` 添加更多数据源，或修改 `src/formatter.py` 调整消息格式。

**Q: 想给别人一键部署？**
A: 直接让他 Fork 你的仓库，按上面的步骤配置即可。核心是改 Secrets，不需要改代码。

## License

MIT
