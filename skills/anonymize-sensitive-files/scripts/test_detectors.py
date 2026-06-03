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


if __name__ == "__main__":
    unittest.main()
