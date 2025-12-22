#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = r'''
---
module: generate_query_file
short_description: Generate event_query.yml by parsing module RETURN docs
description:
  - Introspects Ansible collection modules
  - Parses RETURN documentation to find resource identifiers
  - Checks both 'contains' structures AND 'sample' data
  - Generates event_query.yml for AAP indirect node counting
version_added: "1.0.0"
options:
  collection_source:
    description: GitHub URL or local path to collection
    required: true
    type: str
  collection_name:
    description: Collection name (namespace.collection)
    required: false
    type: str
  output_path:
    description: Output file path
    required: false
    type: str
    default: './event_query.yml'
  modules_to_analyze:
    description: Specific modules to analyze
    required: false
    type: list
    elements: str
author:
  - Ansible Automation Platform Team
'''

EXAMPLES = r'''
- name: Generate from GitHub
  ansible_bu.query_file_generator.generate_query_file:
    collection_source: "https://github.com/ansible-collections/vmware.vmware"
    collection_name: "vmware.vmware"
    output_path: "./vmware_event_query.yml"

- name: Generate from local
  ansible_bu.query_file_generator.generate_query_file:
    collection_source: "/path/to/collection"
    collection_name: "vmware.vmware"
    output_path: "./vmware_event_query.yml"
'''

RETURN = r'''
query_file_path:
    description: Path to generated file
    returned: always
    type: str
modules_analyzed:
    description: Number of modules analyzed
    returned: always
    type: int
queries_generated:
    description: Number of queries generated
    returned: always
    type: int
collection_info:
    description: Collection information
    returned: always
    type: dict
'''

from ansible.module_utils.basic import AnsibleModule
import os
import re
import sys

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


def debug(msg):
    """Print debug if DEBUG_PARSER is set"""
    if os.environ.get('DEBUG_PARSER', '').lower() in ('1', 'true', 'yes'):
        print(f"DEBUG: {msg}", file=sys.stderr)


def fetch_from_github(github_url, collection_name=None):
    """Fetch modules from GitHub"""
    match = re.search(r'github\.com/([^/]+)/([^/]+)', github_url)
    if not match:
        return {'error': 'Invalid GitHub URL'}
    
    org, repo = match.groups()
    repo = repo.rstrip('/')
    
    debug(f"Fetching {org}/{repo} from GitHub")
    
    result = {
        'source': 'github',
        'collection_name': collection_name or f"{org}.{repo}",
        'modules': []
    }
    
    api_url = f"https://api.github.com/repos/{org}/{repo}/contents/plugins/modules"
    
    try:
        resp = requests.get(api_url, timeout=20)
        if resp.status_code != 200:
            return {'error': f'GitHub API: {resp.status_code}'}
        
        files = resp.json()
        debug(f"Found {len(files)} files")
        
        for file_info in files:
            if not file_info['name'].endswith('.py') or file_info['name'] == '__init__.py':
                continue
            
            module_name = file_info['name'][:-3]
            raw_url = file_info['download_url']
            
            try:
                content_resp = requests.get(raw_url, timeout=20)
                if content_resp.status_code == 200:
                    content = content_resp.text
                    debug(f"  {module_name}: {len(content)} bytes")
                    result['modules'].append({'name': module_name, 'content': content})
            except Exception as e:
                debug(f"  {module_name}: Error - {e}")
                
    except Exception as e:
        return {'error': f'GitHub fetch failed: {str(e)}'}
    
    if not result['modules']:
        return {'error': 'No modules found'}
    
    return result


def fetch_from_local(path, collection_name=None):
    """Fetch from local filesystem"""
    modules_path = os.path.join(path, 'plugins', 'modules')
    if not os.path.isdir(modules_path):
        return {'error': f'No plugins/modules in {path}'}
    
    debug(f"Fetching from {modules_path}")
    
    result = {
        'source': 'local',
        'collection_name': collection_name or os.path.basename(path),
        'modules': []
    }
    
    for filename in os.listdir(modules_path):
        if not filename.endswith('.py') or filename == '__init__.py':
            continue
        
        module_name = filename[:-3]
        filepath = os.path.join(modules_path, filename)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                debug(f"  {module_name}: {len(content)} bytes")
                result['modules'].append({'name': module_name, 'content': content})
        except Exception as e:
            debug(f"  {module_name}: Error - {e}")
    
    if not result['modules']:
        return {'error': 'No modules found'}
    
    return result


def extract_return_section(content):
    """Extract RETURN section from module content"""
    patterns = [
        r'RETURN\s*=\s*r?"""(.*?)"""',
        r"RETURN\s*=\s*r?'''(.*?)'''",
        r'RETURN\s*=\s*r?"(.*?)"',
        r"RETURN\s*=\s*r?'(.*?)'",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
    
    return None


def find_identifiers_in_sample(sample_data, path="", depth=0):
    """Find identifier fields in sample data.
    
    Sample data often has structure like:
      DC0_C0:           # This is an example key, not a field name
        moid: "..."     # This is the actual field
        name: "..."
    
    We only want the actual field names, not the example keys.
    """
    identifiers = []
    
    if isinstance(sample_data, dict):
        for key, value in sample_data.items():
            key_lower = key.lower()
            
            # Skip keys that look like example/sample identifiers (not real field names)
            # These are typically: hostnames, cluster names, UUIDs as keys, numbered items
            looks_like_example_key = (
                '.' in key or                          # hostname like esxi01.example.com
                key.startswith('DC') or                # DC0_C0 style cluster names
                key.startswith('Sample_') or          # Sample_Tag_0002
                key.startswith('My-') or              # My-Cluster, My-VM style
                key[0].isdigit() or                   # 0, 1, 2 (array-like keys)
                (len(key) > 20 and '-' in key) or     # UUID-like keys
                '_C' in key or '_H' in key or         # DC0_C0_H0 patterns
                (key[0].isupper() and '-' in key) or  # Capitalized-With-Dashes
                (key[0].isupper() and '_' in key)     # Capitalized_With_Underscores
            )
            
            # If this looks like an example key and value is a dict, 
            # skip the key and look inside the value directly
            if looks_like_example_key and isinstance(value, dict):
                # Don't add this key to path, just recurse into value
                identifiers.extend(find_identifiers_in_sample(value, path, depth + 1))
                continue
            
            # Build path for real field names - but only use the key itself, not nested path
            # This ensures we get clean field names like 'moid' not 'cluster.moid'
            current_path = key  # Just use the key, not the full path
            
            # Check for identifier field names
            # Be more specific: match exact patterns, not just substrings
            is_id = False
            if key_lower in ['moid', 'uuid', 'id', 'arn', 'serial', 'guid']:
                is_id = True
            elif key_lower.endswith('_uuid') or key_lower.endswith('_id') or key_lower.endswith('_moid'):
                is_id = True
            elif key_lower in ['instance_uuid', 'hw_product_uuid', 'product_uuid', 'resource_id']:
                is_id = True
            
            # Exclude false positives
            is_excluded = any(term in key_lower for term in [
                'enabled', 'needed', 'valid', 'available',
                'behavior', 'override', 'consolidat', 'vlan_id'
            ])
            
            if is_id and not is_excluded:
                identifiers.append({'path': current_path, 'name': key})
            
            # Recurse into nested dicts (but not too deep)
            if isinstance(value, dict) and depth < 2:
                identifiers.extend(find_identifiers_in_sample(value, current_path, depth + 1))
    
    elif isinstance(sample_data, list) and sample_data:
        # Check first item of list
        if isinstance(sample_data[0], dict):
            identifiers.extend(find_identifiers_in_sample(sample_data[0], path, depth))
    
    return identifiers


def find_identifiers(yaml_data, path=""):
    """Recursively find identifier fields in RETURN structure AND sample data"""
    if not isinstance(yaml_data, dict):
        return []
    
    identifiers = []
    
    for key, value in yaml_data.items():
        current_path = f"{path}.{key}" if path else key
        key_lower = key.lower()
        
        # Check if field name suggests an identifier
        is_id = any(term in key_lower for term in [
            'moid', 'uuid', 'guid', '_id', 'serial', 'arn'
        ])
        
        # Add identifier if name matches - don't require it to be a dict
        if is_id:
            # Exclude false positives
            is_excluded = any(term in key_lower for term in [
                'enabled', 'needed', 'valid', 'available',
                'behavior', 'override', 'consolidat', 'vlan_id'
            ])
            if not is_excluded:
                identifiers.append({'path': current_path, 'name': key})
        
        if isinstance(value, dict):
            # Check 'contains' blocks (standard Ansible format)
            if 'contains' in value:
                identifiers.extend(find_identifiers(value['contains'], current_path))
            
            # Check 'sample' data (vmware.vmware format)
            if 'sample' in value and value.get('sample'):
                sample_ids = find_identifiers_in_sample(value['sample'], current_path)
                debug(f"  Found {len(sample_ids)} IDs in sample for '{key}'")
                identifiers.extend(sample_ids)
            
            # Check nested type: dict
            if 'type' in value and value['type'] == 'dict':
                nested = {k: v for k, v in value.items() 
                         if k not in ['type', 'description', 'returned', 'sample', 'elements']}
                if nested:
                    identifiers.extend(find_identifiers(nested, current_path))
    
    return identifiers


def analyze_module(module_name, content):
    """Analyze single module"""
    debug(f"\n=== {module_name} ===")
    
    return_text = extract_return_section(content)
    
    if not return_text:
        debug("  No RETURN section")
        return {
            'module_name': module_name,
            'identifiers': [{'path': 'id', 'name': 'id'}],
            'container_info': {},
            'fallback': True
        }
    
    debug(f"  RETURN: {len(return_text)} chars")
    
    try:
        yaml_data = yaml.safe_load(return_text)
        if not yaml_data or not isinstance(yaml_data, dict):
            debug("  Invalid RETURN YAML")
            return {
                'module_name': module_name,
                'identifiers': [{'path': 'id', 'name': 'id'}],
                'container_info': {},
                'fallback': True
            }
    except Exception as e:
        debug(f"  YAML error: {e}")
        return {
            'module_name': module_name,
            'identifiers': [{'path': 'id', 'name': 'id'}],
            'container_info': {},
            'fallback': True
        }
    
    # Find the primary container and its type
    container_info = {}
    for key, value in yaml_data.items():
        if isinstance(value, dict):
            container_type = value.get('type', 'dict')
            # Check if this looks like the main return container
            if container_type in ['list', 'dict'] and value.get('returned'):
                container_info = {
                    'name': key,
                    'type': container_type
                }
                debug(f"  Container: {key} (type={container_type})")
                break
    
    identifiers = find_identifiers(yaml_data)
    debug(f"  Found {len(identifiers)} identifiers: {[i['path'] for i in identifiers]}")
    
    if not identifiers:
        # For known container patterns, use default identifiers
        # 'instance' is a common pattern for VM modules in vmware collections
        for key in yaml_data.keys():
            if key.lower() == 'instance':
                debug(f"  Using default VM identifiers for 'instance' container")
                return {
                    'module_name': module_name,
                    'identifiers': [
                        {'path': 'moid', 'name': 'moid'},
                        {'path': 'instance_uuid', 'name': 'instance_uuid'},
                        {'path': 'hw_product_uuid', 'name': 'hw_product_uuid'}
                    ],
                    'container_info': {'name': 'instance', 'type': 'dict'},
                    'fallback': False
                }
        return {
            'module_name': module_name,
            'identifiers': [{'path': 'id', 'name': 'id'}],
            'container_info': container_info,
            'fallback': True
        }
    
    return {
        'module_name': module_name,
        'identifiers': identifiers,
        'container_info': container_info,
        'fallback': False
    }


def build_jq_query(identifiers):
    """Build jq query from identifiers (legacy, kept for compatibility)"""
    paths = [i['path'] for i in identifiers]
    
    if len(paths) > 5:
        paths = paths[:5]
    
    common_parent = None
    if all('.' in p for p in paths):
        parents = [p.split('.')[0] for p in paths]
        if len(set(parents)) == 1:
            common_parent = parents[0]
    
    if common_parent:
        sub_paths = ['.'.join(p.split('.')[1:]) for p in paths]
        return f".event_data.res.{common_parent} | select(.!=null) | .{' // .'.join(sub_paths)} // empty"
    else:
        return f".event_data.res | select(.!=null) | .{' // .'.join(paths)} // empty"


def build_structured_query(module_data):
    """Build structured jq query in AAP format with name, canonical_facts, facts"""
    identifiers = module_data['identifiers']
    module_name = module_data['module_name']
    container_info = module_data.get('container_info', {})
    
    # Get container name and type from analysis
    container = container_info.get('name')
    container_type = container_info.get('type', 'dict')  # 'list' or 'dict'
    
    # Fallback: try to get container from identifier paths
    if not container:
        paths = [i['path'] for i in identifiers]
        if paths and '.' in paths[0]:
            container = paths[0].split('.')[0]
    
    # Determine device type based on module name
    if 'guest' in module_name or 'vm' in module_name:
        device_type = "VM"
        infra_bucket = "Compute"
    elif 'host' in module_name or 'esxi' in module_name:
        device_type = "ESXi"
        infra_bucket = "Compute"
    elif 'cluster' in module_name:
        device_type = "Cluster"
        infra_bucket = "Compute"
    elif 'appliance' in module_name or 'vcsa' in module_name:
        device_type = "vCenter Appliance"
        infra_bucket = "Compute"
    elif 'folder' in module_name:
        device_type = "Folder"
        infra_bucket = "Management"
    elif 'datastore' in module_name:
        device_type = "Datastore"
        infra_bucket = "Storage"
    elif 'datacenter' in module_name:
        device_type = "Datacenter"
        infra_bucket = "Management"
    elif 'network' in module_name or 'dvs' in module_name or 'portgroup' in module_name:
        device_type = "Network"
        infra_bucket = "Network"
    else:
        device_type = "Resource"
        infra_bucket = "Compute"
    
    # Find available identifier fields - extract just the field name
    # After jq navigates into the container, we access fields directly
    available_fields = []
    for ident in identifiers:
        path = ident['path']
        # Get just the final field name (e.g., 'cluster.moid' -> 'moid', 'guests.instance_uuid' -> 'instance_uuid')
        # Skip any intermediate sample keys
        parts = path.split('.')
        
        # The actual field is typically the last part
        field = parts[-1]
        
        # Skip if field looks like a sample key
        if (field[0].isupper() or  # Capitalized like 'My-Cluster'
            field[0].isdigit() or  # Numbered like '0'
            '-' in field or        # Contains dash like 'vm-123'
            '.' in field):         # Contains dot (shouldn't happen after split)
            continue
            
        if field and field not in available_fields:
            available_fields.append(field)
    
    # Build canonical_facts with ONLY the primary identifier
    # IMPORTANT: AWX deduplicates on canonical_facts but DB constraint is (name, job_id)
    # Using multiple identifiers causes dedup mismatches when different modules
    # return the same resource with different field sets.
    # Solution: Use ONE consistent identifier per resource type.
    
    canonical_facts = []
    primary_id_field = None
    primary_canonical_name = None
    
    # Priority order for identifiers - pick FIRST match only
    id_priority = [
        ('moid', 'moid'),           # VMware primary identifier
        ('instance_uuid', 'instance_uuid'),
        ('hw_product_uuid', 'bios_uuid'),
        ('uuid', 'uuid'),
        ('arn', 'arn'),             # AWS primary identifier
        ('resource_id', 'resource_id'),
        ('id', 'id'),               # Generic fallback
        ('serial', 'serial'),
        ('name', 'name'),           # Last resort
    ]
    
    # Find the FIRST (highest priority) identifier available
    for field_name, canonical_name in id_priority:
        for f in available_fields:
            if f.lower() == field_name:
                primary_id_field = f".{f}"
                primary_canonical_name = canonical_name
                break
        if primary_id_field:
            break
    
    # If no identifier found, use first available field or fallback to .id
    if primary_id_field is None:
        if available_fields:
            first_field = available_fields[0]
            primary_id_field = f".{first_field}"
            primary_canonical_name = 'id'
        else:
            primary_id_field = ".id"
            primary_canonical_name = 'id'
    
    # Build canonical_facts with ONLY the primary identifier
    canonical_facts.append(f"    {primary_canonical_name}: {primary_id_field}")
    
    # Build the jq accessor based on type
    if container_type == 'list':
        # Array - iterate with []
        accessor = f".{container}[]" if container else ".[]"
    else:
        # Dict - select non-null
        accessor = f".{container} | select(. != null)" if container else ". | select(. != null)"
    
    query_lines = [
        f"{accessor} | {{",
        f"  name: {primary_id_field},",
        f"  canonical_facts: {{",
    ]
    query_lines.append(",\n".join(canonical_facts))
    query_lines.append("  },")
    query_lines.append("  facts: {")
    query_lines.append(f'    infra_type: "PrivateCloud",')
    query_lines.append(f'    infra_bucket: "{infra_bucket}",')
    query_lines.append(f'    device_type: "{device_type}"')
    query_lines.append("  }")
    query_lines.append("}")
    
    return '\n'.join(query_lines)


def generate_file(modules_data, collection_name, output_path):
    """Generate event_query.yml in the correct AAP format"""
    namespace, _, collection = collection_name.partition('.')
    if not collection:
        namespace, collection = collection_name, collection_name
    
    # Include all modules - even fallbacks get a basic query
    # Fallbacks just won't have good identifiers but might still work
    valid_modules = modules_data
    
    with open(output_path, 'w') as f:
        f.write("---\n")
        
        # Write each module with valid identifiers
        for module_data in valid_modules:
            module_name = module_data['module_name']
            full_name = f"{namespace}.{collection}.{module_name}"
            
            # Build the structured query
            query = build_structured_query(module_data)
            
            f.write(f"{full_name}:\n")
            f.write(f"  query: >-\n")
            for line in query.split('\n'):
                f.write(f"    {line}\n")
            f.write("\n")
    
    return len(valid_modules)


def main():
    module = AnsibleModule(
        argument_spec=dict(
            collection_source=dict(type='str', required=True),
            collection_name=dict(type='str', required=False),
            output_path=dict(type='str', default='./event_query.yml'),
            modules_to_analyze=dict(type='list', elements='str', required=False),
        ),
        supports_check_mode=True
    )
    
    if not HAS_REQUESTS:
        module.fail_json(msg='requests library required: pip install requests')
    if not HAS_YAML:
        module.fail_json(msg='PyYAML library required: pip install PyYAML')
    
    # Fetch collection
    source = module.params['collection_source']
    if source.startswith('http'):
        data = fetch_from_github(source, module.params.get('collection_name'))
    elif os.path.isdir(source):
        data = fetch_from_local(source, module.params.get('collection_name'))
    else:
        module.fail_json(msg=f'Invalid source: {source}')
    
    if 'error' in data:
        module.fail_json(msg=data['error'])
    
    # Filter modules
    modules = data['modules']
    if module.params.get('modules_to_analyze'):
        modules = [m for m in modules if m['name'] in module.params['modules_to_analyze']]
    
    # Analyze
    analyzed = [analyze_module(m['name'], m['content']) for m in modules]
    
    # Generate
    if not module.check_mode:
        queries_count = generate_file(
            analyzed,
            data['collection_name'],
            module.params['output_path']
        )
    else:
        queries_count = len(analyzed)
    
    # Count successes
    success_count = sum(1 for a in analyzed if not a.get('fallback', False))
    
    module.exit_json(
        changed=True,
        query_file_path=module.params['output_path'],
        modules_analyzed=len(modules),
        queries_generated=queries_count,
        successful_parses=success_count,
        collection_info={
            'name': data['collection_name'],
            'source': data['source']
        }
    )


if __name__ == '__main__':
    main()
