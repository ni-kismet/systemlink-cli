# Routine Configuration Examples

Load this file when you need sanitized live examples for provider-specific
routine payloads beyond the minimal syntax in `commands.md`.

## v1 notebook routines

### Scheduled notebook execution

```bash
slcli routine create --api-version v1 \
  --name "Daily Notebook" \
  --type SCHEDULED \
  --notebook-id <NOTEBOOK_ID> \
  --schedule '{"startTime":"2026-01-01T00:00:00Z","repeat":"DAY"}'
```

### FILES trigger with compound filter

Observed v1 routines use the service-owned `trigger.filter` string directly.
This can be more expressive than the simple `extension=".xml"` example.

```json
{
  "trigger": {
    "source": "FILES",
    "events": ["CREATED"],
    "filter": "workspace = \"<WORKSPACE_ID>\" && (name.Contains(\"Specs\") && extension = \"xlsx\")"
  },
  "execution": {
    "type": "NOTEBOOK",
    "definition": {
      "notebookId": "<NOTEBOOK_ID>"
    }
  }
}
```

Notes:

- Keep the v1 filter string in the service's own syntax.
- Observed FILES filters can combine workspace checks, `name.Contains(...)`, and extension checks.

## v2 event-action routines

### TAG alarm with structured trigger fields

Observed TAG routines can use comparator-driven configuration instead of a
string `filter`.

```json
{
  "event": {
    "type": "TAG",
    "triggers": [
      {
        "configuration": {
          "comparator": "IN_RANGE",
          "deadband": 2,
          "path": "*.path.to.tag",
          "thresholds": ["1", "12"],
          "type": "INT"
        }
      },
      {
        "configuration": {
          "comparator": "NOT_EQUAL",
          "path": "*.path.to.tag",
          "thresholds": ["3"],
          "type": "INT"
        }
      }
    ]
  },
  "actions": [
    {
      "type": "ALARM",
      "configuration": {
        "displayName": "Alarm Name",
        "severity": 4,
        "condition": "In range: [1, 12]",
        "dynamicRecipientList": ["user@example.com"]
      }
    }
  ]
}
```

### TAG health monitor with threshold alarm

```json
{
  "event": {
    "type": "TAG",
    "triggers": [
      {
        "configuration": {
          "comparator": "GREATER_THAN_OR_EQUAL",
          "deadband": 5,
          "path": "*.Health.Memory.UsePercentage",
          "thresholds": ["80"],
          "type": "DOUBLE"
        }
      }
    ]
  },
  "actions": [
    {
      "type": "ALARM",
      "configuration": {
        "displayName": "High memory usage on <system>",
        "severity": 3,
        "condition": "Greater than or equal: 80"
      }
    }
  ]
}
```

Notes:

- Observed TAG comparators include `GREATER_THAN`, `GREATER_THAN_OR_EQUAL`, `NOT_EQUAL`, and `IN_RANGE`.
- Alarm-producing TAG routines still need the clear/reset action that uses trigger `nisystemlink_no_triggers_breached`.

### TESTRESULTCHANGED filter with nested fields and time parsing

```json
{
  "event": {
    "type": "TESTRESULTCHANGED",
    "triggers": [
      {
        "configuration": {
          "filter": "(before.partNumber != after.partNumber) && ((after.status.statusType = \"Done\" && after.hostName = \"<HOST_NAME>\" && after.operator = \"<OPERATOR>\" && after.properties[\"key\"] = \"value\" || after.programName = \"Test Name\" && DateTime(after.updatedAt) > DateTime.parse(\"2026-05-14T19:23:15.275Z\")))"
        }
      }
    ]
  },
  "actions": [
    {
      "type": "NOTEBOOK",
      "configuration": {
        "notebookId": "<NOTEBOOK_ID>",
        "resourceProfile": "LOW",
        "priority": "MEDIUM",
        "serviceAccount": "<SERVICE_ACCOUNT_ID>"
      }
    }
  ]
}
```

Notes:

- Observed filters can combine before/after comparisons, nested status fields, indexed property lookups, and `DateTime.parse(...)`.

### WORKITEMCHANGED filter with collection predicates

```json
{
  "event": {
    "type": "WORKITEMCHANGED",
    "triggers": [
      {
        "configuration": {
          "filter": "(before.assignedTo != after.assignedTo) && (after.resources.assets.selections.Any(s => s.id == \"<ASSET_ID>\") && !after.description.Contains(\"description\") && after.templateId = \"123\")"
        }
      }
    ]
  },
  "actions": [
    {
      "type": "NOTEBOOK",
      "configuration": {
        "resourceProfile": "HIGH",
        "priority": "HIGH"
      }
    }
  ]
}
```

Notes:

- Observed `WORKITEMCHANGED` filters can use `.Any(...)`, negated string checks, and exact template matching.
- Common NOTEBOOK action fields across v2 examples are `notebookId`, `parameters`, `resourceProfile`, `priority`, and `serviceAccount`.
