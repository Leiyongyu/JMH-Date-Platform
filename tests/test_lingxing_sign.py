from backend.integrations.lingxing.sign import _string_value


def test_boolean_sign_values_match_json_and_java_serialization():
    assert _string_value(True) == "true"
    assert _string_value(False) == "false"
