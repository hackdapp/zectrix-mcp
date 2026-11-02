#!/usr/bin/env python3
"""
ZECTRIX NOTE4 智能墨水屏便签 — MCP Server
==========================================
通过 ZECTRIX 极趣云平台 Open API 控制墨水屏设备：
设备管理 / 待办事项 / 文本与图片推送 / 页面管理。

环境变量:
  ZECTRIX_API_KEY   (必填) API Key，形如 zt_xxx，在 cloud.zectrix.com 开放 API 页创建
  ZECTRIX_DEVICE_ID (可选) 默认设备 ID（MAC 地址），单设备场景免传参数
  ZECTRIX_BASE_URL  (可选) 云平台基础地址，默认 https://cloud.zectrix.com

运行:
  ZECTRIX_API_KEY=zt_xxx .venv/bin/python server.py
"""

import io
import logging
import os
import re
import sys
import tempfile
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

# stdio 模式下 stdout 是 MCP 协议通道，日志必须走 stderr
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(levelname)s %(name)s: %(message)s",
)
LOGGER = logging.getLogger("zectrix-mcp")


def _load_dotenv(path: str) -> None:
    """极简 .env 加载器（无第三方依赖）。

    只设置当前环境中不存在的变量，因此客户端配置传入的环境变量优先；
    文件不存在或行格式非法时静默跳过。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except FileNotFoundError:
        pass


# 优先读真实环境变量（客户端配置传入）；否则自动加载 server.py 同目录的 .env
_load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

API_KEY = os.environ.get("ZECTRIX_API_KEY", "").strip()
DEFAULT_DEVICE_ID = os.environ.get("ZECTRIX_DEVICE_ID", "").strip()
BASE_URL = os.environ.get("ZECTRIX_BASE_URL", "https://cloud.zectrix.com").rstrip("/")

mcp = FastMCP("zectrix")

if not API_KEY:
    LOGGER.warning("未检测到 ZECTRIX_API_KEY，工具调用将失败；请在 .env 或客户端 env 中配置")

# ---------------------------------------------------------------- 常量与参数校验

SYNC_INTERVALS = {0, 10, 30, 60, 180, 720}
REPEAT_TYPES = {"daily", "weekly", "monthly", "yearly", "none"}
PRIORITIES = {0, 1, 2}
MAX_TEXT_LEN = 5000
MAX_TITLE_LEN = 200
FONT_SIZE_RANGE = (12, 48)
PAGE_IDS = {"1", "2", "3", "4", "5"}
RENDER_WIDTH = 400
RENDER_HEIGHT = 300
# 跨平台常见中文字体路径（公开系统路径，非本机隐私路径）
FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
]


def _validate_page_id(page_id: str) -> None:
    if page_id not in PAGE_IDS:
        raise ValueError(f"pageId 仅允许 1-5，收到: {page_id!r}")


def _validate_date(value: str, label: str) -> None:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{label} 格式应为 yyyy-MM-dd，收到: {value!r}")


def _validate_time(value: str, label: str) -> None:
    if not re.fullmatch(r"\d{2}:\d{2}", value):
        raise ValueError(f"{label} 格式应为 HH:mm，收到: {value!r}")


# ---------------------------------------------------------------- 基础设施

def _client() -> httpx.Client:
    if not API_KEY:
        raise ValueError("缺少环境变量 ZECTRIX_API_KEY（形如 zt_xxx）")
    return httpx.Client(
        base_url=f"{BASE_URL}/open/v1",
        headers={"X-API-Key": API_KEY},
        timeout=30.0,
    )


def _ensure_device(device_id: Optional[str]) -> str:
    device_id = (device_id or DEFAULT_DEVICE_ID).strip()
    if not device_id:
        raise ValueError("未提供 deviceId，且未设置 ZECTRIX_DEVICE_ID 环境变量")
    return device_id


def _parse_response(resp: httpx.Response) -> dict[str, Any]:
    """校验 HTTP 状态码、解析 JSON 并检查业务错误码，返回完整响应体。"""
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
    try:
        payload = resp.json()
    except Exception:
        raise RuntimeError(f"响应不是合法 JSON: {resp.text[:500]}")
    if not isinstance(payload, dict) or payload.get("code") != 0:
        raise RuntimeError(f"API 错误 code={payload.get('code') if isinstance(payload, dict) else '?'}: "
                           f"{payload.get('msg') if isinstance(payload, dict) else payload}")
    return payload


def _request(method: str, path: str, **kwargs) -> dict[str, Any]:
    """发起请求并复用 _parse_response，返回完整响应体。"""
    with _client() as c:
        resp = c.request(method, path, **kwargs)
    return _parse_response(resp)


def _out(payload: dict[str, Any]) -> Any:
    """取出 data 字段返回（结构化对象，MCP 客户端拿到 JSON 而非字符串）。"""
    return payload.get("data") if "data" in payload else payload


# ---------------------------------------------------------------- 设备管理

@mcp.tool()
def list_devices() -> Any:
    """获取当前账号下已绑定的墨水屏设备列表（deviceId / alias / board）。"""
    return _out(_request("GET", "/devices"))


@mcp.tool()
def set_sync_interval(device_id: Optional[str] = None, sync_interval: int = 60) -> Any:
    """修改设备与云端的同步周期（分钟）。仅允许 0(关闭) / 10 / 30 / 60 / 180 / 720。"""
    if sync_interval not in SYNC_INTERVALS:
        raise ValueError(f"syncInterval 仅允许 {sorted(SYNC_INTERVALS)}，收到: {sync_interval}")
    device_id = _ensure_device(device_id)
    return _out(_request("PUT", f"/devices/{device_id}/sync-interval",
                         json={"syncInterval": sync_interval}))


# ---------------------------------------------------------------- 待办事项

@mcp.tool()
def list_todos(status: Optional[int] = None, device_id: Optional[str] = None) -> Any:
    """获取待办列表。status: 0=待完成, 1=已完成；device_id 为空则返回全部设备待办。"""
    if status is not None and status not in (0, 1):
        raise ValueError(f"status 仅允许 0/1，收到: {status}")
    params: dict[str, Any] = {}
    if status is not None:
        params["status"] = status
    if device_id:
        params["deviceId"] = device_id
    return _out(_request("GET", "/todos", params=params))


@mcp.tool()
def create_todo(
    title: str,
    description: Optional[str] = None,
    due_date: Optional[str] = None,
    due_time: Optional[str] = None,
    repeat_type: Optional[str] = None,
    repeat_weekday: Optional[int] = None,
    repeat_month: Optional[int] = None,
    repeat_day: Optional[int] = None,
    priority: Optional[int] = None,
    device_id: Optional[str] = None,
) -> Any:
    """创建待办。
    title 必填；dueDate 格式 yyyy-MM-dd；dueTime 格式 HH:mm；
    repeatType: daily/weekly/monthly/yearly/none（weekly 用 repeatWeekday 0-6，yearly 用 repeatMonth 1-12，
    monthly/yearly 用 repeatDay 1-31）；priority: 0普通/1重要/2紧急；
    deviceId 未指定时默认绑定 ZECTRIX_DEVICE_ID 配置的设备；两者都未设置则创建为个人待办（不绑设备）。"""
    if priority is not None and priority not in PRIORITIES:
        raise ValueError(f"priority 仅允许 {sorted(PRIORITIES)}，收到: {priority}")
    if repeat_type is not None and repeat_type not in REPEAT_TYPES:
        raise ValueError(f"repeatType 仅允许 {sorted(REPEAT_TYPES)}，收到: {repeat_type}")
    if due_date:
        _validate_date(due_date, "dueDate")
    if due_time:
        _validate_time(due_time, "dueTime")
    body: dict[str, Any] = {"title": title}
    for key, val in {
        "description": description, "dueDate": due_date, "dueTime": due_time,
        "repeatType": repeat_type, "repeatWeekday": repeat_weekday,
        "repeatMonth": repeat_month, "repeatDay": repeat_day, "priority": priority,
    }.items():
        if val is not None:
            body[key] = val
    resolved_device = (device_id or DEFAULT_DEVICE_ID).strip()
    if resolved_device:
        body["deviceId"] = resolved_device
    return _out(_request("POST", "/todos", json=body))


@mcp.tool()
def update_todo(
    todo_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    due_date: Optional[str] = None,
    due_time: Optional[str] = None,
    priority: Optional[int] = None,
) -> Any:
    """更新待办的部分字段（传入的字段才会被修改）。dueDate 格式 yyyy-MM-dd；dueTime 格式 HH:mm；priority: 0/1/2。"""
    if priority is not None and priority not in PRIORITIES:
        raise ValueError(f"priority 仅允许 {sorted(PRIORITIES)}，收到: {priority}")
    if due_date:
        _validate_date(due_date, "dueDate")
    if due_time:
        _validate_time(due_time, "dueTime")
    body: dict[str, Any] = {}
    for key, val in {
        "title": title, "description": description,
        "dueDate": due_date, "dueTime": due_time, "priority": priority,
    }.items():
        if val is not None:
            body[key] = val
    if not body:
        raise ValueError("至少提供一个要更新的字段")
    return _out(_request("PUT", f"/todos/{todo_id}", json=body))


@mcp.tool()
def set_todo_completed(todo_id: int, completed: bool = True) -> Any:
    """标记待办完成（completed=true）或取消完成（completed=false）。"""
    return _out(_request("PUT", f"/todos/{todo_id}/complete", json={"completed": completed}))


@mcp.tool()
def delete_todo(todo_id: int) -> Any:
    """按 ID 删除待办。"""
    return _out(_request("DELETE", f"/todos/{todo_id}"))


# ---------------------------------------------------------------- 显示推送

@mcp.tool()
def push_text(
    text: str,
    device_id: Optional[str] = None,
    font_size: int = 20,
    page_id: Optional[str] = None,
) -> Any:
    """推送纯文本到墨水屏。text 最多 5000 字、支持换行；fontSize 12-48，默认 20；
    pageId 1-5，指定后内容会持久化存储到该页。"""
    if not text.strip():
        raise ValueError("text 不能为空")
    if len(text) > MAX_TEXT_LEN:
        raise ValueError(f"text 最多 {MAX_TEXT_LEN} 字，当前 {len(text)} 字")
    if not (FONT_SIZE_RANGE[0] <= font_size <= FONT_SIZE_RANGE[1]):
        raise ValueError(f"fontSize 仅允许 {FONT_SIZE_RANGE[0]}-{FONT_SIZE_RANGE[1]}，收到: {font_size}")
    device_id = _ensure_device(device_id)
    body: dict[str, Any] = {"text": text, "fontSize": font_size}
    if page_id:
        _validate_page_id(page_id)
        body["pageId"] = page_id
    return _out(_request("POST", f"/devices/{device_id}/display/text", json=body))


@mcp.tool()
def push_structured_text(
    title: Optional[str] = None,
    body: Optional[str] = None,
    device_id: Optional[str] = None,
    page_id: Optional[str] = None,
) -> Any:
    """推送标题+正文到墨水屏。title 最多 200 字，body 最多 5000 字（title 与 body 至少填一项）；
    pageId 1-5，指定后内容会持久化存储到该页。"""
    if not title and not body:
        raise ValueError("title 与 body 至少填写一项")
    if title and len(title) > MAX_TITLE_LEN:
        raise ValueError(f"title 最多 {MAX_TITLE_LEN} 字，当前 {len(title)} 字")
    if body and len(body) > MAX_TEXT_LEN:
        raise ValueError(f"body 最多 {MAX_TEXT_LEN} 字，当前 {len(body)} 字")
    device_id = _ensure_device(device_id)
    payload: dict[str, Any] = {}
    if title:
        payload["title"] = title
    if body:
        payload["body"] = body
    if page_id:
        _validate_page_id(page_id)
        payload["pageId"] = page_id
    return _out(_request("POST", f"/devices/{device_id}/display/structured-text", json=payload))


def _upload_images(device_id: str, image_paths: list[str], dither: bool, page_id: Optional[str]) -> dict[str, Any]:
    """内部：multipart 上传图片到设备，返回完整响应体（调用方负责校验入参）。"""
    handles: list[tuple[str, tuple[str, Any, str]]] = []
    try:
        for p in image_paths:
            handles.append(("images", (os.path.basename(p), open(p, "rb"), "application/octet-stream")))
        data_field: dict[str, str] = {"dither": "true" if dither else "false"}
        if page_id:
            data_field["pageId"] = page_id
        with _client() as c:
            resp = c.post(f"/devices/{device_id}/display/image", data=data_field, files=handles)
        return _parse_response(resp)
    finally:
        for item in handles:
            item[1][1].close()


@mcp.tool()
def push_image(
    image_paths: list[str],
    device_id: Optional[str] = None,
    dither: bool = True,
    page_id: Optional[str] = None,
) -> Any:
    """推送本地图片到墨水屏（400x300 黑白，自动缩放）。image_paths 为本地文件绝对路径列表，
    最多 5 张、单张不超过 2MB；dither=true 使用抖动算法（默认），false 为硬阈值二值化；
    pageId 1-5，指定后持久化存储。"""
    device_id = _ensure_device(device_id)
    if not image_paths:
        raise ValueError("image_paths 不能为空")
    if len(image_paths) > 5:
        raise ValueError("最多支持 5 张图片")
    for p in image_paths:
        if not os.path.isfile(p):
            raise ValueError(f"文件不存在: {p}")
        if os.path.getsize(p) > 2 * 1024 * 1024:
            raise ValueError(f"图片超过 2MB 限制: {p}")
    if page_id:
        _validate_page_id(page_id)
    return _out(_upload_images(device_id, image_paths, dither, page_id))


def _find_font() -> Optional[str]:
    """跨平台探测可用的中文字体，返回第一个存在的路径。"""
    for p in FONT_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def _draw_wrapped(draw, text: str, font, y: int, max_lines: Optional[int] = None) -> int:
    """在画布上自动换行绘制文本，返回下一行 y 坐标。"""
    x0, max_width = 8, RENDER_WIDTH - 16
    line_height = font.size + 4
    lines: list[str] = []
    for raw_line in text.split("\n"):
        if not raw_line:
            lines.append("")
            continue
        current = ""
        for ch in raw_line:
            if draw.textlength(current + ch, font=font) <= max_width:
                current += ch
            else:
                lines.append(current)
                current = ch
        lines.append(current)
    if max_lines is not None:
        lines = lines[:max_lines]
    for line in lines:
        if y + line_height > RENDER_HEIGHT:
            break
        draw.text((x0, y), line, font=font, fill=0)
        y += line_height
    return y


def _render_text_image(title: Optional[str], text: str, font_size: int) -> bytes:
    """将文本渲染为 400x300 黑白 PNG，返回图片字节。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as e:
        raise RuntimeError("缺少 Pillow 依赖，无法渲染文本图片；请执行: pip install Pillow") from e
    font_path = _find_font()
    if not font_path:
        raise RuntimeError("未找到可用的中文字体（Noto Sans CJK / 苹方 / 微软雅黑 等）")

    img = Image.new("L", (RENDER_WIDTH, RENDER_HEIGHT), 255)
    draw = ImageDraw.Draw(img)
    title_font = ImageFont.truetype(font_path, min(font_size + 6, 48))
    body_font = ImageFont.truetype(font_path, font_size)

    y = 6
    if title:
        y = _draw_wrapped(draw, title, title_font, y, max_lines=2)
        draw.line([(8, y + 2), (RENDER_WIDTH - 8, y + 2)], fill=0)
        y += 8
    _draw_wrapped(draw, text, body_font, y)

    img = img.point(lambda p: 0 if p < 128 else 255, "1")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@mcp.tool()
def push_text_image(
    text: str,
    title: Optional[str] = None,
    device_id: Optional[str] = None,
    font_size: int = 24,
    page_id: Optional[str] = None,
) -> Any:
    """将多行文本渲染为 400x300 黑白图片推送到墨水屏（排版比 push_text 更可控，支持标题与分隔线）。
    text 最多 5000 字、title 最多 200 字；fontSize 12-48；pageId 1-5 指定后持久化存储。"""
    if not text.strip():
        raise ValueError("text 不能为空")
    if len(text) > MAX_TEXT_LEN:
        raise ValueError(f"text 最多 {MAX_TEXT_LEN} 字，当前 {len(text)} 字")
    if title and len(title) > MAX_TITLE_LEN:
        raise ValueError(f"title 最多 {MAX_TITLE_LEN} 字，当前 {len(title)} 字")
    if not (FONT_SIZE_RANGE[0] <= font_size <= FONT_SIZE_RANGE[1]):
        raise ValueError(f"fontSize 仅允许 {FONT_SIZE_RANGE[0]}-{FONT_SIZE_RANGE[1]}，收到: {font_size}")
    if page_id:
        _validate_page_id(page_id)
    device_id = _ensure_device(device_id)

    png_bytes = _render_text_image(title, text, font_size)
    fd, tmp_path = tempfile.mkstemp(suffix=".png")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(png_bytes)
        return _out(_upload_images(device_id, [tmp_path], dither=True, page_id=page_id))
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@mcp.tool()
def clear_pages(device_id: Optional[str] = None, page_id: Optional[str] = None) -> Any:
    """删除设备页面。pageId 指定 1-5 删除单页；不传 pageId 则清空该设备全部页面。"""
    device_id = _ensure_device(device_id)
    if page_id:
        _validate_page_id(page_id)
    path = f"/devices/{device_id}/display/pages/{page_id}" if page_id else f"/devices/{device_id}/display/pages"
    return _out(_request("DELETE", path))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
