import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_client import (
    ENV_PREFIX,
    FALLBACK_API_KEY_ENV,
    LLMClient,
    LLMConfig,
    LLMError,
    RequestCache,
    extract_json,
    mask_key,
)
from review_terms_llm import (
    Candidate,
    apply_gates,
    anchored,
    dry_run_transport,
    load_candidates,
    review,
    write_outputs,
)


def make_candidate(term="示例公司", category="org", evidence=None):
    return Candidate(
        term=term,
        code_category=category,
        bucket="HIGH",
        files=3,
        evidence=evidence if evidence is not None else [f"本公司由{term}持有，详见附件。"],
    )


class GateTest(unittest.TestCase):
    """四道闸门：结构 / 锚定 / 交叉 / 非对称权限。"""

    def test_keep_with_grounded_quote_is_accepted(self):
        cand = make_candidate()
        v = apply_gates(
            {"term": "示例公司", "action": "keep", "category": "org", "confidence": 0.9, "quote": "示例公司"},
            {cand.term: cand},
            0.6,
        )
        self.assertEqual(v.bucket, "accepted")
        self.assertEqual(v.gate, "通过")

    def test_term_not_in_batch_is_dropped(self):
        cand = make_candidate()
        v = apply_gates(
            {"term": "示例公司有限公司", "action": "keep", "category": "org", "confidence": 0.9, "quote": "示例公司"},
            {cand.term: cand},
            0.6,
        )
        self.assertEqual(v.bucket, "dropped")
        self.assertIn("结构闸门", v.gate)

    def test_invented_quote_is_dropped(self):
        cand = make_candidate()
        v = apply_gates(
            {"term": "示例公司", "action": "keep", "category": "org", "confidence": 0.9,
             "quote": "这句原文并不存在"},
            {cand.term: cand},
            0.6,
        )
        self.assertEqual(v.bucket, "dropped")
        self.assertIn("锚定闸门", v.gate)

    def test_quote_must_come_from_evidence(self):
        cand = make_candidate(evidence=["北京融侨置业有限公司（下称融侨公司）持有。"])
        grounded = apply_gates(
            {"term": "示例公司", "action": "keep", "category": "org", "confidence": 0.9,
             "quote": "下称融侨公司"},
            {cand.term: cand},
            0.6,
        )
        self.assertEqual(grounded.bucket, "accepted")

    def test_category_conflict_goes_manual(self):
        cand = make_candidate(category="org")
        v = apply_gates(
            {"term": "示例公司", "action": "keep", "category": "project", "confidence": 0.9, "quote": "示例公司"},
            {cand.term: cand},
            0.6,
        )
        self.assertEqual(v.bucket, "manual")
        self.assertIn("类别冲突", v.conflict)

    def test_veto_on_entity_like_term_is_escalated_not_deleted(self):
        cand = make_candidate(term="示例集团有限公司")
        v = apply_gates(
            {"term": "示例集团有限公司", "action": "veto", "category": None, "confidence": 0.9,
             "quote": "", "reason": "看起来像通用词"},
            {cand.term: cand},
            0.6,
        )
        self.assertEqual(v.bucket, "manual")
        self.assertEqual(v.action, "escalate")
        self.assertIn("非对称权限", v.conflict)

    def test_veto_on_generic_term_is_suggested(self):
        cand = make_candidate(term="公司")
        v = apply_gates(
            {"term": "公司", "action": "veto", "category": None, "confidence": 0.9, "quote": ""},
            {cand.term: cand},
            0.6,
        )
        self.assertEqual(v.bucket, "suggested_veto")

    def test_low_confidence_goes_manual(self):
        cand = make_candidate()
        v = apply_gates(
            {"term": "示例公司", "action": "keep", "category": "org", "confidence": 0.4, "quote": "示例公司"},
            {cand.term: cand},
            0.6,
        )
        self.assertEqual(v.bucket, "manual")
        self.assertIn("低于阈值", v.conflict)

    def test_invalid_action_and_category_are_dropped(self):
        cand = make_candidate()
        bad_action = apply_gates(
            {"term": "示例公司", "action": "delete", "category": "org", "confidence": 0.9, "quote": "示例公司"},
            {cand.term: cand}, 0.6,
        )
        self.assertEqual(bad_action.bucket, "dropped")
        bad_category = apply_gates(
            {"term": "示例公司", "action": "keep", "category": "person", "confidence": 0.9, "quote": "示例公司"},
            {cand.term: cand}, 0.6,
        )
        self.assertEqual(bad_category.bucket, "dropped")

    def test_non_dict_and_bad_confidence_are_dropped(self):
        cand = make_candidate()
        self.assertEqual(apply_gates("nope", {cand.term: cand}, 0.6).bucket, "dropped")
        self.assertEqual(
            apply_gates({"term": "示例公司", "action": "keep", "category": "org",
                         "confidence": "高", "quote": "示例公司"}, {cand.term: cand}, 0.6).bucket,
            "dropped",
        )
        self.assertEqual(
            apply_gates({"term": "示例公司", "action": "keep", "category": "org",
                         "confidence": 1.5, "quote": "示例公司"}, {cand.term: cand}, 0.6).bucket,
            "dropped",
        )


class AnchoringTest(unittest.TestCase):
    def test_anchor_normalizes_whitespace(self):
        cand = make_candidate(evidence=["本公司由 示例\n公司 持有"])
        self.assertTrue(anchored("示例公司", cand))
        self.assertTrue(anchored("本公司由示例公司持有", cand))
        self.assertFalse(anchored("别家公司", cand))

    def test_anchor_rejects_empty_quote(self):
        self.assertFalse(anchored("", make_candidate()))


class StubClientTest(unittest.TestCase):
    """调用层行为：缓存、重试、降级。"""

    def _config(self, cache_dir):
        return LLMConfig(endpoint="http://stub", model="stub-model", cache_dir=str(cache_dir))

    def test_cache_hit_avoids_second_call(self):
        calls = []

        def transport(config, system, user):
            calls.append(user)
            return json.dumps({"results": []})

        with tempfile.TemporaryDirectory() as tmp:
            client = LLMClient(self._config(tmp), cache=RequestCache(tmp), transport=transport)
            client.chat_json("s", "u")
            client.chat_json("s", "u")
            self.assertEqual(client.network_calls, 1)
            self.assertEqual(client.cache.hits, 1)

    def test_retry_then_success(self):
        attempts = {"n": 0}

        def transport(config, system, user):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise LLMError("临时失败")
            return '{"results": []}'

        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            config.max_retries = 2
            config.retry_backoff_seconds = 0
            client = LLMClient(config, cache=RequestCache(tmp), transport=transport)
            self.assertEqual(client.chat_json("s", "u"), {"results": []})
            self.assertEqual(attempts["n"], 2)

    def test_exhausted_retries_raise(self):
        def transport(config, system, user):
            raise LLMError("一直失败")

        with tempfile.TemporaryDirectory() as tmp:
            config = self._config(tmp)
            config.max_retries = 1
            config.retry_backoff_seconds = 0
            client = LLMClient(config, cache=RequestCache(tmp), transport=transport)
            with self.assertRaises(LLMError):
                client.chat_json("s", "u")

    def test_extract_json_tolerates_fences_and_prose(self):
        self.assertEqual(extract_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(extract_json('好的，结果如下：{"a": 1} 以上。'), {"a": 1})


class FakeClient:
    """review() 的最小桩：按 term 返回预设判定。"""

    def __init__(self, results, fail=False):
        self.results = results
        self.fail = fail

    def chat_json(self, system, user):
        if self.fail:
            raise LLMError("模拟失败")
        return {"results": self.results}


class ReviewFlowTest(unittest.TestCase):
    def test_call_failure_degrades_to_manual_without_losing_candidates(self):
        cands = [make_candidate(term=f"示例公司{i}") for i in range(3)]
        verdicts = review(cands, FakeClient([], fail=True), batch_size=2, min_confidence=0.6)
        self.assertEqual(len(verdicts), 3)
        self.assertTrue(all(v.bucket == "manual" for v in verdicts))
        self.assertTrue(all("调用失败" in v.gate for v in verdicts))

    def test_missing_result_becomes_manual(self):
        cands = [make_candidate(term="甲公司"), make_candidate(term="乙公司")]
        client = FakeClient([{"term": "甲公司", "action": "keep", "category": "org",
                              "confidence": 0.9, "quote": "甲公司"}])
        verdicts = review(cands, client, batch_size=5, min_confidence=0.6)
        buckets = {v.term: v.bucket for v in verdicts}
        self.assertEqual(buckets["甲公司"], "accepted")
        self.assertEqual(buckets["乙公司"], "manual")

    def test_dropped_result_is_not_counted_as_missing_again(self):
        """模型已答复但被闸门丢弃时，只应入库一次 dropped，不能再补一条漏答。"""
        cands = [make_candidate(term="甲公司")]
        client = FakeClient([{"term": "甲公司", "action": "keep", "category": "org",
                              "confidence": 0.9, "quote": "这段引文在原文中不存在"}])
        verdicts = review(cands, client, batch_size=5, min_confidence=0.6)
        self.assertEqual(len(verdicts), 1)
        self.assertEqual(verdicts[0].bucket, "dropped")
        self.assertIn("锚定闸门", verdicts[0].gate)

    def test_dry_run_end_to_end_intercepts_hallucination(self):
        cands = [make_candidate(term=f"示例实体{i:02d}有限公司") for i in range(6)]
        config = LLMConfig(endpoint="dry-run://local", model="stub")
        with tempfile.TemporaryDirectory() as tmp:
            client = LLMClient(config, cache=RequestCache(tmp), transport=dry_run_transport)
            verdicts = review(cands, client, batch_size=3, min_confidence=0.6)
        buckets = [v.bucket for v in verdicts]
        # 每批第 1 条是编造 term、第 2 条是锚定失败，必须被丢弃
        self.assertEqual(buckets.count("dropped"), 4)
        self.assertEqual(buckets.count("accepted"), 2)
        dropped_gates = [v.gate for v in verdicts if v.bucket == "dropped"]
        self.assertTrue(any("结构闸门" in g for g in dropped_gates))
        self.assertTrue(any("锚定闸门" in g for g in dropped_gates))


class OutputTest(unittest.TestCase):
    def test_outputs_are_written_and_veto_is_not_applied(self):
        from review_terms_llm import Verdict

        verdicts = [
            Verdict("甲公司", "keep", "org", 0.9, "甲公司", "ok", "accepted", "通过"),
            Verdict("通用词", "veto", None, 0.9, "", "通用", "suggested_veto", "通过"),
            Verdict("乙公司", "escalate", None, 0.0, "", "不确定", "manual", "通过"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            stats = write_outputs(out, verdicts, {"model": "stub", "mode": "test"})
            self.assertEqual(stats["accepted"], 1)
            self.assertEqual(stats["suggested_veto"], 1)
            self.assertEqual(stats["manual"], 1)
            payload = json.loads((out / "llm-review.json").read_text(encoding="utf-8"))
            self.assertEqual(len(payload["suggested_veto"]), 1)
            accepted = (out / "terms-llm-accepted.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(accepted, ["org:甲公司"])


class LoadCandidatesTest(unittest.TestCase):
    def test_reads_clusters_and_respects_bucket_filter(self):
        audit = {
            "clusters": [
                {"stem": "甲公司", "category": "org", "bucket": "HIGH", "files": 2,
                 "variants": ["甲公司"], "evidence": [{"file": "a.docx", "channel": "company", "context": "由甲公司持有"}]},
                {"stem": "宽泛项目", "category": "project", "bucket": "LOW", "files": 1,
                 "variants": ["宽泛项目"], "evidence": []},
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "audit.json"
            p.write_text(json.dumps(audit, ensure_ascii=False), encoding="utf-8")
            both = load_candidates(p, include_low=True, limit=None)
            self.assertEqual([c.term for c in both], ["甲公司", "宽泛项目"])
            high_only = load_candidates(p, include_low=False, limit=None)
            self.assertEqual([c.term for c in high_only], ["甲公司"])
            limited = load_candidates(p, include_low=True, limit=1)
            self.assertEqual([c.term for c in limited], ["甲公司"])
            self.assertEqual(both[0].evidence, ["由甲公司持有"])


class ConfigFromEnvTest(unittest.TestCase):
    """配置全部来自环境变量，密钥不落盘。"""

    def test_from_env_reads_all_values(self):
        env = {
            ENV_PREFIX + "ENDPOINT": "https://example.com/v1/chat/completions",
            ENV_PREFIX + "MODEL": "deepseek-v41-flash",
            ENV_PREFIX + "API_KEY": "sk-abcdef123456",
            ENV_PREFIX + "TIMEOUT": "30",
            ENV_PREFIX + "MAX_RETRIES": "5",
            ENV_PREFIX + "MAX_TOKENS": "1024",
            ENV_PREFIX + "TEMPERATURE": "0.2",
            ENV_PREFIX + "CACHE_DIR": "/tmp/cache-x",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = LLMConfig.from_env()
        self.assertEqual(cfg.endpoint, "https://example.com/v1/chat/completions")
        self.assertEqual(cfg.model, "deepseek-v41-flash")
        self.assertEqual(cfg.api_key, "sk-abcdef123456")
        self.assertEqual(cfg.timeout_seconds, 30.0)
        self.assertEqual(cfg.max_retries, 5)
        self.assertEqual(cfg.max_tokens, 1024)
        self.assertEqual(cfg.temperature, 0.2)
        self.assertEqual(cfg.cache_dir, "/tmp/cache-x")
        self.assertEqual(cfg.missing(), [])

    def test_missing_reports_actionable_env_names(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = LLMConfig.from_env()
        missing = cfg.missing()
        self.assertIn(ENV_PREFIX + "ENDPOINT", missing)
        self.assertIn(ENV_PREFIX + "MODEL", missing)
        self.assertTrue(any("API_KEY" in name for name in missing))
        with self.assertRaises(LLMError):
            cfg.validate()

    def test_api_key_falls_back_to_deepseek_env(self):
        with patch.dict(os.environ, {FALLBACK_API_KEY_ENV: "sk-fallback98765"}, clear=True):
            cfg = LLMConfig.from_env()
        self.assertEqual(cfg.api_key, "sk-fallback98765")

    def test_explicit_key_wins_over_fallback_env(self):
        env = {ENV_PREFIX + "API_KEY": "sk-explicit", FALLBACK_API_KEY_ENV: "sk-fallback"}
        with patch.dict(os.environ, env, clear=True):
            cfg = LLMConfig.from_env()
        self.assertEqual(cfg.api_key, "sk-explicit")

    def test_cli_override_beats_env(self):
        with patch.dict(os.environ, {ENV_PREFIX + "MODEL": "from-env"}, clear=True):
            cfg = LLMConfig.from_env({"model": "from-cli"})
        self.assertEqual(cfg.model, "from-cli")

    def test_none_override_is_ignored(self):
        with patch.dict(os.environ, {ENV_PREFIX + "MODEL": "from-env"}, clear=True):
            cfg = LLMConfig.from_env({"model": None})
        self.assertEqual(cfg.model, "from-env")

    def test_unknown_override_rejected(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(LLMError):
                LLMConfig.from_env({"nope": "x"})

    def test_invalid_numbers_raise(self):
        with patch.dict(os.environ, {ENV_PREFIX + "TIMEOUT": "abc"}, clear=True):
            with self.assertRaises(LLMError):
                LLMConfig.from_env()
        with patch.dict(os.environ, {ENV_PREFIX + "MAX_RETRIES": "两"}, clear=True):
            with self.assertRaises(LLMError):
                LLMConfig.from_env()

    def test_mask_key_never_reveals_secret(self):
        self.assertEqual(mask_key(""), "（未设置）")
        self.assertEqual(mask_key("short"), "***")
        masked = mask_key("sk-abcdef1234567890")
        self.assertTrue(masked.startswith("sk-"))
        self.assertIn("***", masked)
        self.assertNotIn("abcdef", masked)

    def test_summary_is_safe_to_print(self):
        cfg = LLMConfig(
            endpoint="https://api.example.com/v1/chat/completions",
            model="deepseek-v41-flash",
            api_key="sk-secretvalue123456",
        )
        summary = cfg.summary()
        self.assertIn("api.example.com", summary)
        self.assertIn("deepseek-v41-flash", summary)
        self.assertIn("***", summary)
        self.assertNotIn("secretvalue", summary)


class ExtraBodyAndTransportTest(unittest.TestCase):
    """请求体透传与空正文（推理模型耗尽 max_tokens）的可操作报错。"""

    @staticmethod
    def _response(payload):
        class _Resp:
            def __init__(self, blob):
                self._blob = blob

            def read(self):
                return self._blob

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return _Resp(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def test_extra_body_is_merged_into_request_body(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return self._response({"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]})

        config = LLMConfig(endpoint="http://x/v1/chat/completions", model="m", api_key="k",
                           extra_body={"enable_thinking": False})
        with patch("urllib.request.urlopen", fake_urlopen):
            from llm_client import default_transport

            default_transport(config, "s", "u")
        self.assertIs(captured["body"]["enable_thinking"], False)
        self.assertEqual(captured["body"]["model"], "m")

    def test_empty_content_error_names_the_reason_and_fix(self):
        def fake_urlopen(req, timeout=None):
            return self._response({
                "choices": [{"message": {"content": ""}, "finish_reason": "length"}],
                "usage": {"completion_tokens": 4096,
                          "completion_tokens_details": {"reasoning_tokens": 4096}},
            })

        config = LLMConfig(endpoint="http://x/v1/chat/completions", model="m", api_key="k")
        with patch("urllib.request.urlopen", fake_urlopen):
            from llm_client import default_transport

            with self.assertRaises(LLMError) as ctx:
                default_transport(config, "s", "u")
        message = str(ctx.exception)
        self.assertIn("空 content", message)
        self.assertIn("reasoning_tokens=4096", message)
        self.assertIn("enable_thinking", message)

    def test_extra_body_parsed_from_env(self):
        with patch.dict(os.environ, {ENV_PREFIX + "EXTRA_BODY": '{"enable_thinking": false}'}, clear=True):
            cfg = LLMConfig.from_env()
        self.assertEqual(cfg.extra_body, {"enable_thinking": False})

    def test_invalid_extra_body_from_env_is_rejected(self):
        with patch.dict(os.environ, {ENV_PREFIX + "EXTRA_BODY": "not-json"}, clear=True):
            with self.assertRaises(LLMError):
                LLMConfig.from_env()
        with patch.dict(os.environ, {ENV_PREFIX + "EXTRA_BODY": "[1, 2]"}, clear=True):
            with self.assertRaises(LLMError):
                LLMConfig.from_env()

    def test_summary_shows_extra_body(self):
        cfg = LLMConfig(endpoint="http://x/v1/chat/completions", model="m",
                        api_key="sk-abcdef123", extra_body={"enable_thinking": False})
        self.assertIn("enable_thinking", cfg.summary())


if __name__ == "__main__":
    unittest.main()
