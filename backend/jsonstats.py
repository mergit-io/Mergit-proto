#!/usr/bin/env python3
"""
jsonstats - A CLI tool to analyze JSON files and display statistics.

This tool reads JSON files and provides detailed statistics including:
- Total key count
- Value type breakdown (string, int, float, bool, null, list, dict)
- Maximum nesting depth
"""

import json
import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Tuple
from collections import defaultdict


def count_keys(obj: Any) -> int:
    """
    Recursively count all keys in a JSON object.
    
    Args:
        obj: A JSON-serializable object (dict, list, etc.)
        
    Returns:
        Total count of all keys in the object and nested objects.
    """
    if isinstance(obj, dict):
        count = len(obj)
        for value in obj.values():
            count += count_keys(value)
        return count
    elif isinstance(obj, list):
        count = 0
        for item in obj:
            count += count_keys(item)
        return count
    else:
        return 0


def get_value_types(obj: Any) -> Dict[str, int]:
    """
    Recursively analyze value types in a JSON object.
    
    Args:
        obj: A JSON-serializable object (dict, list, etc.)
        
    Returns:
        Dictionary with count of each value type (string, int, float, bool, null, list, dict).
    """
    type_counts = defaultdict(int)
    
    def traverse(item: Any) -> None:
        """Helper function to traverse and count types."""
        if isinstance(item, dict):
            type_counts['dict'] += 1
            for value in item.values():
                traverse(value)
        elif isinstance(item, list):
            type_counts['list'] += 1
            for element in item:
                traverse(element)
        elif isinstance(item, bool):  # Check bool before int
            type_counts['bool'] += 1
        elif isinstance(item, int):
            type_counts['int'] += 1
        elif isinstance(item, float):
            type_counts['float'] += 1
        elif isinstance(item, str):
            type_counts['string'] += 1
        elif item is None:
            type_counts['null'] += 1
    
    traverse(obj)
    return dict(type_counts)


def get_max_depth(obj: Any) -> int:
    """
    Calculate the maximum nesting depth of a JSON object.
    
    The depth is measured as follows:
    - Scalar values have depth 0
    - A dict or list containing only scalar values has depth 1
    - Each additional level of nesting adds 1 to the depth
    
    Args:
        obj: A JSON-serializable object (dict, list, etc.)
        
    Returns:
        Maximum nesting depth in the object.
    """
    if isinstance(obj, dict):
        if not obj:
            return 0
        return 1 + max(get_max_depth(value) for value in obj.values())
    elif isinstance(obj, list):
        if not obj:
            return 0
        return 1 + max(get_max_depth(item) for item in obj)
    else:
        return 0


def analyze_json_file(file_path: str) -> Tuple[Dict[str, Any], str]:
    """
    Read and analyze a JSON file.
    
    Args:
        file_path: Path to the JSON file.
        
    Returns:
        Tuple of (statistics_dict, error_message).
        If successful, statistics_dict contains the analysis and error_message is empty.
        If failed, statistics_dict is empty and error_message contains the error.
    """
    try:
        path = Path(file_path)
        
        if not path.exists():
            return {}, f"Error: File '{file_path}' does not exist."
        
        if not path.is_file():
            return {}, f"Error: '{file_path}' is not a file."
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        stats = {
            'file': str(path.absolute()),
            'key_count': count_keys(data),
            'value_types': get_value_types(data),
            'max_depth': get_max_depth(data),
        }
        
        return stats, ""
    
    except json.JSONDecodeError as e:
        return {}, f"Error: Invalid JSON in '{file_path}': {str(e)}"
    except UnicodeDecodeError:
        return {}, f"Error: File '{file_path}' is not valid UTF-8 encoded."
    except Exception as e:
        return {}, f"Error: Failed to read file '{file_path}': {str(e)}"


def format_statistics(stats: Dict[str, Any]) -> str:
    """
    Format statistics for display.
    
    Args:
        stats: Dictionary containing statistics from analyze_json_file.
        
    Returns:
        Formatted string for display.
    """
    output = []
    output.append(f"File: {stats['file']}")
    output.append(f"Total Key Count: {stats['key_count']}")
    output.append(f"Maximum Nesting Depth: {stats['max_depth']}")
    output.append("\nValue Type Breakdown:")
    
    type_counts = stats['value_types']
    type_order = ['string', 'int', 'float', 'bool', 'null', 'list', 'dict']
    
    for type_name in type_order:
        count = type_counts.get(type_name, 0)
        output.append(f"  {type_name}: {count}")
    
    return "\n".join(output)


def main():
    """Main entry point for the CLI tool."""
    parser = argparse.ArgumentParser(
        description='Analyze JSON files and display statistics.'
    )
    parser.add_argument(
        'file',
        help='Path to the JSON file to analyze'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Display additional information'
    )
    
    args = parser.parse_args()
    
    stats, error = analyze_json_file(args.file)
    
    if error:
        print(error, file=sys.stderr)
        sys.exit(1)
    
    output = format_statistics(stats)
    print(output)
    
    if args.verbose:
        print(f"\nVerbose Info:")
        print(f"  Raw value types: {stats['value_types']}")


if __name__ == '__main__':
    main()
