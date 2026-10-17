# ============================================================
# 意图识别回复文案测试：教学知识库场景文案回归保护
# ============================================================

from app.rag.query_processor.intent_recognition import (
    get_greeting_response,
    get_rejected_response,
)


class TestIntentResponses:
    def test_greeting_mentions_kb_assistant(self):
        resp = get_greeting_response("你好")
        assert "人工智能学院教学知识库" in resp
        assert "ESP32" in resp and "树莓派" in resp

    def test_greeting_default(self):
        resp = get_greeting_response("在吗")
        assert "嵌入式开发" in resp

    def test_greeting_thanks(self):
        resp = get_greeting_response("谢谢")
        assert "技术资料" in resp

    def test_rejected_mentions_kb(self):
        resp = get_rejected_response()
        assert "技术资料检索" in resp
        assert "重新提问" in resp
