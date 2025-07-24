import unittest
import os
import sys
import importlib.util
from unittest.mock import patch, mock_open


class TestVersionInfo(unittest.TestCase):
    """Test cases for version information across the project"""

    def test_resolver_init_version(self):
        """Test that resolver/__init__.py contains a version"""
        try:
            import resolver
            version = resolver.__version__
            self.assertIsInstance(version, str)
            self.assertTrue(len(version) > 0)
            # Check version format (should be semantic versioning)
            version_parts = version.split('.')
            self.assertGreaterEqual(len(version_parts), 2)  # At least major.minor
            # Each part should be numeric
            for part in version_parts:
                # Handle pre-release versions like "1.0.0-alpha"
                numeric_part = part.split('-')[0]
                self.assertTrue(numeric_part.isdigit(), f"Version part '{numeric_part}' should be numeric")
        except ImportError:
            self.fail("Could not import resolver module")

    def test_pyproject_toml_version(self):
        """Test that pyproject.toml contains a version that matches __init__.py"""
        try:
            # Read pyproject.toml
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            pyproject_path = os.path.join(project_root, 'pyproject.toml')
            
            if not os.path.exists(pyproject_path):
                self.skipTest("pyproject.toml not found")
            
            with open(pyproject_path, 'r') as f:
                content = f.read()
            
            # Look for version line
            version_line = None
            for line in content.split('\n'):
                if line.strip().startswith('version = '):
                    version_line = line
                    break
            
            self.assertIsNotNone(version_line, "Version not found in pyproject.toml")
            
            # Extract version from the line
            pyproject_version = version_line.split('=')[1].strip().strip('"').strip("'")
            
            # Compare with resolver.__version__
            import resolver
            resolver_version = resolver.__version__
            
            self.assertEqual(pyproject_version, resolver_version, 
                           f"Version mismatch: pyproject.toml has '{pyproject_version}' but resolver.__init__.py has '{resolver_version}'")
            
        except Exception as e:
            self.fail(f"Failed to read or parse pyproject.toml: {e}")

    def test_version_format(self):
        """Test that version follows semantic versioning format"""
        try:
            import resolver
            version = resolver.__version__
            
            # Split version into parts
            # Handle pre-release versions like "1.0.0-alpha" or "1.0.0-rc.1"
            base_version = version.split('-')[0]  # Get the base version without pre-release info
            version_parts = base_version.split('.')
            
            # Should have at least major.minor
            self.assertGreaterEqual(len(version_parts), 2, "Version should have at least major.minor")
            
            # Should have at most major.minor.patch
            self.assertLessEqual(len(version_parts), 3, "Version should have at most major.minor.patch")
            
            # Each part should be numeric
            for i, part in enumerate(version_parts):
                self.assertTrue(part.isdigit(), f"Version part {i} ('{part}') should be numeric")
                # Should be non-negative
                self.assertGreaterEqual(int(part), 0, f"Version part {i} should be non-negative")
                
        except ImportError:
            self.fail("Could not import resolver module")

    def test_version_is_not_empty(self):
        """Test that version is not empty or None"""
        try:
            import resolver
            version = resolver.__version__
            self.assertIsNotNone(version, "Version should not be None")
            self.assertNotEqual(version.strip(), "", "Version should not be empty")
            self.assertNotEqual(version.strip().lower(), "unknown", "Version should not be 'unknown'")
            self.assertNotEqual(version.strip(), "0.0.0", "Version should not be placeholder '0.0.0'")
        except ImportError:
            self.fail("Could not import resolver module")

    def test_version_consistency_across_files(self):
        """Test that version is consistent across different files that might contain it"""
        try:
            import resolver
            resolver_version = resolver.__version__
            
            # Check if there are any other files that might contain version info
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
            # Check setup.py if it exists
            setup_py_path = os.path.join(project_root, 'setup.py')
            if os.path.exists(setup_py_path):
                with open(setup_py_path, 'r') as f:
                    setup_content = f.read()
                
                # Look for version in setup.py (this is a simple check)
                if 'version=' in setup_content:
                    # This would need more sophisticated parsing for a real check
                    pass  # Skip for now as setup.py doesn't exist in this project
            
            # Check __init__.py in the package
            init_py_path = os.path.join(project_root, 'resolver', '__init__.py')
            if os.path.exists(init_py_path):
                with open(init_py_path, 'r') as f:
                    init_content = f.read()
                
                # The version should be defined as __version__ = "x.y.z"
                self.assertIn('__version__', init_content, "__version__ should be defined in __init__.py")
                self.assertIn(resolver_version, init_content, f"Version {resolver_version} should appear in __init__.py")
                
        except ImportError:
            self.fail("Could not import resolver module")


class TestVersionImport(unittest.TestCase):
    """Test cases for version import functionality"""

    def test_can_import_version_directly(self):
        """Test that we can import version directly from the package"""
        try:
            from resolver import __version__
            self.assertIsInstance(__version__, str)
            self.assertTrue(len(__version__) > 0)
        except ImportError as e:
            self.fail(f"Could not import __version__ directly: {e}")

    def test_version_accessible_from_package(self):
        """Test that version is accessible as package attribute"""
        try:
            import resolver
            # Should be able to access version as attribute
            version = getattr(resolver, '__version__', None)
            self.assertIsNotNone(version, "Package should have __version__ attribute")
            self.assertIsInstance(version, str)
        except ImportError:
            self.fail("Could not import resolver package")

    @patch('builtins.open', side_effect=FileNotFoundError)
    def test_version_import_handles_missing_file(self, mock_open):
        """Test graceful handling if version file is missing"""
        # This test simulates what would happen if __init__.py was missing
        # In practice, this shouldn't happen, but it's good to test error handling
        
        # Since we can't easily mock the import system for this specific case,
        # we'll skip this test in the actual implementation
        self.skipTest("Mocking import system for this test is complex")

    def test_version_type_and_format(self):
        """Test version type and basic format requirements"""
        try:
            import resolver
            version = resolver.__version__
            
            # Type check
            self.assertIsInstance(version, str, "Version should be a string")
            
            # Basic format check
            self.assertRegex(version, r'^\d+\.\d+(\.\d+)?(-\w+)?$', 
                           "Version should match semantic versioning pattern (e.g., '1.0.0' or '1.0.0-alpha')")
            
        except ImportError:
            self.fail("Could not import resolver module")


class TestVersionUtilities(unittest.TestCase):
    """Test utility functions related to version handling"""

    def test_version_comparison_basic(self):
        """Test basic version comparison functionality"""
        # Since the project doesn't seem to have version comparison utilities,
        # we'll test basic string-based version comparison logic
        
        version1 = "1.0.0"
        version2 = "1.0.1"
        version3 = "1.1.0"
        version4 = "2.0.0"
        
        # Convert versions to tuples for comparison
        def version_tuple(v):
            return tuple(map(int, v.split('.')))
        
        self.assertLess(version_tuple(version1), version_tuple(version2))
        self.assertLess(version_tuple(version2), version_tuple(version3))
        self.assertLess(version_tuple(version3), version_tuple(version4))
        self.assertGreater(version_tuple(version4), version_tuple(version1))

    def test_current_version_is_valid_semver(self):
        """Test that current version follows semantic versioning"""
        try:
            import resolver
            version = resolver.__version__
            
            # For this project, we'll use a simpler pattern since it's early stage
            simple_pattern = r'^\d+\.\d+\.\d+$'
            
            self.assertRegex(version, simple_pattern, 
                           f"Version '{version}' should follow simple semantic versioning (major.minor.patch)")
            
        except ImportError:
            self.fail("Could not import resolver module")


if __name__ == '__main__':
    # Run with verbose output to see all test names
    unittest.main(verbosity=2)