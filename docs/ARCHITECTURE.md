# Query File Generator Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Query File Generator                          │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│  │  Collection  │───▶│  AI Analysis │───▶│   Generate   │     │
│  │ Introspection│    │   (Claude)   │    │  Query File  │     │
│  └──────────────┘    └──────────────┘    └──────────────┘     │
│          │                   │                    │            │
│          ▼                   ▼                    ▼            │
│    Fetch Docs          Identify IDs        event_query.yml    │
│    & Modules           & Resources                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Deploy to
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│            Ansible Collection with Audit Extension              │
│                                                                  │
│  my_collection/                                                  │
│  ├── plugins/modules/                                            │
│  │   ├── azure_vm.py                                            │
│  │   └── azure_disk.py                                          │
│  └── extensions/audit/                                           │
│      └── event_query.yml  ◀─── Generated file goes here        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Used by
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│         Ansible Automation Platform Controller                  │
│                                                                  │
│  ┌──────────────────────────────────────────────────┐          │
│  │  Job Execution                                     │          │
│  │                                                    │          │
│  │  1. Run playbook with collection modules          │          │
│  │  2. Capture task event stream                     │          │
│  │  3. Apply jq queries from event_query.yml         │          │
│  │  4. Extract unique resource identifiers           │          │
│  │  5. Count as indirect nodes                       │          │
│  └──────────────────────────────────────────────────┘          │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────┐          │
│  │  Subscription Management                          │          │
│  │                                                    │          │
│  │  - 50 direct nodes (SSH/WinRM)                    │          │
│  │  - 200 indirect nodes (API-managed):              │          │
│  │    * 100 Azure VMs                                │          │
│  │    * 50 VMware VMs                                │          │
│  │    * 30 Cisco switches                            │          │
│  │    * 20 AWS instances                             │          │
│  │                                                    │          │
│  │  Total: 250 nodes (subscription consumption)      │          │
│  └──────────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

## Component Flow

### 1. Collection Analysis Phase

```
User Input: Collection reference (GitHub URL, Galaxy name, or local path)
     │
     ▼
┌─────────────────┐
│ Fetch Collection│
│   Metadata      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Fetch Module   │
│  Documentation  │
│  & Source Code  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Parse DOCS    │
│    Extract:     │
│  - Return vals  │
│  - Examples     │
│  - Parameters   │
└────────┬────────┘
         │
         ▼
    Module Info
```

### 2. AI Analysis Phase

```
Module Documentation
         │
         ▼
┌──────────────────────┐
│   Claude AI Prompt:  │
│                      │
│   "Analyze these     │
│    modules and       │
│    identify:         │
│    1. Resources      │
│    2. Identifiers    │
│    3. jq paths"      │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│  AI Response:        │
│                      │
│  {                   │
│    "queries": [      │
│      {               │
│        "module": ... │
│        "resource":...│
│        "ids": [...]  │
│      }               │
│    ]                 │
│  }                   │
└──────────┬───────────┘
           │
           ▼
    Query Patterns
```

### 3. Query File Generation Phase

```
Query Patterns
     │
     ▼
┌─────────────────┐
│  Convert to     │
│  event_query    │
│  YAML format    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Validate:     │
│  - YAML syntax  │
│  - Required     │
│    fields       │
│  - jq syntax    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Write to file:  │
│ event_query.yml │
└─────────────────┘
```

## Data Flow Example: Azure VM Creation

### 1. Playbook Execution

```yaml
- name: Create Azure VM
  azure.azcollection.azure_rm_virtualmachine:
    resource_group: mygroup
    name: myvm
    vm_size: Standard_DS1_v2
    # ... other params
```

### 2. Task Completion Event

```json
{
  "event": "runner_on_ok",
  "event_data": {
    "task_action": "azure.azcollection.azure_rm_virtualmachine",
    "task_action_result": {
      "changed": true,
      "id": "/subscriptions/xxx/resourceGroups/mygroup/providers/Microsoft.Compute/virtualMachines/myvm",
      "properties": {
        "vmId": "12345678-1234-5678-1234-567812345678",
        "provisioningState": "Succeeded"
      }
    }
  }
}
```

### 3. Query Application

From `azure_event_query.yml`:
```yaml
- name: Azure Virtual Machine
  collection_pattern: "azure\\.azcollection\\.azure_rm_virtualmachine"
  queries:
    - name: vm_id
      jq_expression: '.event_data.task_action_result.id // empty'
    - name: vm_uuid
      jq_expression: '.event_data.task_action_result.properties.vmId // empty'
```

### 4. Extraction Results

```
Extracted Identifiers:
  vm_id: "/subscriptions/xxx/resourceGroups/mygroup/providers/Microsoft.Compute/virtualMachines/myvm"
  vm_uuid: "12345678-1234-5678-1234-567812345678"

Result: 1 indirect node counted
```

## Why This Matters

### Traditional Node Counting

```
┌──────────────────────────────────────────┐
│  Playbook runs against 10 hosts          │
│  - Direct SSH/WinRM connections          │
│  - Ansible connects to each host         │
│                                           │
│  ✓ 10 managed nodes counted              │
└──────────────────────────────────────────┘
```

### Indirect Node Counting

```
┌──────────────────────────────────────────┐
│  Playbook runs on localhost              │
│  - Calls Azure API to create 100 VMs     │
│  - Never connects to VMs directly        │
│  - Ansible manages via API only          │
│                                           │
│  Without queries: 0 nodes counted ✗      │
│  With queries: 100 nodes counted ✓       │
└──────────────────────────────────────────┘
```

### Hybrid Infrastructure

```
Direct Nodes (SSH/WinRM):
  - 10 Linux servers
  - 5 Windows servers
  = 15 direct nodes

Indirect Nodes (API-managed):
  - 100 Azure VMs (via azure.azcollection)
  - 50 VMware VMs (via vmware.vmware)
  - 30 Cisco switches (via cisco.ios)
  - 20 AWS instances (via amazon.aws)
  = 200 indirect nodes

Total Subscription Consumption: 215 nodes
```

## Module Architecture

### Core Module: generate_query_file.py

```python
class CollectionAnalyzer:
    """Main analyzer class"""
    
    def fetch_collection_docs(source):
        """
        Input: GitHub URL / Galaxy name / Local path
        Output: {
            'modules': [
                {'name': 'module_name', 'content': '...'},
                ...
            ]
        }
        """
    
    def analyze_with_ai(docs):
        """
        Input: Collection documentation
        Output: {
            'queries': [
                {
                    'module_pattern': 'regex',
                    'resource_type': 'vm|network|etc',
                    'identifier_queries': [...]
                },
                ...
            ]
        }
        """
    
    def generate_event_query_file(queries):
        """
        Input: Query patterns
        Output: event_query.yml file
        """
```

### Extensibility Points

1. **Custom Fetchers**: Add support for new collection sources
   ```python
   def _fetch_from_gitlab(self, url):
       # Implement GitLab API fetching
   ```

2. **Custom Analyzers**: Implement alternative analysis methods
   ```python
   def analyze_with_patterns(self, docs):
       # Pattern-based analysis without AI
   ```

3. **Custom Validators**: Add validation logic
   ```python
   def validate_queries(self, queries):
       # Validate jq expressions, patterns, etc.
   ```

## Performance Considerations

### AI Analysis Costs

- **Input**: ~5000 tokens per 10 modules
- **Output**: ~1000 tokens per response
- **Cost**: ~$0.015 per collection (with Claude Sonnet)
- **Time**: 2-5 seconds per collection

### Caching Strategy

```python
# Cache collection documentation
cache_key = f"{collection_name}:{version}"
if cache_key in cache:
    return cache[cache_key]

# Cache AI responses
response_cache[module_hash] = ai_response
```

## Security Considerations

1. **API Key Storage**: Never commit API keys
   ```bash
   # Use environment variables
   export ANTHROPIC_API_KEY="..."
   
   # Or Ansible Vault
   ansible-vault encrypt_string 'my-api-key' --name 'anthropic_api_key'
   ```

2. **Input Validation**: Sanitize collection sources
   ```python
   if not is_valid_url(collection_source):
       raise ValueError("Invalid collection source")
   ```

3. **Output Validation**: Verify generated queries
   ```python
   validate_yaml(query_file)
   validate_jq_expressions(queries)
   ```

## Testing Strategy

### Unit Tests
- Module documentation parsing
- AI response parsing
- YAML generation
- jq expression validation

### Integration Tests
- Full workflow with real collections
- AI API integration
- File system operations

### End-to-End Tests
- Generate query files
- Deploy to collections
- Run playbooks
- Verify node counting

## Future Enhancements

1. **Web UI**: Browser-based query file generator
2. **Validation Tool**: Test queries against real playbook runs
3. **Query Optimizer**: Suggest more efficient jq expressions
4. **Multi-Model Support**: Use multiple AI models for consensus
5. **Learning System**: Improve prompts based on user feedback

## Related Documentation

- [README.md](../README.md) - Full documentation
- [EVENT_QUERY_FORMAT.md](EVENT_QUERY_FORMAT.md) - Query file format
- [GETTING_STARTED.md](../GETTING_STARTED.md) - Quick start guide
