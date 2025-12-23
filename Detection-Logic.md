# Query File Generator - Container Type Detection Logic

## The Problem

Ansible modules return data in different structures:
- **Lists**: `[{item1}, {item2}, ...]` → requires `.container[]` in jq
- **Dicts**: `{key: value, ...}` → requires `.container | select(. != null)` in jq

Getting this wrong breaks indirect node counting:
- List treated as dict → no iteration, only one node counted
- Dict treated as list → jq error, no nodes counted

## Detection Signals (in order of reliability)

### 1. Explicit Type Declaration (HIGH confidence)
```yaml
RETURN:
  resourcegroups:
    type: list        # ← Explicit declaration
    returned: always
```
**Action**: Trust it completely.

### 2. Elements Field (HIGH confidence)
```yaml
RETURN:
  items:
    elements: dict    # ← Only appears for lists
    returned: always
```
**Action**: Treat as list.

### 3. Sample Data Structure (MEDIUM confidence)
```yaml
RETURN:
  guests:
    sample:           # ← Sample is a list
      - moid: "vm-1"
      - moid: "vm-2"
```
**Action**: Infer type from sample structure.

### 4. Contains Block Only (LOW confidence)
```yaml
RETURN:
  result:
    contains:         # ← Could be list or dict
      id:
        type: str
```
**Action**: Default to dict (safer), flag for review.

### 5. Module Name Inference (LOW confidence)
When RETURN doc is missing/unparseable:
- `azure_rm_*_info` → guess list with pluralized container
- `azure_rm_*` (action) → guess dict with `.state` container

**Action**: Make best guess, **flag for review**.

## Output Files

### event_query.yml
The generated queries file.

### event_query_REVIEW.txt
Lists modules with LOW confidence detection that need manual verification:
```
Module: azure.azcollection.azure_rm_storage_info
  Container: .storages
  Type: list
  Source: name_inference
  Note: UNVERIFIED Azure pattern (needs review)
```

## How to Verify Low-Confidence Detections

1. Run the module against real infrastructure
2. Examine the actual return data:
   ```bash
   ansible-playbook test.yml -v | grep "result:"
   ```
3. If return is `[{...}, {...}]` → type should be `list`
4. If return is `{...}` → type should be `dict`
5. Update event_query.yml accordingly

## Known Limitations

1. **Cannot detect type** when RETURN doc is missing AND module isn't Azure
2. **Azure inference is based on conventions** that may not always hold
3. **Sample data may be truncated** in documentation (list shown as single item)

## Recommendations

1. Always review the `_REVIEW.txt` file after generation
2. Test generated queries against actual module output
3. For critical collections, manually verify a sample of modules
4. Consider contributing improved RETURN docs upstream
