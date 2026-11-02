"""pytest 测试套件：覆盖 server.py 各工具的校验、成功与错误路径。

所有测试不依赖真实 API Key 或网络：
- 通过 monkeypatch 替换 server._request / server._client；
- 显式传 device_id 绕开默认设备。
"""

import os

import httpx
import pytest

import server


# ---------------------------------------------------------------- 测试辅助

def patch_request(monkeypatch, response=None):
    """替换 server._request，返回记录每次调用参数的列表。"""
    calls = []

    def fake(method, path, **kwargs):
        calls.append({"method": method, "path": path, **kwargs})
        return response if response is not None else {"code": 0, "data": {"ok": True}}

    monkeypatch.setattr(server, "_request", fake)
    return calls


# ---------------------------------------------------------------- 参数校验

class TestValidatePageId:
    def test_valid(self):
        for page_id in ("1", "2", "3", "4", "5"):
            server._validate_page_id(page_id)  # 不抛异常

    @pytest.mark.parametrize("page_id", ["0", "6", "", "01", "abc", None])
    def test_invalid(self, page_id):
        with pytest.raises(ValueError, match="pageId"):
            server._validate_page_id(page_id)


class TestValidateDate:
    @pytest.mark.parametrize("value", ["2025-01-01", "1999-12-31", "0000-00-00"])
    def test_valid(self, value):
        server._validate_date(value, "dueDate")

    @pytest.mark.parametrize("value", ["2025-1-1", "01/01/2025", "2025/01/01", "2025-01-1", "not-a-date", ""])
    def test_invalid(self, value):
        with pytest.raises(ValueError, match="yyyy-MM-dd"):
            server._validate_date(value, "dueDate")


class TestValidateTime:
    @pytest.mark.parametrize("value", ["00:00", "09:30", "23:59"])
    def test_valid(self, value):
        server._validate_time(value, "dueTime")

    @pytest.mark.parametrize("value", ["9:30", "0930", "09:60:00", "2400", "noon", ""])
    def test_invalid(self, value):
        with pytest.raises(ValueError, match="HH:mm"):
            server._validate_time(value, "dueTime")


# ---------------------------------------------------------------- 工具参数校验（ValueError）

class TestSetSyncIntervalValidation:
    @pytest.mark.parametrize("interval", [0, 10, 30, 60, 180, 720])
    def test_valid_values(self, monkeypatch, interval):
        calls = patch_request(monkeypatch)
        result = server.set_sync_interval(device_id="DEV1", sync_interval=interval)
        assert result == {"ok": True}
        assert calls[0]["path"] == "/devices/DEV1/sync-interval"
        assert calls[0]["json"] == {"syncInterval": interval}

    @pytest.mark.parametrize("interval", [-1, 1, 5, 15, 45, 90, 360, 1440])
    def test_invalid_values(self, interval):
        with pytest.raises(ValueError, match="syncInterval"):
            server.set_sync_interval(device_id="DEV1", sync_interval=interval)


class TestListTodosValidation:
    @pytest.mark.parametrize("status", [0, 1, None])
    def test_valid_status(self, monkeypatch, status):
        calls = patch_request(monkeypatch)
        server.list_todos(status=status, device_id="DEV1")
        assert calls[0]["path"] == "/todos"

    @pytest.mark.parametrize("status", [-1, 2, 99])
    def test_invalid_status(self, status):
        with pytest.raises(ValueError, match="status"):
            server.list_todos(status=status)


class TestCreateTodoValidation:
    @pytest.mark.parametrize("priority", [-1, 3, 99])
    def test_invalid_priority(self, priority):
        with pytest.raises(ValueError, match="priority"):
            server.create_todo("标题", priority=priority)

    @pytest.mark.parametrize("repeat_type", ["hourly", "biweekly", "DAILY", "every day"])
    def test_invalid_repeat_type(self, repeat_type):
        with pytest.raises(ValueError, match="repeatType"):
            server.create_todo("标题", repeat_type=repeat_type)

    @pytest.mark.parametrize("due_date", ["2025-1-1", "01/01/2025", "abc"])
    def test_invalid_due_date(self, due_date):
        with pytest.raises(ValueError, match="yyyy-MM-dd"):
            server.create_todo("标题", due_date=due_date)

    @pytest.mark.parametrize("due_time", ["9:00", "0900", "09:30:00"])
    def test_invalid_due_time(self, due_time):
        with pytest.raises(ValueError, match="HH:mm"):
            server.create_todo("标题", due_time=due_time)


class TestUpdateTodoValidation:
    def test_invalid_priority(self):
        with pytest.raises(ValueError, match="priority"):
            server.update_todo(1, priority=5)

    def test_invalid_due_date(self):
        with pytest.raises(ValueError, match="yyyy-MM-dd"):
            server.update_todo(1, due_date="2025/01/01")

    def test_invalid_due_time(self):
        with pytest.raises(ValueError, match="HH:mm"):
            server.update_todo(1, due_time="9:00")

    def test_empty_body(self):
        with pytest.raises(ValueError, match="至少提供"):
            server.update_todo(1)


class TestPushTextValidation:
    def test_empty_text(self):
        with pytest.raises(ValueError, match="不能为空"):
            server.push_text("   ", device_id="DEV1")

    def test_text_too_long(self):
        with pytest.raises(ValueError, match="最多 5000"):
            server.push_text("x" * 5001, device_id="DEV1")

    @pytest.mark.parametrize("font_size", [11, 49, 0, 100])
    def test_invalid_font_size(self, font_size):
        with pytest.raises(ValueError, match="fontSize"):
            server.push_text("hello", device_id="DEV1", font_size=font_size)

    def test_invalid_page_id(self):
        with pytest.raises(ValueError, match="pageId"):
            server.push_text("hello", device_id="DEV1", page_id="6")


class TestPushStructuredTextValidation:
    def test_both_empty(self):
        with pytest.raises(ValueError, match="至少"):
            server.push_structured_text(device_id="DEV1")

    def test_title_too_long(self):
        with pytest.raises(ValueError, match="title 最多 200"):
            server.push_structured_text(title="x" * 201, device_id="DEV1")

    def test_body_too_long(self):
        with pytest.raises(ValueError, match="body 最多 5000"):
            server.push_structured_text(body="x" * 5001, device_id="DEV1")

    def test_invalid_page_id(self):
        with pytest.raises(ValueError, match="pageId"):
            server.push_structured_text(title="hello", device_id="DEV1", page_id="0")


class TestPushImageValidation:
    def test_empty_list(self):
        with pytest.raises(ValueError, match="不能为空"):
            server.push_image([], device_id="DEV1")

    def test_too_many(self):
        with pytest.raises(ValueError, match="最多支持 5"):
            server.push_image(["a", "b", "c", "d", "e", "f"], device_id="DEV1")

    def test_file_not_found(self, tmp_path):
        with pytest.raises(ValueError, match="文件不存在"):
            server.push_image([str(tmp_path / "missing.png")], device_id="DEV1")

    def test_file_too_large(self, tmp_path):
        big = tmp_path / "big.png"
        big.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
        with pytest.raises(ValueError, match="超过 2MB"):
            server.push_image([str(big)], device_id="DEV1")


class TestClearPagesValidation:
    @pytest.mark.parametrize("page_id", ["0", "6", "abc"])
    def test_invalid_page_id(self, page_id):
        with pytest.raises(ValueError, match="pageId"):
            server.clear_pages(device_id="DEV1", page_id=page_id)


# ---------------------------------------------------------------- 成功路径

class TestListDevicesSuccess:
    def test_success(self, monkeypatch):
        calls = patch_request(monkeypatch, response={"code": 0, "data": [{"deviceId": "DEV1"}]})
        result = server.list_devices()
        assert result == [{"deviceId": "DEV1"}]
        assert calls[0] == {"method": "GET", "path": "/devices"}


class TestSetSyncIntervalSuccess:
    def test_success(self, monkeypatch):
        calls = patch_request(monkeypatch)
        result = server.set_sync_interval(device_id="DEV1", sync_interval=30)
        assert result == {"ok": True}
        assert calls[0]["method"] == "PUT"
        assert calls[0]["path"] == "/devices/DEV1/sync-interval"
        assert calls[0]["json"] == {"syncInterval": 30}


class TestListTodosSuccess:
    def test_success_with_status_and_device(self, monkeypatch):
        calls = patch_request(monkeypatch)
        server.list_todos(status=0, device_id="DEV1")
        assert calls[0]["method"] == "GET"
        assert calls[0]["path"] == "/todos"
        assert calls[0]["params"] == {"status": 0, "deviceId": "DEV1"}

    def test_success_without_params(self, monkeypatch):
        calls = patch_request(monkeypatch)
        server.list_todos()
        assert calls[0]["params"] == {}


class TestCreateTodoSuccess:
    def test_full_success(self, monkeypatch):
        calls = patch_request(monkeypatch)
        result = server.create_todo(
            "买菜",
            description="周末采购",
            due_date="2025-01-01",
            due_time="09:30",
            repeat_type="weekly",
            repeat_weekday=1,
            repeat_month=2,
            repeat_day=3,
            priority=1,
            device_id="DEV1",
        )
        assert result == {"ok": True}
        assert calls[0]["method"] == "POST"
        assert calls[0]["path"] == "/todos"
        assert calls[0]["json"] == {
            "title": "买菜",
            "description": "周末采购",
            "dueDate": "2025-01-01",
            "dueTime": "09:30",
            "repeatType": "weekly",
            "repeatWeekday": 1,
            "repeatMonth": 2,
            "repeatDay": 3,
            "priority": 1,
            "deviceId": "DEV1",
        }

    def test_minimal_success(self, monkeypatch):
        calls = patch_request(monkeypatch)
        server.create_todo("标题")
        assert calls[0]["json"] == {"title": "标题"}


class TestUpdateTodoSuccess:
    def test_success(self, monkeypatch):
        calls = patch_request(monkeypatch)
        result = server.update_todo(42, title="新标题", priority=2)
        assert result == {"ok": True}
        assert calls[0]["method"] == "PUT"
        assert calls[0]["path"] == "/todos/42"
        assert calls[0]["json"] == {"title": "新标题", "priority": 2}


class TestSetTodoCompletedSuccess:
    @pytest.mark.parametrize("completed", [True, False])
    def test_success(self, monkeypatch, completed):
        calls = patch_request(monkeypatch)
        server.set_todo_completed(7, completed=completed)
        assert calls[0]["method"] == "PUT"
        assert calls[0]["path"] == "/todos/7/complete"
        assert calls[0]["json"] == {"completed": completed}


class TestDeleteTodoSuccess:
    def test_success(self, monkeypatch):
        calls = patch_request(monkeypatch)
        server.delete_todo(9)
        assert calls[0]["method"] == "DELETE"
        assert calls[0]["path"] == "/todos/9"


class TestPushTextSuccess:
    def test_success(self, monkeypatch):
        calls = patch_request(monkeypatch)
        result = server.push_text("hello", device_id="DEV1", font_size=20, page_id="1")
        assert result == {"ok": True}
        assert calls[0]["method"] == "POST"
        assert calls[0]["path"] == "/devices/DEV1/display/text"
        assert calls[0]["json"] == {"text": "hello", "fontSize": 20, "pageId": "1"}

    def test_boundary_font_size_and_text_length(self, monkeypatch):
        calls = patch_request(monkeypatch)
        server.push_text("x" * 5000, device_id="DEV1", font_size=12)
        assert calls[0]["json"]["fontSize"] == 12
        assert len(calls[0]["json"]["text"]) == 5000


class TestPushStructuredTextSuccess:
    def test_success(self, monkeypatch):
        calls = patch_request(monkeypatch)
        result = server.push_structured_text(title="标题", body="正文", device_id="DEV1", page_id="3")
        assert result == {"ok": True}
        assert calls[0]["method"] == "POST"
        assert calls[0]["path"] == "/devices/DEV1/display/structured-text"
        assert calls[0]["json"] == {"title": "标题", "body": "正文", "pageId": "3"}

    def test_body_only(self, monkeypatch):
        calls = patch_request(monkeypatch)
        server.push_structured_text(body="只有正文", device_id="DEV1")
        assert calls[0]["json"] == {"body": "只有正文"}


class TestPushImageSuccess:
    def test_success(self, monkeypatch, tmp_path):
        img = tmp_path / "photo.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 100)
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["path"] = request.url.path
            captured["content"] = request.content
            return httpx.Response(200, json={"code": 0, "data": {"pushed": True}})

        client = httpx.Client(
            base_url="https://cloud.zectrix.com/open/v1",
            transport=httpx.MockTransport(handler),
        )
        monkeypatch.setattr(server, "_client", lambda: client)

        result = server.push_image([str(img)], device_id="DEV1", dither=True, page_id="1")
        assert result == {"pushed": True}
        assert captured["method"] == "POST"
        assert captured["path"] == "/open/v1/devices/DEV1/display/image"
        assert b'name="dither"' in captured["content"]
        assert b"photo.png" in captured["content"]


class TestClearPagesSuccess:
    def test_single_page(self, monkeypatch):
        calls = patch_request(monkeypatch)
        server.clear_pages(device_id="DEV1", page_id="2")
        assert calls[0]["method"] == "DELETE"
        assert calls[0]["path"] == "/devices/DEV1/display/pages/2"

    def test_all_pages(self, monkeypatch):
        calls = patch_request(monkeypatch)
        server.clear_pages(device_id="DEV1")
        assert calls[0]["method"] == "DELETE"
        assert calls[0]["path"] == "/devices/DEV1/display/pages"


# ---------------------------------------------------------------- _request / _client 错误路径

class TestRequestErrorHandling:
    def test_http_error(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, text="bad request")

        client = httpx.Client(
            base_url="https://cloud.zectrix.com/open/v1",
            transport=httpx.MockTransport(handler),
        )
        monkeypatch.setattr(server, "_client", lambda: client)
        with pytest.raises(RuntimeError, match="HTTP 400"):
            server._request("GET", "/devices")

    def test_non_json_response(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<html>not json</html>")

        client = httpx.Client(
            base_url="https://cloud.zectrix.com/open/v1",
            transport=httpx.MockTransport(handler),
        )
        monkeypatch.setattr(server, "_client", lambda: client)
        with pytest.raises(RuntimeError, match="不是合法 JSON"):
            server._request("GET", "/devices")

    def test_business_error_code(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"code": 1001, "msg": "设备不存在"})

        client = httpx.Client(
            base_url="https://cloud.zectrix.com/open/v1",
            transport=httpx.MockTransport(handler),
        )
        monkeypatch.setattr(server, "_client", lambda: client)
        with pytest.raises(RuntimeError, match="API 错误 code=1001"):
            server._request("GET", "/devices")


class TestClientAndDevice:
    def test_client_missing_api_key(self, monkeypatch):
        monkeypatch.setattr(server, "API_KEY", "")
        with pytest.raises(ValueError, match="ZECTRIX_API_KEY"):
            server._client()

    def test_ensure_device_missing(self, monkeypatch):
        monkeypatch.setattr(server, "DEFAULT_DEVICE_ID", "")
        with pytest.raises(ValueError, match="deviceId"):
            server._ensure_device(None)

    def test_ensure_device_strips(self, monkeypatch):
        monkeypatch.setattr(server, "DEFAULT_DEVICE_ID", "")
        assert server._ensure_device("  DEV1  ") == "DEV1"


# ---------------------------------------------------------------- _load_dotenv

class TestLoadDotenv:
    def test_sets_new_vars(self, tmp_path, monkeypatch):
        dotenv = tmp_path / ".env"
        dotenv.write_text('FOO=bar\nBAZ="qux"\n', encoding="utf-8")
        monkeypatch.delenv("FOO", raising=False)
        monkeypatch.delenv("BAZ", raising=False)

        server._load_dotenv(str(dotenv))

        assert os.environ.get("FOO") == "bar"
        assert os.environ.get("BAZ") == "qux"

    def test_does_not_override_existing(self, tmp_path, monkeypatch):
        dotenv = tmp_path / ".env"
        dotenv.write_text("EXISTING=overwritten\n", encoding="utf-8")
        monkeypatch.setenv("EXISTING", "original")

        server._load_dotenv(str(dotenv))

        assert os.environ.get("EXISTING") == "original"

    def test_missing_file_no_error(self, tmp_path):
        server._load_dotenv(str(tmp_path / "nope.env"))  # 不抛异常

    def test_skips_invalid_lines(self, tmp_path, monkeypatch):
        dotenv = tmp_path / ".env"
        dotenv.write_text("# comment\nNO_EQUALS\nEMPTY=\nVALID=yes\n", encoding="utf-8")
        monkeypatch.delenv("VALID", raising=False)
        monkeypatch.delenv("EMPTY", raising=False)

        server._load_dotenv(str(dotenv))

        assert os.environ.get("VALID") == "yes"
        assert "NO_EQUALS" not in os.environ
        # 空值行有 "=" 号，会被当作空字符串写入
        assert os.environ.get("EMPTY") == ""


# ---------------------------------------------------------------- 文本→图片渲染（改进 4）

class TestPushTextImageValidation:
    def test_empty_text(self):
        with pytest.raises(ValueError, match="不能为空"):
            server.push_text_image("   ", device_id="DEV1")

    def test_text_too_long(self):
        with pytest.raises(ValueError, match="最多 5000"):
            server.push_text_image("x" * 5001, device_id="DEV1")

    def test_title_too_long(self):
        with pytest.raises(ValueError, match="title 最多 200"):
            server.push_text_image("hi", title="x" * 201, device_id="DEV1")

    @pytest.mark.parametrize("font_size", [11, 49, 0, 100])
    def test_invalid_font_size(self, font_size):
        with pytest.raises(ValueError, match="fontSize"):
            server.push_text_image("hi", device_id="DEV1", font_size=font_size)

    def test_invalid_page_id(self):
        with pytest.raises(ValueError, match="pageId"):
            server.push_text_image("hi", device_id="DEV1", page_id="0")


class TestRenderTextImage:
    def test_render_returns_png(self):
        pytest.importorskip("PIL")
        if server._find_font() is None:
            pytest.skip("系统无中文字体")
        png = server._render_text_image("标题", "正文\n第二行", 24)
        assert png.startswith(b"\x89PNG")
        assert len(png) > 0

    def test_find_font_type(self):
        font = server._find_font()
        assert font is None or os.path.isfile(font)


class TestPushTextImageSuccess:
    def test_success_and_temp_cleanup(self, monkeypatch):
        calls = []
        monkeypatch.setattr(server, "_render_text_image", lambda title, text, font_size: b"\x89PNG-fake")

        def fake_upload(device_id, image_paths, dither, page_id):
            calls.append({"device_id": device_id, "paths": list(image_paths), "dither": dither, "page_id": page_id})
            return {"code": 0, "data": {"pushed": True}}

        monkeypatch.setattr(server, "_upload_images", fake_upload)

        result = server.push_text_image("hello", title="标题", device_id="DEV1", page_id="1")

        assert result == {"pushed": True}
        assert calls[0]["device_id"] == "DEV1"
        assert calls[0]["dither"] is True
        assert calls[0]["page_id"] == "1"
        assert len(calls[0]["paths"]) == 1
        assert calls[0]["paths"][0].endswith(".png")
        # 临时文件已被清理
        assert not os.path.exists(calls[0]["paths"][0])
