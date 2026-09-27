import unittest

from adversarial_pipeline.llm_client import (
    AimeLiteLLMTransientError,
    _aime_litellm_payload_for_messages,
    _extract_aime_litellm_messages_text,
)


class AimeLiteLLMMessagesTest(unittest.TestCase):
    def test_converts_system_text_and_data_images(self):
        payload = {
            "model": "claude-opus-4-8",
            "max_output_tokens": 4096,
            "temperature": 0,
            "top_p": 1,
            "messages": [
                {"role": "system", "content": "Follow the task."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Inspect both images."},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,BBBB"}},
                    ],
                },
            ],
        }
        converted = _aime_litellm_payload_for_messages(payload)
        self.assertEqual(converted["model"], "claude-opus-4-8")
        self.assertEqual(converted["max_tokens"], 4096)
        self.assertNotIn("temperature", converted)
        self.assertNotIn("top_p", converted)
        self.assertEqual(converted["system"], [{"type": "text", "text": "Follow the task."}])
        content = converted["messages"][0]["content"]
        self.assertEqual(content[0], {"type": "text", "text": "Inspect both images."})
        self.assertEqual(content[1]["source"], {"type": "base64", "media_type": "image/png", "data": "AAAA"})
        self.assertEqual(content[2]["source"], {"type": "base64", "media_type": "image/jpeg", "data": "BBBB"})

    def test_extracts_messages_text(self):
        body = {"content": [{"type": "text", "text": "first"}, {"type": "text", "text": "second"}]}
        self.assertEqual(_extract_aime_litellm_messages_text(body), "first\nsecond")

    def test_rejects_empty_messages_content(self):
        with self.assertRaises(AimeLiteLLMTransientError):
            _extract_aime_litellm_messages_text({"content": []})


if __name__ == "__main__":
    unittest.main()
