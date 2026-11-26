import pytest

from shared import topics as T
from ai.model_versions import (POLICY_BY_METHOD, is_model_version, list_model_versions, newest_model_version,
                               policy_of)


def touch_model(models_dir, model_version, with_json=True):
    (models_dir / f"{model_version}.zip").write_bytes(b"")
    if with_json:
        (models_dir / f"{model_version}.json").write_text("{}", encoding="utf-8")


@pytest.mark.parametrize("text, expected", [
    ("ppo-20261201-2", True), ("bc-20261130-1", True),
    ("ppo-2026121-2", False), ("sac-20261201-1", False), ("ppo-20261201", False), ("PPO-20261201-1", False),
])
def test_model_version_names(text, expected):
    assert is_model_version(text) is expected


def test_policy_follows_the_method():
    assert policy_of("ppo-20261201-2") == "rl"
    assert policy_of("bc-20261201-1") == "imitation"
    assert set(POLICY_BY_METHOD.values()) == set(T.POLICY_VALUES)
    with pytest.raises(ValueError):
        policy_of("latest")


def test_newest_is_by_date_then_number(tmp_path):
    for version in ["ppo-20261201-2", "ppo-20261201-10", "bc-20261130-5", "ppo-20261129-9"]:
        touch_model(tmp_path, version)
    assert list_model_versions(tmp_path) == ["ppo-20261129-9", "bc-20261130-5", "ppo-20261201-2", "ppo-20261201-10"]
    assert newest_model_version(tmp_path) == "ppo-20261201-10"


def test_incomplete_or_unnamed_models_are_not_listed(tmp_path):
    touch_model(tmp_path, "ppo-20261201-1", with_json=False)
    touch_model(tmp_path, "my-model")
    touch_model(tmp_path, "bc-20261130-1")
    assert list_model_versions(tmp_path) == ["bc-20261130-1"]


def test_no_models_folder_gives_no_model(tmp_path):
    assert list_model_versions(tmp_path / "missing") == []
    assert newest_model_version(tmp_path / "missing") is None
