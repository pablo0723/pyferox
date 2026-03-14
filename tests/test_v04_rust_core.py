import unittest

from pyferox import Schema, Serializer
from pyferox.rust_bridge import compiled_schema_cache_size, rust_validation_mode


class PayloadSchema(Schema):
    name: str
    age: int


class PayloadSerializer(Serializer):
    name: str
    age: int


class V04RustCoreTests(unittest.TestCase):
    def test_schema_validation_path(self):
        validated = PayloadSchema.validate({"name": "Ada", "age": 33})
        self.assertEqual(validated["name"], "Ada")
        self.assertEqual(validated["age"], 33)

    def test_serializer_validation_path(self):
        serializer = PayloadSerializer(data={"name": "Ada", "age": 33})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["age"], 33)

    def test_compiled_schema_cache_behavior(self):
        mode = rust_validation_mode()
        self.assertEqual(mode, "rust-compiled")
        before = compiled_schema_cache_size()
        PayloadSchema.validate({"name": "Ada", "age": 33})
        PayloadSerializer(data={"name": "Ada", "age": 33}).is_valid()
        after = compiled_schema_cache_size()
        self.assertGreaterEqual(after, before)


if __name__ == "__main__":
    unittest.main()
