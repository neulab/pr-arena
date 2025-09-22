"""Test dependabot configuration."""

import yaml
from pathlib import Path


def test_dependabot_config_exists():
    """Test that dependabot.yml exists."""
    config_path = Path(__file__).parent.parent / ".github" / "dependabot.yml"
    assert config_path.exists(), "dependabot.yml should exist"


def test_dependabot_config_valid_yaml():
    """Test that dependabot.yml is valid YAML."""
    config_path = Path(__file__).parent.parent / ".github" / "dependabot.yml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    assert config is not None, "dependabot.yml should contain valid YAML"
    assert "version" in config, "dependabot.yml should have version field"
    assert "updates" in config, "dependabot.yml should have updates field"


def test_dependabot_config_has_groups():
    """Test that dependabot.yml has grouping configured."""
    config_path = Path(__file__).parent.parent / ".github" / "dependabot.yml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    assert config["version"] == 2, "dependabot.yml should use version 2"
    assert isinstance(config["updates"], list), "updates should be a list"
    assert len(config["updates"]) >= 1, "should have at least one update configuration"

    # Check that at least one update configuration has groups
    has_groups = any("groups" in update for update in config["updates"])
    assert has_groups, "at least one update configuration should have groups"


def test_dependabot_config_pip_ecosystem():
    """Test that pip ecosystem is configured with groups."""
    config_path = Path(__file__).parent.parent / ".github" / "dependabot.yml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    pip_updates = [update for update in config["updates"] if update.get("package-ecosystem") == "pip"]
    assert len(pip_updates) == 1, "should have exactly one pip update configuration"

    pip_config = pip_updates[0]
    assert "groups" in pip_config, "pip configuration should have groups"
    assert isinstance(pip_config["groups"], dict), "groups should be a dictionary"
    assert len(pip_config["groups"]) >= 1, "should have at least one group defined"


def test_dependabot_config_github_actions_ecosystem():
    """Test that github-actions ecosystem is configured with groups."""
    config_path = Path(__file__).parent.parent / ".github" / "dependabot.yml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    actions_updates = [update for update in config["updates"] if update.get("package-ecosystem") == "github-actions"]
    assert len(actions_updates) == 1, "should have exactly one github-actions update configuration"

    actions_config = actions_updates[0]
    assert "groups" in actions_config, "github-actions configuration should have groups"
    assert isinstance(actions_config["groups"], dict), "groups should be a dictionary"
    assert len(actions_config["groups"]) >= 1, "should have at least one group defined"


def test_dependabot_config_group_patterns():
    """Test that groups have proper patterns configured."""
    config_path = Path(__file__).parent.parent / ".github" / "dependabot.yml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    for update in config["updates"]:
        if "groups" in update:
            for group_name, group_config in update["groups"].items():
                assert "patterns" in group_config, f"group {group_name} should have patterns"
                assert isinstance(group_config["patterns"], list), f"patterns for {group_name} should be a list"
                assert len(group_config["patterns"]) >= 1, f"group {group_name} should have at least one pattern"
