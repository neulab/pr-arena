"""
Patch for daytona_api_client compatibility issue.

The daytona-sdk 0.18.1 (required by openhands-ai 0.40.0) expects certain classes to be 
available in daytona_api_client, but in newer versions of daytona_api_client (0.21.0+), 
these have been renamed from Workspace* to Sandbox*:

- WorkspaceState -> SandboxState
- WorkspaceVolume -> SandboxVolume  
- WorkspaceInfo -> SandboxInfo

This patch adds the missing Workspace* aliases to maintain compatibility without
requiring a downgrade of daytona_api_client or upgrade of daytona-sdk.
"""

def apply_daytona_patch():
    """Apply the daytona compatibility patch."""
    try:
        import daytona_api_client
        from daytona_api_client.models.sandbox_state import SandboxState
        from daytona_api_client.models.sandbox_volume import SandboxVolume
        from daytona_api_client.models.sandbox_info import SandboxInfo
        
        # Add the missing WorkspaceState alias
        if not hasattr(daytona_api_client, 'WorkspaceState'):
            daytona_api_client.WorkspaceState = SandboxState
            
        # Add the missing WorkspaceVolume alias
        if not hasattr(daytona_api_client, 'WorkspaceVolume'):
            daytona_api_client.WorkspaceVolume = SandboxVolume
            
        # Add the missing WorkspaceInfo alias
        if not hasattr(daytona_api_client, 'WorkspaceInfo'):
            daytona_api_client.WorkspaceInfo = SandboxInfo
            
        # Also add them to the module's __all__ if it exists
        if hasattr(daytona_api_client, '__all__'):
            if 'WorkspaceState' not in daytona_api_client.__all__:
                daytona_api_client.__all__.append('WorkspaceState')
            if 'WorkspaceVolume' not in daytona_api_client.__all__:
                daytona_api_client.__all__.append('WorkspaceVolume')
            if 'WorkspaceInfo' not in daytona_api_client.__all__:
                daytona_api_client.__all__.append('WorkspaceInfo')
                
    except ImportError:
        # If daytona_api_client is not available, skip the patch
        pass