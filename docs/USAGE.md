# Usage Guide

## Installation

```bash
git clone https://github.com/YOUR_ORG/query-file-generator.git
cd query-file-generator
pip install -r requirements.txt
ansible-galaxy collection install .
```

## Basic Usage

### From GitHub

```bash
cd playbooks
ansible-playbook generate_vmware_queries.yml
```

### From Local Collection

```bash
# Install collection first
ansible-galaxy collection install vmware.vmware

# Generate from local
ansible-playbook generate_from_local.yml
```

### With Debug Output

```bash
export DEBUG_PARSER=1
ansible-playbook generate_vmware_queries.yml
```

## Module Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `collection_source` | Yes | GitHub URL or local path |
| `collection_name` | No | namespace.collection format |
| `output_path` | No | Output file (default: ./event_query.yml) |
| `modules_to_analyze` | No | List of specific modules |

## Deployment

After generating:

```bash
# Copy to collection's audit directory
cp vmware_vmware_event_query.yml \
   ~/.ansible/collections/ansible_collections/vmware/vmware/extensions/audit/event_query.yml

# Test with playbook using the collection
ansible-playbook your-vmware-playbook.yml

# Verify in AAP Controller
# Subscription Management → Indirect Nodes
```

## Understanding the Output

### Successfully Parsed Modules

```yaml
vmware.vmware.vm: |
  .event_data.res | select(.!=null) | .vm.moid // empty
```

These have real identifiers found from RETURN documentation.

### Fallback Modules

```yaml
vmware.vmware.some_module: [FALLBACK] |
  .event_data.res | select(.!=null) | .id // empty
```

These modules had no identifiers in their RETURN docs.

## Troubleshooting

### GitHub Rate Limiting

Use local collection instead:

```bash
ansible-galaxy collection install vmware.vmware
ansible-playbook generate_from_local.yml
```

### All Modules Show [FALLBACK]

Enable debug to investigate:

```bash
export DEBUG_PARSER=1
ansible-playbook generate_vmware_queries.yml
```
