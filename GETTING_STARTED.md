# Getting Started with Query File Generator

This guide will walk you through generating your first audit query file.

## Prerequisites

1. **Ansible 2.9+** installed
2. **Python 3.8+** installed
3. **Anthropic API key** (get one at https://console.anthropic.com)

## Installation

### Step 1: Install the Collection

```bash
# From Ansible Galaxy (when published)
ansible-galaxy collection install ansible_bu.query_file_generator

# Or from source
git clone <this-repo>
cd query-file-generator
ansible-galaxy collection install .
```

### Step 2: Install Python Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `anthropic` - For AI analysis
- `requests` - For HTTP requests
- `PyYAML` - For YAML parsing

### Step 3: Set API Key

```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
```

Or store in `~/.bashrc` or `~/.zshrc`:
```bash
echo 'export ANTHROPIC_API_KEY="sk-ant-api03-..."' >> ~/.bashrc
source ~/.bashrc
```

## Quick Start: Generate Your First Query File

### Example 1: Azure Collection

Create a playbook `generate-azure.yml`:

```yaml
---
- name: Generate audit query for Azure
  hosts: localhost
  tasks:
    - name: Generate Azure query file
      ansible_bu.query_file_generator.generate_query_file:
        collection_source: "https://github.com/ansible-collections/azure"
        collection_name: "azure.azcollection"
        output_path: "./azure_event_query.yml"
```

Run it:
```bash
ansible-playbook generate-azure.yml
```

Output:
```
PLAY [Generate audit query for Azure] ******************************

TASK [Generate Azure query file] **********************************
changed: [localhost]

PLAY RECAP *********************************************************
localhost: ok=1 changed=1 unreachable=0 failed=0 skipped=0
```

### Example 2: VMware Collection

```yaml
---
- name: Generate VMware queries
  hosts: localhost
  tasks:
    - name: Generate VMware query file
      ansible_bu.query_file_generator.generate_query_file:
        collection_source: "vmware.vmware"
        output_path: "./vmware_event_query.yml"
```

### Example 3: Network Devices

```yaml
---
- name: Generate Cisco IOS queries
  hosts: localhost
  tasks:
    - name: Generate for specific modules
      ansible_bu.query_file_generator.generate_query_file:
        collection_source: "cisco.ios"
        modules_to_analyze:
          - ios_config
          - ios_interfaces
          - ios_vlans
        output_path: "./cisco_ios_query.yml"
```

## Understanding the Output

Generated file structure:
```yaml
extension_name: azure.azcollection_audit
extension_version: 1.0.0
description: Audit queries for azure.azcollection...

queries:
  - name: Azure Virtual Machine
    query_type: jq
    collection_pattern: "azure\\.azcollection\\.azure_rm_virtualmachine"
    resource_type: virtual_machine
    queries:
      - name: vm_id
        description: Azure VM Resource ID
        jq_expression: '.event_data.task_action_result.id // empty'
```

Key components:
- **collection_pattern**: Regex to match module names
- **resource_type**: Category of resource (VM, network device, etc.)
- **jq_expression**: Query to extract unique identifier

## Deploying Query Files

### Option 1: Install to Existing Collection

```bash
# Find collection path
ansible-galaxy collection list | grep azure.azcollection

# Copy query file
mkdir -p ~/.ansible/collections/ansible_collections/azure/azcollection/extensions/audit
cp azure_event_query.yml ~/.ansible/collections/ansible_collections/azure/azcollection/extensions/audit/event_query.yml
```

### Option 2: Include in Collection Development

```bash
# In your collection repository
mkdir -p extensions/audit
cp generated_event_query.yml extensions/audit/event_query.yml
git add extensions/audit/event_query.yml
git commit -m "Add audit query file"
```

### Option 3: Deploy to Ansible Automation Platform

1. Package the collection with query file:
   ```bash
   ansible-galaxy collection build
   ```

2. Upload to Automation Hub or Private Galaxy

3. Install in AAP:
   ```bash
   ansible-galaxy collection install my-collection-1.0.0.tar.gz
   ```

## Verifying It Works

### Test 1: Check File Structure

```bash
yamllint azure_event_query.yml
```

### Test 2: Test JQ Expressions

Create test data:
```bash
cat > test_event.json << 'EOF'
{
  "event_data": {
    "task_action_result": {
      "id": "/subscriptions/xxx/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
    }
  }
}
EOF
```

Test the expression:
```bash
jq '.event_data.task_action_result.id // empty' test_event.json
```

Should output:
```
"/subscriptions/xxx/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1"
```

### Test 3: Run with Ansible Controller

1. Deploy query file to collection
2. Run a playbook using that collection
3. Check Controller → Administration → Subscription Management
4. Verify indirect nodes are being counted

## Advanced Usage

### Generate for Multiple Collections

```yaml
---
- name: Batch generate query files
  hosts: localhost
  vars:
    collections:
      - { source: "azure.azcollection", output: "./azure_query.yml" }
      - { source: "amazon.aws", output: "./aws_query.yml" }
      - { source: "vmware.vmware", output: "./vmware_query.yml" }
      - { source: "cisco.ios", output: "./cisco_query.yml" }
  
  tasks:
    - name: Generate all query files
      ansible_bu.query_file_generator.generate_query_file:
        collection_source: "{{ item.source }}"
        output_path: "{{ item.output }}"
      loop: "{{ collections }}"
```

### Customize AI Analysis

For better results with complex collections:

```yaml
- name: Deep analysis with more context
  ansible_bu.query_file_generator.generate_query_file:
    collection_source: "https://github.com/my-org/complex-collection"
    collection_name: "my_org.complex"
    deep_analysis: true  # Analyzes return values in detail
    output_path: "./complex_query.yml"
```

### Fallback Mode (No AI)

If you don't have an Anthropic API key:

```yaml
- name: Generate with pattern matching
  ansible_bu.query_file_generator.generate_query_file:
    collection_source: "simple.collection"
    output_path: "./simple_query.yml"
    # No anthropic_api_key provided - uses fallback
```

Note: Fallback mode uses basic pattern matching and may miss some identifiers.

## Troubleshooting

### "anthropic module not found"

```bash
pip install anthropic
```

### "API key not found"

```bash
export ANTHROPIC_API_KEY="your-key-here"
```

### "No modules found in collection"

- Verify collection source URL/path
- Check that `plugins/modules/` directory exists
- Try specifying `collection_name` explicitly

### Generated queries seem wrong

1. Review the collection's module documentation
2. Test modules manually to see actual return values
3. Edit the generated query file manually
4. Submit feedback to improve AI prompts

## Next Steps

1. **Review Examples**: Check `examples/` directory for complete query files
2. **Read Format Docs**: See `docs/EVENT_QUERY_FORMAT.md` for detailed format info
3. **Test Queries**: Use `playbooks/test_generator.yml` to validate
4. **Deploy**: Add to your collections and start counting indirect nodes

## Common Workflows

### Workflow 1: New Collection Development

```bash
# 1. Generate query file
ansible-playbook -e "collection=my.newcollection" generate.yml

# 2. Review and edit
vim my_newcollection_event_query.yml

# 3. Add to collection
mkdir -p extensions/audit
cp my_newcollection_event_query.yml extensions/audit/event_query.yml

# 4. Test
ansible-playbook test_collection_with_queries.yml

# 5. Commit
git add extensions/audit/event_query.yml
git commit -m "Add audit queries"
```

### Workflow 2: Updating Existing Queries

```bash
# 1. Regenerate with latest collection
ansible-playbook generate.yml

# 2. Compare with existing
diff old_query.yml new_query.yml

# 3. Merge changes
# Keep your manual customizations, add new patterns from AI

# 4. Test updated file
ansible-playbook test_queries.yml
```

### Workflow 3: Multi-Platform Infrastructure

```bash
# Generate for all your platforms
ansible-playbook generate_all.yml

# This creates:
# - azure_query.yml
# - aws_query.yml  
# - vmware_query.yml
# - cisco_ios_query.yml
# - juniper_junos_query.yml
# etc.

# Deploy all to respective collections
ansible-playbook deploy_queries.yml
```

## Support

- **GitHub Issues**: https://github.com/ansible-collections/query-file-generator/issues
- **Ansible Forum**: https://forum.ansible.com
- **Documentation**: See `docs/` directory

## Resources

- [EVENT_QUERY_FORMAT.md](docs/EVENT_QUERY_FORMAT.md) - Detailed format documentation
- [README.md](README.md) - Full collection documentation
- [examples/](examples/) - Complete working examples
- [playbooks/](playbooks/) - Example playbooks
