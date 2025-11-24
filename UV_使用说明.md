# UV环境使用说明

## ✅ 已完成的工作

### 1. UV环境配置
- ✅ 使用UV创建了Python 3.11虚拟环境
- ✅ 安装了所有项目依赖包（38个包）
- ✅ 虚拟环境路径：`.venv/`

### 2. 功能验证结果

**✓ 测试通过的功能：**
- ✅ 从分享链接提取视频ID（3个链接全部成功）
- ✅ 从合集URL提取合集ID（功能正常）
- ✅ URL解析和重定向功能正常

**示例结果：**
```
链接: https://v.douyin.com/XoK0FI1zKgM/
  ✓ 视频ID: 7409470825398635816
  ✓ 真实地址: https://www.douyin.com/video/7409470825398635816

合集URL: https://www.douyin.com/collection/7348687990509553679
  ✓ 合集ID: 7348687990509553679
```

## 🔧 UV命令使用

### 激活虚拟环境
```powershell
# PowerShell
.\.venv\Scripts\Activate.ps1

# CMD
.venv\Scripts\activate.bat
```

### 使用UV运行Python脚本
```powershell
# 方式1: 直接使用虚拟环境的Python
.venv\Scripts\python.exe your_script.py

# 方式2: 使用UV运行
C:\Users\Administrator\.local\bin\uv.exe run python your_script.py
```

### 安装新包
```powershell
# 使用UV安装
C:\Users\Administrator\.local\bin\uv.exe pip install package_name

# 更新requirements.txt
C:\Users\Administrator\.local\bin\uv.exe pip install -r requirements.txt
```

## 📝 下一步：配置Cookie并测试完整流程

### 1. 获取抖音Cookie

1. 打开浏览器，访问 https://www.douyin.com
2. 登录你的抖音账号
3. 按F12打开开发者工具
4. 切换到"网络"(Network)标签
5. 刷新页面
6. 找到任意请求，在请求头中找到 `Cookie`
7. 复制完整的Cookie值

### 2. 配置Cookie

编辑文件：`crawlers/douyin/web/config.yaml`

找到以下部分并替换Cookie：
```yaml
TokenManager:
  douyin:
    headers:
      Cookie: "你的Cookie值"
```

### 3. 获取真实合集地址

**方法1：从视频页面找**
1. 在浏览器中打开你的视频链接
2. 如果视频属于合集，页面会显示合集信息
3. 点击合集名称，浏览器地址栏会显示合集URL
4. 格式类似：`https://www.douyin.com/collection/xxxxxxxx`

**方法2：使用我们的脚本自动提取**
运行以下命令：
```powershell
.venv\Scripts\python.exe test_mix_flow.py
```

脚本会自动从视频数据中提取合集ID和合集地址。

### 4. 运行完整测试

配置好Cookie后，运行完整测试：
```powershell
# 测试ID提取
.venv\Scripts\python.exe test_mix_simple.py

# 测试完整流程（需要Cookie）
.venv\Scripts\python.exe test_mix_flow.py
```

## 🎯 验证结果

**已验证的功能：**
- ✅ 能从分享链接找到真实视频ID
- ✅ 能从合集URL提取合集ID  
- ✅ URL重定向解析功能正常

**需要Cookie才能验证的功能：**
- ⏳ 获取视频详情（标题、点赞数等）
- ⏳ 获取合集中的所有视频列表
- ⏳ 获取评论数据

## 📊 流程总结

```
分享链接 
  ↓ (自动重定向)
视频真实ID 
  ↓ (获取视频详情，需要Cookie)
合集ID 
  ↓ (爬取合集，需要Cookie)
99个视频的完整数据
  ↓
保存到CSV文件
```

**当前进度：** ✅ 步骤1-2完成，等待Cookie配置完成后续步骤

## 🚀 快速开始命令

```powershell
# 1. 确保在项目目录
cd D:\Douyin_TikTok_Download_API

# 2. 运行简化测试（不需要Cookie）
.venv\Scripts\python.exe test_mix_simple.py

# 3. 配置Cookie后运行完整测试
.venv\Scripts\python.exe test_mix_flow.py

# 4. 运行完整爬虫
.venv\Scripts\python.exe douyin_mix_scraper.py
```

## 💡 常见问题

### Q: 如何知道自己的视频是否属于合集？
A: 在浏览器中打开视频页面，如果页面上显示合集名称，就属于合集。

### Q: 如何找到合集中有多少个视频？
A: 配置好Cookie后，运行测试脚本会显示合集视频总数。

### Q: Cookie会过期吗？
A: 会的，需要定期更新。如果爬取失败，首先检查Cookie是否过期。

### Q: 可以不配置Cookie吗？
A: 不行。抖音API需要Cookie来验证请求，否则返回空数据。


合集地址:
9- 6.46 C@h.od mDH:/ 10/07 我正在看【绘说现代化】长按复制此条消息，打开抖音搜索，一起看合集~ https://v.douyin.com/upgB8WBR3Ds/ 0@5.com :4pm


