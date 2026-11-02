# ZECTRIX NOTE4 MCP Server

通过 [ZECTRIX 极趣云平台 Open API](https://wiki.zectrix.com/zh/software/api-docs) 控制
小铁吧 NOTE4 智能墨水屏便签（4.2 寸 400×300）的标准 MCP 服务器，适用于 Claude Desktop、
Cursor、Cherry Studio 等任何支持 MCP 的客户端。

## 工具清单

| 工具 | 说明 |
|---|---|
| `list_devices` | 获取已绑定设备列表 |
| `set_sync_interval` | 修改设备同步周期（0/10/30/60/180/720 分钟） |
| `list_todos` | 待办列表（可按状态/设备过滤） |
| `create_todo` | 创建待办（标题、截止日期时间、重复规则、优先级、绑定设备） |
| `update_todo` | 更新待办字段 |
| `set_todo_completed` | 标记完成 / 取消完成 |
| `delete_todo` | 删除待办 |
| `push_text` | 推送纯文本（≤5000 字，可调字号，可持久化到指定页） |
| `push_structured_text` | 推送标题+正文（≤200 字标题 + ≤5000 字正文） |
| `push_image` | 推送本地图片（最多 5 张、单张 ≤2MB，可选抖动算法） |
| `push_text_image` | 将多行文本渲染为黑白图片推送（支持标题/自动换行，需中文字体） |
| `clear_pages` | 删除单页 / 清空全部页面 |

## 安装

```bash
cd zectrix-mcp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## uvx / pipx 一键安装

项目已提供标准打包配置（`pyproject.toml`），可一键安装为 `zectrix-mcp` 命令，之后无需再写死
`.venv/bin/python` 与 `server.py` 的绝对路径：

```bash
# pipx：在项目目录下安装到独立环境，生成全局命令 zectrix-mcp
cd zectrix-mcp
pipx install .

# uvx：免安装，在项目目录下临时运行（发布到 PyPI 后可直接 uvx zectrix-mcp）
uvx --from . zectrix-mcp
```

安装完成后，客户端配置里的「命令」直接填 `zectrix-mcp`、参数留空即可，下文各客户端示例已按此更新；
发布到 PyPI 后也可直接使用 `uvx zectrix-mcp` 作为命令。

> 提示：通过 pipx/uvx 安装后，请优先使用客户端配置的 `env` 块（方式 B）传入密钥；
> 源码目录 `.env` 的自动加载仅在直接运行 `server.py` 时生效。

## 获取 API Key

1. 浏览器打开 https://cloud.zectrix.com，用小程序「我的 → 扫一扫登录平台」扫码登录
2. 平台菜单进入「开放 API」
3. 点击「创建 API Key」，妥善保存（形如 `zt_xxx`，等同于账号密码，勿公开）

## 配置密钥的两种方式（任选其一）

**方式 A：`.env` 文件（推荐，最简单）**

在 `server.py` 同目录创建 `.env`，server 启动时会自动加载（真实环境变量优先于 `.env`）：

```bash
cd zectrix-mcp
cp .env.example .env   # 然后编辑 .env，填入真实 Key 和 MAC
```

`.env` 内容：

```
ZECTRIX_API_KEY=zt_你的key
ZECTRIX_DEVICE_ID=AA:BB:CC:DD:EE:FF
```

**方式 B：客户端配置的 `env` 块**

在下方客户端配置的 `"env"` 中直接填写。若两种方式都配了，客户端 `env` 优先。

## 快速验证

```bash
cd zectrix-mcp && ZECTRIX_API_KEY=zt_xxx ZECTRIX_DEVICE_ID=AA:BB:CC:DD:EE:FF \
  .venv/bin/python server.py
```

不设环境变量时，server 会自动读取同目录 `.env`。另开终端用任意 MCP 客户端连接，或直接调用 `list_devices` 确认鉴权成功。

## 客户端配置

### 豆包工作（Doubao Work）

1. 打开豆包客户端，点击左侧「插件·技能·伙伴」→「插件」页
2. 点击右上角「添加」→「新建自定义插件」（即新建自定义连接器）
3. 按下表填写（传输类型选 **STDIO**）：

| 字段 | 值 |
|---|---|
| 服务器名称 | zectrix 小铁吧 |
| 传输类型 | STDIO |
| 命令 | `zectrix-mcp` |
| 参数 | （留空） |
| 环境变量 | `ZECTRIX_API_KEY` = `zt_xxx`；`ZECTRIX_DEVICE_ID` = `AA:BB:CC:DD:EE:FF` |

   参数与环境变量点击「+ 添加」逐条添加。
4. 保存后，在「新工作任务」对话中输入 `/` 或 `@` 搜索并选中该插件，即可直接下发控制指令。

注意事项：
- 自定义连接器仅支持在本地电脑中使用
- 使用 `zectrix-mcp` 命令时，请在连接器的环境变量里填入 Key（方式 B）；直接运行 `server.py` 源码时才可依赖同目录 `.env` 自动加载

### Claude Desktop

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "zectrix": {
      "command": "zectrix-mcp",
      "env": {
        "ZECTRIX_API_KEY": "zt_xxx",
        "ZECTRIX_DEVICE_ID": "AA:BB:CC:DD:EE:FF"
      }
    }
  }
}
```

保存后重启 Claude Desktop。

### Cursor

项目根目录创建 `.cursor/mcp.json`：

```json
{
  "mcpServers": {
    "zectrix": {
      "command": "zectrix-mcp",
      "env": {
        "ZECTRIX_API_KEY": "zt_xxx",
        "ZECTRIX_DEVICE_ID": "AA:BB:CC:DD:EE:FF"
      }
    }
  }
}
```

### Cherry Studio / 其他客户端

「MCP 服务器 → 添加 → 标准输入流（stdio）」：

- 命令：`zectrix-mcp`
- 参数：（留空）
- 环境变量：`ZECTRIX_API_KEY` / `ZECTRIX_DEVICE_ID`（可选）

## 典型用法示例

- 「把待办『买牛奶』推到小铁吧第 2 页」→ `create_todo` + `push_structured_text`
- 「显示一段会议提醒」→ `push_structured_text(title="会议提醒", body="15:00 三楼会议室\n带笔记本", page_id="1")`
- 「清空第 3 页」→ `clear_pages(page_id="3")`
- 「把一段话排版成图片显示」→ `push_text_image(title="今日待办", text="1. 买牛奶\n2. 开会 15:00", page_id="2")`

## 说明

- 图片推送要求本地文件路径（stdio 模式下 MCP server 与客户端同机运行）
- 单张图片 >2MB 或超过 5 张会被拒绝
- 设备同步周期仅允许 `0 / 10 / 30 / 60 / 180 / 720` 分钟
- `push_text_image` 依赖 Pillow 与系统中文字体（苹方 / Noto Sans CJK / 微软雅黑等），跨平台自动探测，无需手动配置字体路径
