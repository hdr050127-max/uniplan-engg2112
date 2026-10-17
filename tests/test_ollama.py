"""Which Ollama server answers: the configured one while it is up, this machine when it is not
(llm/ollama.py). No real server is contacted."""
import io
import json
import unittest
import urllib.error
from unittest import mock

from llm import ollama

REMOTE = "http://192.0.2.7:11434"


def reply(content: str) -> io.BytesIO:
    return io.BytesIO(json.dumps({"message": {"content": content}}).encode())


class ServerChoiceTests(unittest.TestCase):
    def setUp(self):
        ollama.base_url.cache_clear()
        patcher = mock.patch.dict("os.environ", {"UNIPLAN_OLLAMA_URL": REMOTE})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(ollama.base_url.cache_clear)

    def test_uses_the_configured_server_while_it_answers(self):
        with mock.patch.object(ollama, "_models", return_value={"m"}):
            self.assertEqual(ollama.base_url(), REMOTE)

    def test_falls_back_when_the_configured_server_is_down_at_start(self):
        with mock.patch.object(ollama, "_models", return_value=None):
            self.assertEqual(ollama.base_url(), ollama.LOCAL)

    def test_a_call_that_cannot_reach_the_server_is_retried_here(self):
        seen = []

        def urlopen(request, timeout):
            seen.append(request.full_url)
            if request.full_url.startswith(REMOTE):
                raise urllib.error.URLError(ConnectionRefusedError("refused"))
            return reply("blocked_time")

        with mock.patch.object(ollama, "_models", return_value={"m"}), \
                mock.patch("urllib.request.urlopen", side_effect=urlopen):
            self.assertEqual(ollama.base_url(), REMOTE)
            self.assertEqual(ollama.chat("m", []), "blocked_time")
            self.assertEqual(ollama.base_url(), ollama.LOCAL)       # stays here for the next calls
        self.assertEqual([url.split("/api")[0] for url in seen], [REMOTE, ollama.LOCAL])

    def test_an_error_answer_is_not_treated_as_the_server_being_down(self):
        def urlopen(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 404, "model not found", None, None)

        with mock.patch.object(ollama, "_models", return_value={"m"}), \
                mock.patch("urllib.request.urlopen", side_effect=urlopen):
            with self.assertRaises(urllib.error.HTTPError):
                ollama.chat("m", [])
            self.assertEqual(ollama.base_url(), REMOTE)

    def test_the_configured_server_is_used_again_once_it_is_back(self):
        with mock.patch.object(ollama, "_models", return_value=None):
            self.assertEqual(ollama.base_url(), ollama.LOCAL)
        with mock.patch.object(ollama, "_models", return_value={"m"}):
            self.assertEqual(ollama.base_url(), ollama.LOCAL)           # not re-checked within a minute
            with mock.patch.object(ollama.time, "monotonic", return_value=ollama.time.monotonic() + 61):
                self.assertEqual(ollama.base_url(), REMOTE)


if __name__ == "__main__":
    unittest.main()
