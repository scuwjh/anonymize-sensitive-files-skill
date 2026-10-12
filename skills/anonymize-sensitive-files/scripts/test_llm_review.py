import json
import tempfile
import unittest
from pathlib import Path

from llm_client import LLMClient, LLMConfig, LLMError, RequestCache, extract_json
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


if __name__ == "__main__":
    unittest.main()
