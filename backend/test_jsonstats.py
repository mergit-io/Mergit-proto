#!/usr/bin/env python3
"""
Unit tests for the jsonstats module.
"""

import unittest
import json
import tempfile
import os
import sys
from pathlib import Path

# Import the functions from jsonstats
from jsonstats import (
    count_keys,
    get_value_types,
    get_max_depth,
    analyze_json_file,
    format_statistics
)


class TestCountKeys(unittest.TestCase):
    """Test the count_keys function."""
    
    def test_empty_dict(self):
        """Test with empty dictionary."""
        self.assertEqual(count_keys({}), 0)
    
    def test_single_key(self):
        """Test with single key."""
        self.assertEqual(count_keys({'a': 1}), 1)
    
    def test_multiple_keys(self):
        """Test with multiple keys."""
        self.assertEqual(count_keys({'a': 1, 'b': 2, 'c': 3}), 3)
    
    def test_nested_dict(self):
        """Test with nested dictionaries."""
        obj = {'a': {'b': {'c': 1}}}
        self.assertEqual(count_keys(obj), 3)
    
    def test_dict_with_list(self):
        """Test dictionary containing lists."""
        obj = {'a': [1, 2, 3], 'b': {'c': 4}}
        self.assertEqual(count_keys(obj), 3)
    
    def test_list_of_dicts(self):
        """Test list containing dictionaries."""
        obj = [{'a': 1}, {'b': 2}]
        self.assertEqual(count_keys(obj), 2)
    
    def test_scalar_value(self):
        """Test with scalar values."""
        self.assertEqual(count_keys(42), 0)
        self.assertEqual(count_keys("string"), 0)
        self.assertEqual(count_keys(None), 0)


class TestGetValueTypes(unittest.TestCase):
    """Test the get_value_types function."""
    
    def test_single_string(self):
        """Test with single string value."""
        result = get_value_types({'a': 'hello'})
        self.assertEqual(result['string'], 1)
        self.assertEqual(result['dict'], 1)
    
    def test_multiple_types(self):
        """Test with multiple value types."""
        obj = {
            'str': 'hello',
            'int': 42,
            'float': 3.14,
            'bool': True,
            'null': None,
            'list': [1, 2],
            'dict': {'nested': 'value'}
        }
        result = get_value_types(obj)
        self.assertEqual(result['string'], 2)  # 'hello' and 'value'
        self.assertEqual(result['int'], 3)     # 42 and [1, 2]
        self.assertEqual(result['float'], 1)
        self.assertEqual(result['bool'], 1)
        self.assertEqual(result['null'], 1)
        self.assertEqual(result['list'], 1)
        self.assertEqual(result['dict'], 2)    # outer dict and nested dict
    
    def test_nested_types(self):
        """Test type counting in nested structures."""
        obj = {'outer': {'inner': [1, 2, 3]}}
        result = get_value_types(obj)
        self.assertEqual(result['dict'], 2)
        self.assertEqual(result['list'], 1)
        self.assertEqual(result['int'], 3)
    
    def test_bool_vs_int(self):
        """Test that booleans are counted separately from integers."""
        obj = {'bool_val': True, 'int_val': 1}
        result = get_value_types(obj)
        self.assertEqual(result['bool'], 1)
        self.assertEqual(result['int'], 1)


class TestGetMaxDepth(unittest.TestCase):
    """Test the get_max_depth function."""
    
    def test_empty_dict(self):
        """Test with empty dictionary."""
        self.assertEqual(get_max_depth({}), 0)
    
    def test_flat_dict(self):
        """Test with flat dictionary (scalars only)."""
        # A dict with only scalar values has depth 1
        self.assertEqual(get_max_depth({'a': 1, 'b': 2}), 1)
    
    def test_one_level_nesting(self):
        """Test with one level of nesting."""
        # A dict containing another dict has depth 2
        self.assertEqual(get_max_depth({'a': {'b': 1}}), 2)
    
    def test_two_level_nesting(self):
        """Test with two levels of nesting."""
        # A dict containing nested dicts has depth 3
        self.assertEqual(get_max_depth({'a': {'b': {'c': 1}}}), 3)
    
    def test_list_nesting(self):
        """Test with list nesting."""
        # List with depth calculation
        self.assertEqual(get_max_depth([[[1]]]), 3)
    
    def test_mixed_nesting(self):
        """Test with mixed dict and list nesting."""
        obj = {'a': [{'b': [1, 2, 3]}]}
        # dict (1) -> list (2) -> dict (3) -> list (4)
        self.assertEqual(get_max_depth(obj), 4)
    
    def test_scalar_value(self):
        """Test with scalar value."""
        self.assertEqual(get_max_depth(42), 0)
        self.assertEqual(get_max_depth("string"), 0)


class TestAnalyzeJsonFile(unittest.TestCase):
    """Test the analyze_json_file function."""
    
    def setUp(self):
        """Set up temporary directory for test files."""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_valid_json_file(self):
        """Test with valid JSON file."""
        file_path = os.path.join(self.temp_dir, 'test.json')
        test_data = {'name': 'John', 'age': 30}
        with open(file_path, 'w') as f:
            json.dump(test_data, f)
        
        stats, error = analyze_json_file(file_path)
        self.assertEqual(error, "")
        self.assertEqual(stats['key_count'], 2)
        self.assertIn('value_types', stats)
        self.assertIn('max_depth', stats)
    
    def test_invalid_json_file(self):
        """Test with invalid JSON file."""
        file_path = os.path.join(self.temp_dir, 'invalid.json')
        with open(file_path, 'w') as f:
            f.write('{ invalid json }')
        
        stats, error = analyze_json_file(file_path)
        self.assertNotEqual(error, "")
        self.assertIn('Invalid JSON', error)
        self.assertEqual(stats, {})
    
    def test_nonexistent_file(self):
        """Test with nonexistent file."""
        stats, error = analyze_json_file('/nonexistent/path/file.json')
        self.assertNotEqual(error, "")
        self.assertIn('does not exist', error)
        self.assertEqual(stats, {})
    
    def test_directory_instead_of_file(self):
        """Test when path points to directory."""
        stats, error = analyze_json_file(self.temp_dir)
        self.assertNotEqual(error, "")
        self.assertIn('not a file', error)
        self.assertEqual(stats, {})
    
    def test_nested_json_structure(self):
        """Test with complex nested JSON."""
        file_path = os.path.join(self.temp_dir, 'nested.json')
        test_data = {
            'users': [
                {'name': 'Alice', 'age': 25, 'active': True},
                {'name': 'Bob', 'age': 30, 'active': False}
            ],
            'metadata': {
                'version': '1.0',
                'timestamp': None
            }
        }
        with open(file_path, 'w') as f:
            json.dump(test_data, f)
        
        stats, error = analyze_json_file(file_path)
        self.assertEqual(error, "")
        self.assertGreater(stats['key_count'], 0)
        self.assertGreater(stats['max_depth'], 0)


class TestFormatStatistics(unittest.TestCase):
    """Test the format_statistics function."""
    
    def test_format_output(self):
        """Test that statistics are formatted correctly."""
        stats = {
            'file': '/path/to/file.json',
            'key_count': 10,
            'max_depth': 2,
            'value_types': {'string': 5, 'int': 3, 'bool': 1, 'null': 1}
        }
        output = format_statistics(stats)
        
        self.assertIn('file.json', output)
        self.assertIn('Total Key Count: 10', output)
        self.assertIn('Maximum Nesting Depth: 2', output)
        self.assertIn('Value Type Breakdown:', output)
        self.assertIn('string: 5', output)
        self.assertIn('int: 3', output)


class TestIntegration(unittest.TestCase):
    """Integration tests for the complete workflow."""
    
    def setUp(self):
        """Set up temporary directory for test files."""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_complex_json_analysis(self):
        """Test complete analysis of a complex JSON structure."""
        file_path = os.path.join(self.temp_dir, 'complex.json')
        test_data = {
            'application': 'MyApp',
            'version': 1.0,
            'enabled': True,
            'config': {
                'debug': False,
                'timeout': 30,
                'features': ['auth', 'api', 'web'],
                'defaults': {
                    'retry': 3,
                    'delay': 1.5
                }
            },
            'permissions': [
                {'user': 'admin', 'level': 10},
                {'user': 'guest', 'level': 1}
            ],
            'error': None
        }
        with open(file_path, 'w') as f:
            json.dump(test_data, f)
        
        stats, error = analyze_json_file(file_path)
        self.assertEqual(error, "")
        
        # Verify key statistics
        self.assertGreater(stats['key_count'], 0)
        self.assertGreater(stats['max_depth'], 1)
        
        # Verify type breakdown exists
        types = stats['value_types']
        self.assertGreater(len(types), 0)


if __name__ == '__main__':
    unittest.main()
