# DrissionPage 抖音合集爬虫使用说明
python crawl_mix_drission.py --mix-id 7326746646719498279 --start 3 --login-wait 60
## 简介

`crawl_mix_drission.py` 是一个基于 DrissionPage 的抖音合集视频爬虫，使用浏览器网络监听方式获取评论数据。

## 环境要求

- Python 3.8+
- DrissionPage
- Chrome 浏览器

## 安装依赖

```bash
uv pip install DrissionPage pyyaml
```

## 基本用法

### 1. 爬取完整合集（交互模式）

```bash
python crawl_mix_drission.py --mix-id 7326746646719498279
```

运行后会显示：
```
[时间] ✅ 共发现 99 个视频

[时间] ℹ️  请选择爬取区间（直接回车表示全部爬取）
  从第几个视频开始? [1-99，默认1]: 
  到第几个视频结束? [1-99，默认99]: 
```

- **直接按两次回车**：爬取全部视频
- **输入数字**：指定爬取区间，例如输入 `10` 和 `20` 表示爬取第 10-20 个视频

### 2. 命令行指定数量（跳过交互）

```bash
# 爬取前 5 个视频
python crawl_mix_drission.py --mix-id 7326746646719498279 --limit 5
```

### 3. 只获取视频列表（不抓评论）

```bash
python crawl_mix_drission.py --mix-id 7326746646719498279 --no-comments
```

## 完整参数说明

| 参数 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `--mix-id` | ✅ | - | 合集ID或合集链接（支持短链接） |
| `--limit` | ❌ | 0 | 限制爬取视频数量，0表示交互选择 |
| `--no-comments` | ❌ | False | 不抓取评论 |
| `--max-comments` | ❌ | 2000 | 每个视频最大评论数 |
| `--sleep` | ❌ | 3.0 | 视频之间的间隔秒数 |
| `--out` | ❌ | output_drission | 输出目录 |
| `--headless` | ❌ | False | 无头模式（不显示浏览器） |
| `--login-wait` | ❌ | 60 | 登录等待秒数 |

## 使用示例

### 示例 1：基础爬取

```bash
python crawl_mix_drission.py --mix-id 7326746646719498279
```

### 示例 2：爬取前 10 个视频

```bash
python crawl_mix_drission.py --mix-id 7326746646719498279 --limit 10
```

### 示例 3：自定义输出目录

```bash
python crawl_mix_drission.py --mix-id 7326746646719498279 --out my_output
```

### 示例 4：增加等待时间（防止风控）

```bash
python crawl_mix_drission.py --mix-id 7326746646719498279 --sleep 5 --login-wait 120
```

### 示例 5：无头模式运行

```bash
python crawl_mix_drission.py --mix-id 7326746646719498279 --headless
```

### 示例 6：使用合集链接

```bash
# 短链接
python crawl_mix_drission.py --mix-id "https://v.douyin.com/xxxxx/"

# 完整链接
python crawl_mix_drission.py --mix-id "https://www.douyin.com/collection/7326746646719498279"
```

## 输出说明

### 目录结构

```
output_drission/
├── 001/                              # 第1个视频
│   └── 视频标题_视频ID.csv
├── 002/                              # 第2个视频
│   └── 视频标题_视频ID.csv
├── ...
└── 099/                              # 第99个视频
    └── 视频标题_视频ID.csv
```

### CSV 字段说明

| 字段 | 说明 |
|------|------|
| 序号 | 行号 |
| 视频ID | 抖音视频唯一标识 |
| 视频标题 | 视频描述 |
| 视频URL | 视频链接 |
| 发布时间 | Unix时间戳 |
| 视频时长(s) | 秒数 |
| 作者昵称 | 发布者名称 |
| 作者ID | 发布者ID |
| 点赞数 | 视频点赞数 |
| 收藏数 | 视频收藏数 |
| 分享数 | 视频分享数 |
| 播放数 | 视频播放数 |
| 评论总数 | 视频评论总数 |
| 层级 | video=视频信息, L1=一级评论, L2=二级评论 |
| 评论ID | 评论唯一标识 |
| 评论内容 | 评论文本 |
| 评论用户 | 评论者昵称 |
| 评论用户ID | 评论者ID |
| 评论点赞数 | 评论获赞数 |
| 回复数 | 评论的回复数 |
| 评论时间 | 评论发布时间 |
| IP属地 | 评论者IP归属地 |
| 回复目标用户 | 二级评论回复的目标用户 |

## 常见问题

### Q: 评论获取数量很少？

A: 可能原因：
1. 抖音风控，需要登录账号
2. 验证码弹窗，需要手动处理
3. 网络不稳定

解决方法：
- 确保 `crawlers/douyin/web/config.yaml` 中有有效的 Cookie
- 使用非无头模式运行，手动处理验证码
- 增加 `--sleep` 参数值

### Q: 如何获取 Cookie？

A: 
1. 在浏览器中登录抖音
2. 打开开发者工具 → Network → 刷新页面
3. 找到任意请求，复制 Request Headers 中的 Cookie
4. 粘贴到 `crawlers/douyin/web/config.yaml` 的 Cookie 字段

### Q: 程序提示登录失败？

A:
1. 检查 Cookie 是否过期
2. 增加 `--login-wait` 参数，手动扫码登录
3. 使用非无头模式查看登录状态

## 断点续爬

如果爬取中断，可以使用交互模式从断点继续：

```bash
python crawl_mix_drission.py --mix-id 7326746646719498279
```

然后输入上次中断的位置，例如：
```
从第几个视频开始? [1-99，默认1]: 25
到第几个视频结束? [25-99，默认99]: 
```

这样就会从第 25 个视频继续爬取到最后。

## 注意事项

1. **遵守抖音使用条款**：仅用于学习研究
2. **控制爬取频率**：避免对服务器造成压力
3. **保护隐私**：不要公开传播用户数据
4. **Cookie 安全**：不要泄露自己的登录凭证
