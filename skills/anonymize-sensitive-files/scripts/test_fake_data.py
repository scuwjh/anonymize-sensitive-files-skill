import unittest

from fake_data import FAKE_VALUES, FakeDataFactory


class FakeDataPoolsTest(unittest.TestCase):
    def test_common_business_fake_data_pools_are_large_enough(self):
        for category in ["name", "phone", "email", "address", "org", "customer", "project", "contract", "custom"]:
            with self.subTest(category=category):
                self.assertGreaterEqual(len(FAKE_VALUES[category]), 12)

    def test_structured_fake_data_pools_have_enough_variety(self):
        for category in ["id_card", "passport", "bank_card", "social_credit_code", "ip", "url", "domain", "secret"]:
            with self.subTest(category=category):
                self.assertGreaterEqual(len(FAKE_VALUES[category]), 6)

    def test_larger_pools_are_used_before_cycling(self):
        factory = FakeDataFactory()
        replacements = [factory.replacement_for("name", f"真实姓名{index}") for index in range(12)]
        self.assertEqual(len(set(replacements)), 12)

    def test_replacement_never_equals_original_fake_pool_value(self):
        factory = FakeDataFactory()
        self.assertNotEqual(factory.replacement_for("name", "张三"), "张三")
        self.assertNotEqual(factory.replacement_for("org", "北京星河科技有限公司"), "北京星河科技有限公司")

    def test_safe_mapping_uses_random_salt_without_explicit_seed(self):
        first = FakeDataFactory()
        second = FakeDataFactory()
        first.replacement_for("phone", "13812345678")
        second.replacement_for("phone", "13812345678")

        first_hash = next(iter(first.safe_mapping()["phone"]))
        second_hash = next(iter(second.safe_mapping()["phone"]))
        self.assertNotEqual(first_hash, second_hash)


if __name__ == "__main__":
    unittest.main()
