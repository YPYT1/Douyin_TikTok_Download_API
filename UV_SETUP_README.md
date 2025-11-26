# UV 环境配置说明

## 环境已配置完成 ✅

项目已经使用 `uv` 成功配置，所有依赖已安装完毕。

## 已安装的关键依赖

- **DrissionPage**: 4.1.1.2 (浏览器自动化框架)
- **FastAPI**: 0.122.0
- **Pydantic**: 2.12.4
- **其他依赖**: 共 56 个包

## 如何运行脚本

使用 `uv run` 命令来运行 Python 脚本，这会自动使用项目的虚拟环境：

```bash
# 运行爬虫脚本（示例命令）
uv run python crawl_mix_drission.py --mix-id 7326746646719498279 --start 3 --login-wait 60
```

## 常用命令

### 查看帮助信息
```bash
uv run python crawl_mix_drission.py --help
```

### 同步依赖（如果需要更新）
```bash
uv sync
```

### 添加新依赖
```bash
uv add <package-name>
```

### 查看已安装的包
```bash
uv pip list
```

## 配置变更说明

为了支持 Python 3.13，已对 `pyproject.toml` 进行了以下更新：

1. 添加了 `DrissionPage>=4.0.0` 依赖
2. 更新了 `pydantic>=2.10.0` 和 `pydantic_core>=2.27.0`
3. 更新了 `fastapi>=0.115.0` 和 `starlette>=0.41.0`
4. 更新了 `typing_extensions>=4.12.2`

## 注意事项

- 所有 Python 命令都应该使用 `uv run python` 前缀
- 项目使用的是 Python 3.13
- 虚拟环境由 uv 自动管理，无需手动激活

## 故障排除

如果遇到依赖问题，可以尝试：

```bash
# 清理并重新安装
uv sync --reinstall
```
