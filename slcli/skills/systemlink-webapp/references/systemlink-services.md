# SystemLink Services — API Reference

## How to find a service's OpenAPI spec

```
https://<server>/<service-prefix>/swagger/v2/<service-name>.yaml
```

Examples:
- `https://myserver.com/nitag/swagger/v2/nitag.yaml`
- `https://myserver.com/nitest/swagger/v2/nitest.yaml`

Use the spec URL as the `input` in your `openapi-ts.config.ts`.

---

## Tag Historian (`/nitag`)

**Base URL:** `window.location.origin + '/nitag'`

### Key endpoints

| Operation | Method | Path |
|-----------|--------|------|
| Query tags with current values | POST | `/nitag/v2/query-tags-with-values` |
| Get single tag | GET | `/nitag/v2/tags/{path}` |
| Write tag value | PUT | `/nitag/v2/tags/{path}/values/current` |
| Query tag history | POST | `/nitag/v2/history-data/query-decimated-data` |

### Query body (`POST /query-tags-with-values`)

```typescript
{
  filter: 'path = "system.*" and type = "DOUBLE"',  // LINQ filter string
  take: 1000,          // max records to return
  orderBy: 'TIMESTAMP',  // PATH | VALUE | TIMESTAMP | WORKSPACE
  descending: true,
  // projection: [...]  // AVOID — flattens the response and breaks tag.path / tag.type access
}
```

### Response shape (`TagWithValue`)

```typescript
{
  tag: {
    path: string,
    type: 'DOUBLE' | 'INT' | 'STRING' | 'BOOLEAN' | 'U_INT64' | 'DATE_TIME',
    keywords: string[],
    properties: Record<string, string>,
    workspace: string,
    lastUpdated: string,
  },
  current: {
    value: { value: string | number | boolean },
    timestamp: string,
  },
  aggregates: { ... }
}
```

> **Gotcha:** If you include `projection` in the query, the response is flattened — `tag` nesting is removed and `path`, `type` etc. lift to the top level. This breaks `twv.tag?.path`. Omit `projection` unless you update all mapping code to match the flat shape.

---

## Test Monitor (`/nitest`)

**Base URL:** `window.location.origin + '/nitest'`

### Key endpoints

| Operation | Method | Path |
|-----------|--------|------|
| Query results | POST | `/nitest/v2/query-results` |
| Get result by ID | GET | `/nitest/v2/results/{id}` |
| Query steps | POST | `/nitest/v2/query-steps` |
| Get products | GET | `/nitest/v2/products` |

### Query body

```typescript
{
  filter: 'startedWithin = "7d"',
  orderBy: 'startedAt',
  descending: true,
  take: 200,
}
```

---

## Asset Management (`/niapm`)

**Base URL:** `window.location.origin + '/niapm'`

### Key endpoints

| Operation | Method | Path |
|-----------|--------|------|
| Query assets | POST | `/niapm/v1/query-assets` |
| Get asset | GET | `/niapm/v1/assets/{id}` |
| Get calibration forecast | GET | `/niapm/v1/assets/{id}/policies` |

---

## Systems Management (`/nisysmgmt`)

**Base URL:** `window.location.origin + '/nisysmgmt'`

### Key endpoints

| Operation | Method | Path |
|-----------|--------|------|
| Get systems | GET | `/nisysmgmt/v1/systems` |
| Query systems | POST | `/nisysmgmt/v1/query-systems` |

---

## Work Orders (`/niworkorder`)

**Base URL:** `window.location.origin + '/niworkorder'`

### Key endpoints

| Operation | Method | Path |
|-----------|--------|------|
| Query work orders | POST | `/niworkorder/v1/query` |
| Update work order | PATCH | `/niworkorder/v1/work-orders/{id}` |

---

## Authentication patterns

### Same-origin (recommended for deployed webapps)

The app is served by SystemLink and calls SystemLink. Browser session cookies are sent automatically if `credentials: 'include'` is set on fetch requests.

```typescript
// hey-api client setup
import { createClient } from '@hey-api/client-fetch';

export const apiClient = createClient({
  baseUrl: `${window.location.origin}/nitag`,
  credentials: 'include',
});
```

No API key needed. The user must be logged in to SystemLink in that browser tab.

### API key (for dev/remote scenarios)

```typescript
export const apiClient = createClient({
  baseUrl: `${window.location.origin}/nitag`,
  headers: {
    'x-ni-api-key': localStorage.getItem('sl_api_key') ?? '',
  },
});
```

Let the user enter their API key in a config UI (a Nimble drawer works well). Store in `localStorage`. Never hardcode keys.

---

## LINQ filter syntax (used by tags, test, and other services)

```
path = "system.cpu.usage"              exact match
path.StartsWith("system.")             prefix match
type = "DOUBLE"                        enum match
lastUpdated > "2024-01-01"             date comparison
path = "cpu" and type = "DOUBLE"       AND
path = "cpu" or path = "mem"           OR
keywords.Contains("production")        array contains
```

String values must be double-quoted in the filter string. Build filters by joining parts with ` and `.

---

## Error handling

SystemLink APIs return standard HTTP status codes. Common ones:

| Code | Meaning |
|------|---------|
| 401 | Not authenticated — user needs to log in, or API key is invalid |
| 403 | Authenticated but not authorized for this workspace/resource |
| 404 | Resource not found |
| 422 | Invalid request body (e.g., bad LINQ filter) |

Show errors in a `<nimble-banner severity="error">` with the status code and message from the response body.
