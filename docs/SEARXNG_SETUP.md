# SearXNG 本地搜索引擎部署说明（Windows）

## 什么是 SearXNG

SearXNG 是一个开源的元搜索引擎，可以聚合 Google、Bing、Wikipedia 等 80+ 个搜索引擎的结果。ACS 资料采集助手通过 SearXNG 实现"输入主题，全网找资料"。

---

## 部署步骤

### 1. 确保 Docker Desktop 已安装并运行

```powershell
docker --version   # 确认 Docker 已安装
```

### 2. 创建部署目录

```powershell
mkdir D:\ACS_SearXNG
cd D:\ACS_SearXNG
mkdir searxng
```

### 3. 创建 `docker-compose.yml`

在 `D:\ACS_SearXNG` 下新建文件 `docker-compose.yml`，内容：

```yaml
services:
  searxng:
    image: docker.io/searxng/searxng:latest
    container_name: acs-searxng
    restart: unless-stopped
    ports:
      - "127.0.0.1:8080:8080"
    volumes:
      - ./searxng:/etc/searxng:rw
    environment:
      - SEARXNG_BASE_URL=http://127.0.0.1:8080/
      - SEARXNG_SECRET=change-this-to-a-long-random-string
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETGID
      - SETUID
```

### 4. 创建 `settings.yml`

在 `D:\ACS_SearXNG\searxng` 下新建文件 `settings.yml`，内容：

```yaml
use_default_settings: true

general:
  instance_name: "ACS Local SearXNG"

search:
  safe_search: 1
  formats:
    - html
    - json

server:
  secret_key: "change-this-to-a-long-random-string"
  bind_address: "0.0.0.0"
  limiter: false
  image_proxy: false
```

### 5. 启动容器

```powershell
cd D:\ACS_SearXNG
docker compose up -d
```

首次启动会下载镜像（约 500MB），请耐心等待。

### 6. 验证

```powershell
# 测试 JSON 接口
curl.exe "http://127.0.0.1:8080/search?q=园区废气治理案例&format=json"
```

如果返回 JSON 数据，说明部署成功。

---

## 常用命令

```powershell
# 查看容器状态
docker ps

# 查看容器日志
docker logs acs-searxng

# 停止容器
docker compose down

# 重启容器
docker compose restart

# 更新镜像
docker compose pull
docker compose up -d
```

---

## 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `safe_search` | 安全搜索等级 (0/1/2) | 1 |
| `formats` | 输出格式 | html + json |
| `limiter` | 速率限制 | false（本地使用关闭） |
| `image_proxy` | 图片代理 | false |

---

## 故障排查

| 问题 | 解决方法 |
|------|----------|
| Docker 命令报错 | 确认 Docker Desktop 已启动 |
| 镜像拉取失败 | 检查网络，或使用镜像加速器 |
| 端口已被占用 | 修改 `ports` 中的 `8080` 为其他端口 |
| SearXNG 返回 403 | 检查 `settings.yml` 中 `formats` 包含 `json` |
| 搜索无结果 | 检查 `docker logs acs-searxng` 查看错误 |
