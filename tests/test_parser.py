#!/usr/bin/env python3
"""
Test script to verify the parser is finding identifiers correctly.
Run with: python3 -m pytest tests/ -v
Or directly: python3 tests/test_parser.py
"""

import pytest
import requests
import re
import yaml


def find_identifiers_in_sample(sample_data, path=""):
    """Find identifier fields in sample data"""
    identifiers = []
    
    if isinstance(sample_data, dict):
        for key, value in sample_data.items():
            current_path = f"{path}.{key}" if path else key
            key_lower = key.lower()
            
            is_id = any(term in key_lower for term in [
                'moid', 'uuid', 'guid', '_id',
                'instance_uuid', 'hw_product_uuid', 'product_uuid',
                'serial', 'arn'
            ])
            
            is_excluded = any(term in key_lower for term in [
                'enabled', 'needed', 'valid', 'available',
                'behavior', 'override', 'consolidat'
            ])
            
            if is_id and not is_excluded:
                identifiers.append({'path': current_path, 'name': key})
            
            if isinstance(value, dict):
                identifiers.extend(find_identifiers_in_sample(value, current_path))
    
    elif isinstance(sample_data, list) and sample_data:
        if isinstance(sample_data[0], dict):
            identifiers.extend(find_identifiers_in_sample(sample_data[0], path))
    
    return identifiers


def find_identifiers(yaml_data, path=""):
    """Find identifiers in RETURN structure AND sample data"""
    if not isinstance(yaml_data, dict):
        return []
    
    identifiers = []
    
    for key, value in yaml_data.items():
        current_path = f"{path}.{key}" if path else key
        
        if isinstance(value, dict):
            if 'contains' in value:
                identifiers.extend(find_identifiers(value['contains'], current_path))
            
            if 'sample' in value and value.get('sample'):
                sample_ids = find_identifiers_in_sample(value['sample'], current_path)
                identifiers.extend(sample_ids)
    
    return identifiers


def fetch_and_parse_module(module_name):
    """Fetch and parse a single module, return identifiers"""
    url = f"https://raw.githubusercontent.com/ansible-collections/vmware.vmware/main/plugins/modules/{module_name}.py"
    
    resp = requests.get(url, timeout=20)
    if resp.status_code != 200:
        return None, f"Failed to fetch: {resp.status_code}"
    
    content = resp.text
    
    # Find RETURN
    match = re.search(r"RETURN\s*=\s*r?'''(.*?)'''", content, re.DOTALL)
    if not match:
        return None, "No RETURN section"
    
    return_text = match.group(1).strip()
    yaml_data = yaml.safe_load(return_text)
    
    if not yaml_data:
        return None, "Empty YAML"
    
    identifiers = find_identifiers(yaml_data)
    return identifiers, None


# Pytest parametrized tests
@pytest.mark.parametrize("module_name", ['vm', 'guest_info', 'cluster_info', 'folder'])
def test_module_has_identifiers(module_name):
    """Test that modules can be parsed and have identifiers"""
    identifiers, error = fetch_and_parse_module(module_name)
    
    if error:
        pytest.skip(f"Could not parse module: {error}")
    
    assert identifiers is not None, f"No identifiers found for {module_name}"
    assert len(identifiers) > 0, f"Empty identifiers for {module_name}"


def test_guest_info_has_moid():
    """Test guest_info specifically has moid identifier"""
    identifiers, error = fetch_and_parse_module('guest_info')
    
    assert error is None, f"Parse error: {error}"
    assert identifiers is not None
    
    paths = [i['path'] for i in identifiers]
    assert any('moid' in p for p in paths), f"No moid found in {paths}"


def test_guest_info_has_uuid():
    """Test guest_info has uuid identifiers"""
    identifiers, error = fetch_and_parse_module('guest_info')
    
    assert error is None
    paths = [i['path'] for i in identifiers]
    assert any('uuid' in p.lower() for p in paths), f"No uuid found in {paths}"


# Direct execution support
def main():
    print("Query File Generator - Parser Test")
    print("=" * 60)
    
    modules = ['vm', 'guest_info', 'cluster_info', 'appliance_info', 'folder']
    
    for module in modules:
        print(f"\n{'='*60}")
        print(f"Testing: {module}")
        
        identifiers, error = fetch_and_parse_module(module)
        
        if error:
            print(f"❌ {error}")
        elif identifiers:
            print(f"✅ Found {len(identifiers)} identifier(s):")
            for ident in identifiers:
                print(f"   - {ident['path']}")
        else:
            print("⚠️  No identifiers found (would use fallback)")
    
    print(f"\n{'='*60}")
    print("Test complete!")


if __name__ == '__main__':
    main()
