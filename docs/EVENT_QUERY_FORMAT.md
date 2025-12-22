# Event Query File Format Documentation

## Overview

The `event_query.yml` file defines patterns for extracting unique resource identifiers from Ansible playbook execution event streams. This enables Ansible Automation Platform Controller to count "indirect nodes" - resources managed through third-party APIs.

## File Structure

```yaml
extension_name: <namespace>.<collection>_audit
extension_version: <semver>
description: <text>
queries:
  - name: <resource type name>
    query_type: jq
    collection_pattern: <regex>
    resource_type: <category>
    queries:
      - name: <identifier name>
        description: <text>
        jq_expression: <jq path>
```

## Field Definitions

### Top Level

#### `extension_name` (required)
- **Type**: string
- **Format**: `<namespace>.<collection>_audit`
- **Description**: Unique identifier for this audit extension
- **Example**: `azure.azcollection_audit`, `vmware.vmware_audit`

#### `extension_version` (required)
- **Type**: string
- **Format**: Semantic versioning (MAJOR.MINOR.PATCH)
- **Description**: Version of this audit extension
- **Example**: `1.0.0`, `2.1.3`

#### `description` (required)
- **Type**: string
- **Description**: Human-readable description of what this extension audits
- **Example**: "Audit queries for Azure collection to count indirect nodes"

### Query Entry

#### `name` (required)
- **Type**: string
- **Description**: Human-readable name for the resource type being tracked
- **Example**: "Azure Virtual Machine", "Cisco IOS Router", "VMware vSphere Cluster"

#### `query_type` (required)
- **Type**: string
- **Values**: `jq` (currently only supported value)
- **Description**: Type of query expression used
- **Note**: Future versions may support other query languages

#### `collection_pattern` (required)
- **Type**: string (regex pattern)
- **Description**: Regular expression to match fully qualified collection names (FQCN) of modules
- **Format**: Escape dots with double backslashes: `\\.`
- **Examples**:
  - `azure\\.azcollection\\.azure_rm_virtualmachine` - Matches specific module
  - `vmware\\.vmware\\.(vmware_guest|vm)` - Matches multiple modules via alternation
  - `cisco\\.ios\\.ios_.*` - Matches all ios_ modules
  - `.*\\.my_module` - Matches module in any namespace

#### `resource_type` (required)
- **Type**: string
- **Description**: Category of resource being managed
- **Common Values**:
  - `virtual_machine` - VMs, instances, compute resources
  - `network_device` - Switches, routers, firewalls, APs
  - `network_interface` - NICs, vNICs, network adapters
  - `network_resource` - VPCs, subnets, security groups, load balancers
  - `storage` - Disks, volumes, datastores, buckets
  - `database` - Database instances, clusters
  - `container` - Containers, pods, container orchestration
  - `container_cluster` - Kubernetes, OpenShift, ECS clusters
  - `compute_host` - Physical servers, hypervisors
  - `cluster` - Server clusters, availability sets
  - `resource_group` - Organizational containers
  - `managed_node` - Generic managed resource

#### `queries` (required)
- **Type**: array of query objects
- **Description**: List of identifier extraction patterns

### Identifier Query

#### `name` (required)
- **Type**: string
- **Description**: Name of the identifier field
- **Examples**: `vm_uuid`, `device_serial`, `resource_id`, `moid`

#### `description` (required)
- **Type**: string
- **Description**: Human-readable description of what this identifier represents
- **Example**: "Azure VM Resource ID", "Device serial number", "vSphere MOID"

#### `jq_expression` (required)
- **Type**: string (jq query)
- **Description**: jq expression to extract the identifier from event data
- **Context**: Executed against the full event payload from Ansible Controller
- **Must return**: String identifier or `empty` if not found

## Event Data Structure

Ansible Controller provides event data in this structure:

```json
{
  "event": "runner_on_ok",
  "event_data": {
    "host": "localhost",
    "task": "Create Azure VM",
    "task_action": "azure.azcollection.azure_rm_virtualmachine",
    "task_action_result": {
      "changed": true,
      "id": "/subscriptions/.../virtualMachines/vm1",
      "state": {
        "properties": {
          "vmId": "12345678-1234-5678-1234-567812345678"
        }
      }
    },
    "task_args": {
      "name": "vm1",
      "resource_group": "mygroup"
    }
  },
  "host": "localhost",
  "resolved_action": "azure.azcollection.azure_rm_virtualmachine",
  "uuid": "event-uuid-here"
}
```

## JQ Expression Patterns

### Basic Path Access

```jq
.event_data.task_action_result.id
```
Accesses: `event_data` → `task_action_result` → `id`

### Alternative Operator

```jq
.event_data.task_action_result.id // empty
```
Returns the value if it exists, otherwise returns `empty` (no output)

### Multiple Alternatives

```jq
.event_data.task_action_result.id // .event_data.task_action_result.state.id // empty
```
Tries first path, if null/missing tries second path, finally returns empty

### Nested Object Access

```jq
.event_data.task_action_result.state.properties.vmId
```
Navigates through nested objects

### Array Access

```jq
.event_data.task_action_result.instances[0].id
```
Gets first element from array

### Complex Example

```jq
.event_data.task_action_result.ansible_facts.azure_vm.id // .event_data.task_action_result.id // empty
```
Comprehensive pattern checking multiple common locations

## Best Practices

### 1. Use Specific Patterns

**Good**:
```yaml
collection_pattern: "azure\\.azcollection\\.azure_rm_virtualmachine"
```

**Avoid** (too broad):
```yaml
collection_pattern: ".*virtualmachine.*"
```

### 2. Provide Fallbacks

Always use `// empty` at the end:
```jq
.event_data.task_action_result.id // empty
```

Try multiple common locations:
```jq
.primary.path // .secondary.path // .tertiary.path // empty
```

### 3. Resource Type Accuracy

Match resource_type to what's actually being counted:
- One VM = `virtual_machine`
- One switch = `network_device`  
- One load balancer = `network_resource`

### 4. Multiple Identifiers Per Resource

When a resource has multiple unique identifiers, include them all:

```yaml
queries:
  - name: vm_moid
    description: VMware Managed Object ID
    jq_expression: '.event_data.task_action_result.instance._moId // empty'
  
  - name: vm_uuid
    description: Virtual Machine Instance UUID
    jq_expression: '.event_data.task_action_result.instance.instance_uuid // empty'
```

Controller will deduplicate based on any matching identifier.

### 5. Correlation Fields

Include non-unique fields for correlation/debugging:

```yaml
- name: vm_name
  description: Virtual Machine Name (for correlation)
  jq_expression: '.event_data.task_action_result.instance.hw_name // empty'
```

## Testing JQ Expressions

### Using jq CLI

Create sample event data:
```bash
cat > test_event.json << 'EOF'
{
  "event_data": {
    "task_action_result": {
      "id": "/subscriptions/xxx/virtualMachines/vm1",
      "properties": {
        "vmId": "12345678-1234-5678-1234-567812345678"
      }
    }
  }
}
EOF
```

Test your expression:
```bash
jq '.event_data.task_action_result.id // empty' test_event.json
```

### Testing in Playbooks

```yaml
- name: Test jq expression
  ansible.builtin.shell: |
    echo '{{ event_json | to_json }}' | jq '{{ jq_expression }}'
  vars:
    event_json:
      event_data:
        task_action_result:
          id: "/subscriptions/xxx/vm1"
    jq_expression: '.event_data.task_action_result.id // empty'
```

## Common Patterns by Platform

### Cloud Providers (Azure, AWS, GCP)

Resource IDs are typically long strings:
```jq
.event_data.task_action_result.id // .event_data.task_action_result.state.id // empty
```

### VMware vSphere

MOIDs and UUIDs:
```jq
.event_data.task_action_result.instance._moId // empty
.event_data.task_action_result.instance.instance_uuid // empty
```

### Network Devices

Serial numbers and management IPs:
```jq
.event_data.task_action_result.ansible_facts.ansible_net_serialnum // empty
.event_data.host // empty
```

### Containers

Container IDs and names:
```jq
.event_data.task_action_result.container.Id // empty
.event_data.task_action_result.Id // empty
```

## Validation

### YAML Schema Validation

```yaml
# Use yamllint or similar
yamllint event_query.yml
```

### Structural Requirements

1. ✅ Valid YAML syntax
2. ✅ All required fields present
3. ✅ `collection_pattern` is valid regex
4. ✅ `jq_expression` is valid jq syntax
5. ✅ At least one query entry
6. ✅ Each query has at least one identifier

### Testing with Real Data

1. Deploy query file to collection
2. Run a playbook using that collection
3. Check Controller logs for extracted identifiers
4. Verify subscription counting reflects expected nodes

## Deployment

### Collection Structure

```
my.collection/
├── plugins/
│   └── modules/
│       └── ...
├── extensions/
│   └── audit/
│       └── event_query.yml   # ← Deploy here
├── galaxy.yml
└── README.md
```

### Installation

```bash
# Copy generated file
cp generated_event_query.yml \
   ~/.ansible/collections/ansible_collections/my/collection/extensions/audit/event_query.yml

# Or in collection development
mkdir -p extensions/audit
cp event_query.yml extensions/audit/
ansible-galaxy collection build
ansible-galaxy collection install my-collection-1.0.0.tar.gz
```

## Examples

See the `examples/` directory for complete working examples:
- `azure_event_query.yml` - Azure cloud resources
- `vmware_event_query.yml` - VMware vSphere infrastructure
- `cisco_ios_event_query.yml` - Cisco network devices

## Troubleshooting

### Identifiers Not Being Extracted

1. **Check module output**: Run module with `-vvv` to see actual return values
2. **Verify path**: Ensure jq path matches actual data structure
3. **Test expression**: Use `jq` CLI to validate expression
4. **Check pattern**: Ensure `collection_pattern` matches FQCN

### Incorrect Node Counts

1. **Review resource_type**: Ensure it matches what's being counted
2. **Check deduplication**: Multiple identifiers should point to same resource
3. **Verify uniqueness**: Identifier must be unique per resource
4. **Check scope**: Some resources might be regional vs. global

### Query File Not Loading

1. **Verify location**: Must be in `extensions/audit/event_query.yml`
2. **Check syntax**: Run `yamllint` to validate YAML
3. **Review logs**: Check Controller logs for parsing errors
4. **Collection version**: Ensure collection version supports audit extensions

## References

- [jq Manual](https://stedolan.github.io/jq/manual/)
- [Ansible Module Development](https://docs.ansible.com/ansible/latest/dev_guide/developing_modules_general.html)
- [YAML Specification](https://yaml.org/spec/1.2/spec.html)
- [Ansible Automation Platform Documentation](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/)
