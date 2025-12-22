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
        moid: .moid
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

**Note**: The generator uses a **single identifier** in `canonical_facts` (e.g., `moid` for VMware). This is critical for proper deduplication when multiple modules interact with the same resource in a job.

## Integrating with a Collection

The generated `event_query.yml` file must be placed in the collection's `extensions/audit/` directory.

### Step 1: Fork and Modify

1. Fork the target collection (e.g., `vmware.vmware`)
2. Add the generated file:
   ```bash
   mkdir -p extensions/audit
   cp vmware_vmware_event_query.yml extensions/audit/event_query.yml
   ```
3. Commit and push to your fork

### Step 2: Use Git-based Collection in AAP

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
  id   |            created            |   name   |   canonical_facts    |                                     facts                                      |                                            events                                            | count | job_id | organization_id 
-------+-------------------------------+----------+----------------------+--------------------------------------------------------------------------------+----------------------------------------------------------------------------------------------+-------+--------+-----------------
 13444 | 2025-12-22 16:29:14.052044+00 | vm-10440 | {"moid": "vm-10440"} | {"infra_type": "PrivateCloud", "device_type": "VM", "infra_bucket": "Compute"} | ["community.vmware.vmware_guest", "vmware.vmware.vm_powerstate", "vmware.vmware.guest_info"] |     3 |  16747 |               1
```

### Understanding the Results

The `main_indirectmanagednodeaudit` table aggregates all module interactions with a resource into a **single record per job**:

| Column | Description |
|--------|-------------|
| `name` | Primary identifier (e.g., VM moid) |
| `canonical_facts` | Single identifier used for deduplication |
| `facts` | Resource metadata (infra_type, device_type, infra_bucket) |
| `events` | **Array of all modules that touched this resource** |
| `count` | **Total number of module interactions** |
| `job_id` | The job that performed the automation |

**Key Insight**: In the example above, VM `vm-10440` was touched by **3 different modules** in a single job:
1. `community.vmware.vmware_guest` - Created the VM
2. `vmware.vmware.vm_powerstate` - Changed power state  
3. `vmware.vmware.guest_info` - Gathered VM information

Despite 3 module calls, this counts as **1 indirect managed node** because it's the same VM. The `events` array tracks which modules interacted with it, and `count` shows the total interactions.

### How Deduplication Works

AWX deduplicates records using `canonical_facts`. This generator uses a **single primary identifier** (e.g., `moid` for VMware) to ensure proper deduplication when multiple modules from different collections touch the same resource:

```yaml
# Both collections use the same identifier structure:
vmware.vmware.vm_powerstate:
  canonical_facts: { moid: .moid }

community.vmware.vmware_guest:
  canonical_facts: { moid: .moid }
```

This ensures that `vm-10440` from `vmware.vmware` and `vm-10440` from `community.vmware` are recognized as the **same node** and aggregated together.

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

3. **Finds Primary Identifier**: Searches for the highest-priority unique identifier field using this order:
   - `moid` (VMware)
   - `instance_uuid`
   - `hw_product_uuid` → mapped to `bios_uuid`
   - `uuid`
   - `arn` (AWS)
   - `resource_id`
   - `id`
   - `serial`
   - `name` (fallback)

4. **Uses Single Identifier**: Only ONE identifier is used in `canonical_facts` to ensure consistent deduplication across modules. This prevents duplicate key errors when multiple modules touch the same resource.

5. **Generates jq Queries**: Creates structured queries that extract:
   - `name`: Primary identifier for the node
   - `canonical_facts`: Single identifying attribute for deduplication
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
