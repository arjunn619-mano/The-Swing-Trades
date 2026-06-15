from swing_trades.utils.alerts import send_telegram_alert


class _Resp:
    def __init__(self, status=200):
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")


def test_no_credentials_returns_false():
    assert send_telegram_alert("hi", bot_token=None, chat_id=None) is False


def test_sends_message_with_chat_and_text():
    captured = {}

    def post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _Resp(200)

    ok = send_telegram_alert("hello", bot_token="TOK", chat_id="CHAT", http_post=post)
    assert ok is True
    assert "botTOK" in captured["url"]
    assert captured["json"] == {"chat_id": "CHAT", "text": "hello"}


def test_http_error_returns_false_not_raises():
    def post(url, json=None, timeout=None):
        return _Resp(500)

    assert send_telegram_alert("x", bot_token="T", chat_id="C", http_post=post) is False
