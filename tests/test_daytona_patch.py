"""Test the daytona compatibility patch."""

import pytest


def test_daytona_patch_applies_correctly():
    """Test that the daytona patch correctly adds missing aliases."""
    from resolver.daytona_patch import apply_daytona_patch
    
    # Apply the patch
    apply_daytona_patch()
    
    # Import daytona_api_client and verify the aliases exist
    import daytona_api_client
    
    # Check that all required aliases are available
    required_aliases = ['WorkspaceState', 'WorkspaceVolume', 'WorkspaceInfo']
    for alias in required_aliases:
        assert hasattr(daytona_api_client, alias), f"Missing alias: {alias}"
    
    # Verify the aliases point to the correct classes
    from daytona_api_client.models.sandbox_state import SandboxState
    from daytona_api_client.models.sandbox_volume import SandboxVolume
    from daytona_api_client.models.sandbox_info import SandboxInfo
    
    assert daytona_api_client.WorkspaceState is SandboxState
    assert daytona_api_client.WorkspaceVolume is SandboxVolume
    assert daytona_api_client.WorkspaceInfo is SandboxInfo


def test_resolver_imports_successfully():
    """Test that the resolver modules can be imported without errors."""
    # This should not raise any ImportError
    from resolver.resolve_issue import main
    from resolver.send_pull_request import load_all_resolver_outputs
    
    # If we get here, the imports were successful
    assert True


def test_openhands_imports_successfully():
    """Test that openhands modules can be imported after applying the patch."""
    # Apply patch first
    from resolver.daytona_patch import apply_daytona_patch
    apply_daytona_patch()
    
    # These imports should work without errors
    import openhands
    from openhands.resolver.interfaces.github import GithubIssueHandler
    
    # If we get here, the imports were successful
    assert True