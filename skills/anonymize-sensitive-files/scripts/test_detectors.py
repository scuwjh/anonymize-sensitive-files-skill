import unittest

from detectors import detect_sensitive_values


class DetectorQualityTest(unittest.TestCase):
    def test_version_number_is_not_reported_as_ip_without_ip_context(self):
        findings = detect_sensitive_values("版本 1.2.3.4 已发布", [])

        self.assertEqual([finding for finding in findings if finding.category == "ip"], [])

    def test_labeled_ip_address_is_still_reported(self):
        findings = detect_sensitive_values("服务器 IP：1.2.3.4", [])

        self.assertEqual([finding.value for finding in findings if finding.category == "ip"], ["1.2.3.4"])

    def test_address_detection_trims_introductory_phrase(self):
        findings = detect_sensitive_values("客户位于北京市朝阳区示例路88号，联系人李雷。", [])
        addresses = [finding for finding in findings if finding.category == "address"]

        self.assertEqual(len(addresses), 1)
        self.assertEqual(addresses[0].value, "北京市朝阳区示例路88号")

    def test_legal_prose_is_not_reported_as_address(self):
        sentences = [
            "关于确认境外上市财务负责人任职资格的请示",
            "市场部与上市办联合召开资本市场专题工作会议",
            "本次发行上市申请文件存在虚假记载",
        ]
        for sentence in sentences:
            findings = detect_sensitive_values(sentence, [], [])
            self.assertEqual([finding.value for finding in findings if finding.category == "address"], [], sentence)

    def test_two_level_address_is_still_reported(self):
        findings = detect_sensitive_values("住所：上海市浦东新区世纪大道100号", [], [])
        self.assertEqual([finding.value for finding in findings if finding.category == "address"], ["上海市浦东新区世纪大道100号"])

    def test_case_and_document_numbers_are_detected(self):
        findings = detect_sensitive_values("案号：（2020）京0105民初28200号，京市监罚字〔2019〕123号", [], [])
        self.assertEqual([finding.category for finding in findings], ["case_number", "doc_number"])

    def test_landline_is_reported_as_phone_category(self):
        findings = detect_sensitive_values("传真：021-8888 5678", [], [])
        self.assertEqual([(finding.category, finding.source) for finding in findings], [("phone", "cn_landline")])


if __name__ == "__main__":
    unittest.main()
