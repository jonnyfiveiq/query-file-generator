# AAP Event Query File Auto Generator

An Ansible collection that automatically generates `event_query.yml` files for AAP (Ansible Automation Platform) Indirect Node Counting.

This tool parses Ansible collection module RETURN documentation and generates the jq queries needed for AAP to extract and count managed infrastructure nodes from job events.

## Overview

AAP's Indirect Node Counting feature tracks infrastructure managed through automation (VMs, clusters, hosts, etc.) without requiring direct inventory entries. This generator automates the creation of the `event_query.yml` files that define how to extract node identifiers from module return data.

## Requirements

- Python 3.9+
- Ansible Core 2.14+
- Python packages: `requests`, `pyyaml`

## Installation

### Install the Collection

```bash
# Clone the repository
git clone https://github.com/jonnyfiveiq/query_file_auto_generator.git
cd query_file_auto_generator

# Install as Ansible collection
ansible-galaxy collection install . --force

# Or install dependencies for local development
pip install requests pyyaml
```

### Install from GitHub directly

```bash
ansible-galaxy collection install git+https://github.com/jonnyfiveiq/query_file_auto_generator.git
```

## Usage

### Generate Query File for VMware Collection

```bash
cd playbooks
ansible-playbook generate_vmware_queries.yml
```

This produces `vmware_vmware_event_query.yml` with queries for all VMware modules.

### Generate Query File for Azure Collection

```bash
ansible-playbook generate_azure_queries.yml
```

### Custom Collection

Create a playbook:

```yaml
---
- name: Generate event_query.yml for custom collection
  hosts: localhost
  gather_facts: false
  tasks:
    - name: Generate query file
      jonnyfiveiq.query_file_generator.generate_query_file:
        collection_name: "mycollection.myname"
        collection_source: "github"
        github_org: "ansible-collections"
        github_repo: "mycollection.myname"
        output_file: "mycollection_event_query.yml"
        infra_type: "MyCloud"
```

### Module Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `collection_name` | Yes | - | Collection name (e.g., `vmware.vmware`) |
| `collection_source` | No | `github` | Source type: `github` or `local` |
| `github_org` | No | `ansible-collections` | GitHub organization |
| `github_repo` | No | - | GitHub repository name |
| `local_path` | No | - | Local path to collection |
| `output_file` | No | `{collection}_event_query.yml` | Output filename |
| `infra_type` | No | `PrivateCloud` | Value for `facts.infra_type` |
| `debug` | No | `false` | Enable debug output |

## Example Output

Running the generator for `vmware.vmware` produces:

```yaml
---
vmware.vmware.cluster:
  query: >-
    .cluster | select(. != null) | {
      name: .moid,
      canonical_facts: {
        name: .name,
        moid: .moid
      },
      facts: {
        infra_type: "PrivateCloud",
        infra_bucket: "Compute",
        device_type: "Cluster"
      }
    }

vmware.vmware.guest_info:
  query: >-
    .guests[] | {
      name: .moid,
      canonical_facts: {
        name: .name,
        moid: .moid,
        instance_uuid: .instance_uuid,
        bios_uuid: .hw_product_uuid
      },
      facts: {
        infra_type: "PrivateCloud",
        infra_bucket: "Compute",
        device_type: "VM"
      }
    }

vmware.vmware.vm:
  query: >-
    .vm | select(. != null) | {
      name: .moid,
      canonical_facts: {
        name: .name,
        moid: .moid
      },
      facts: {
        infra_type: "PrivateCloud",
        infra_bucket: "Compute",
        device_type: "VM"
      }
    }

# ... additional modules
```

## Integrating with a Collection

The generated `event_query.yml` file must be placed in the collection's `extensions/audit/` directory.

### Option 1: Fork and Modify

1. Fork the target collection (e.g., `vmware.vmware`)
2. Add the generated file:
   ```bash
   mkdir -p extensions/audit
   cp vmware_vmware_event_query.yml extensions/audit/event_query.yml
   ```
3. Commit and push to your fork

### Option 2: Use Git-based Collection in AAP

Configure your AAP project to use a forked collection with the query file:

**requirements.yml:**
```yaml
collections:
  - name: https://github.com/jonnyfiveiq/vmware.vmware.git
    type: git
    version: main
  - name: https://github.com/jonnyfiveiq/community.vmware.git
    type: git
    version: main
```

This allows testing without modifying the upstream collection.

## Testing in AAP

### 1. Verify Feature Flag is Enabled

```bash
curl -k -u admin:password https://YOUR_AAP_HOST/api/controller/v2/feature_flags_state/ | jq .
```

Look for:
```json
{
  "FEATURE_INDIRECT_NODE_COUNTING_ENABLED": true
}
```

### 2. Run a Job Using the Collection

Run any playbook that uses modules from the collection (e.g., `vmware.vmware.vm_powerstate`).

### 3. Force Immediate Processing (Optional)

By default, indirect node data rolls up every 60 minutes. To force immediate processing:

```bash
# Access AWX shell
awx-manage shell_plus

# In the Python shell:
from awx.main.tasks.host_indirect import *
save_indirect_host_entries.delay(Job.objects.order_by('-created').first().id, wait_for_events=False)
```

### 4. Verify Query File Loaded

```bash
# Access PostgreSQL
awx-manage dbshell

# Check loaded queries
SELECT id, fqcn, collection_version FROM main_eventquery;
```

Example output:
```
 id |     fqcn      | collection_version 
----+---------------+--------------------
 16 | vmware.vmware | 1.11.0
```

To see the full query content:
```sql
SELECT * FROM main_eventquery;
```

### 5. Verify Indirect Nodes Counted

```sql
SELECT * FROM main_indirectmanagednodeaudit;
```

Example output:
```
  id   |            created            |   name   |              canonical_facts               |                        facts                         |             events              | count | job_id | organization_id 
-------+-------------------------------+----------+--------------------------------------------+------------------------------------------------------+---------------------------------+-------+--------+-----------------
 13402 | 2025-12-22 10:03:15.670548+00 | vm-10413 | {"moid": "vm-10413", "name": "deletemeVM"} | {"infra_type": "myCloud", "device_type": "VM", ...}  | ["vmware.vmware.vm_powerstate"] |     1 |  16687 |               1
 13403 | 2025-12-22 10:05:36.095925+00 | vm-10414 | {"moid": "vm-10414", "name": "deletemeVM"} | {"infra_type": "myCloud", "device_type": "VM", ...}  | ["vmware.vmware.vm_powerstate"] |     1 |  16689 |               1
```

### 6. Check Job Event Data (Debugging)

If nodes aren't being counted, check the raw event data:

```sql
SELECT 
    id,
    event_data::json->'resolved_action' as action,
    event_data::json->'res' as result
FROM main_jobevent 
WHERE event_data::text LIKE '%resolved_action%'
ORDER BY id DESC 
LIMIT 5;
```

## How It Works

1. **Parses RETURN Documentation**: The generator reads each module's RETURN docstring to understand the data structure returned by the module.

2. **Detects Container Type**: Identifies whether the return is a list (`type: list`) or dict (`type: dict`) to generate the correct jq accessor:
   - Lists: `.container[]` (iterate)
   - Dicts: `.container | select(. != null)` (access)

3. **Finds Identifiers**: Searches for unique identifier fields (moid, uuid, instance_id, arn, etc.) in both the RETURN schema and sample data.

4. **Generates jq Queries**: Creates structured queries that extract:
   - `name`: Unique identifier for the node
   - `canonical_facts`: Key identifying attributes
   - `facts`: Metadata about the infrastructure type

## Supported Collections

Tested with:
- `vmware.vmware` - VMware vSphere modules
- `azure.azcollection` - Azure modules (partial)
- `amazon.aws` - AWS modules (partial)

The generator works with any collection that has properly documented RETURN sections with identifier fields.

## Troubleshooting

### No Indirect Nodes Counted

1. **Check feature flag**: Ensure `FEATURE_INDIRECT_NODE_COUNTING_ENABLED` is `true`
2. **Check query loaded**: Verify `main_eventquery` has your collection
3. **Check event data**: Ensure `resolved_action` matches the FQCN in your queries
4. **Force processing**: Use the shell command to process immediately

### Query File Not Loading

- Ensure the file is at `extensions/audit/event_query.yml` in the collection
- Check the collection is installed correctly in the EE
- Verify YAML syntax is valid

### jq Query Errors

Test your queries locally:
```bash
echo '{"guests": [{"moid": "vm-123", "name": "test"}]}' | jq '.guests[] | {name: .moid}'
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `python -m pytest tests/`
5. Submit a pull request

## License

Apache License 2.0

## Related Resources

- [AAP Documentation](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/)
- [Ansible Collections Developer Guide](https://docs.ansible.com/ansible/latest/dev_guide/developing_collections.html)
- [jq Manual](https://stedolan.github.io/jq/manual/)
