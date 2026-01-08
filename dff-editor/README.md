# Dynamic Form Fields Editor

This directory contains a standalone web editor for SystemLink Dynamic Form Fields configurations with a modern, VS Code-like interface.

## Files

- index.html - The main editor interface
- editor.js - Editor JavaScript logic
- README.md - This file
- index.html.backup - Backup of original simple editor

## Usage

1. Start the editor server:
  ```bash
  slcli dff edit --output-dir dff-editor --port 8080
  ```

2. Open your browser to: http://localhost:8080

3. Use the visual editor to build and manage your configuration

4. Click "Apply to Server" when ready to save

## Features

### Monaco Editor
- Syntax highlighting and IntelliSense for JSON
- Real-time validation against DFF schema
- Auto-formatting (Alt+F) and validate (Alt+V)
- Find/Replace (Ctrl+F / Ctrl+H)
- Minimap, dark theme, format on paste/type
- Auto-save every 30 seconds to local storage

### Configuration Tree View
- Root configuration, configurations, groups, fields
- Counts for groups/fields; required field indicator
- Click to navigate

### Add New Items
- Add Configuration: name, workspace, resource type, group keys
- Add Group: key, name, display text, field keys (with duplicate key guard)
- Add Field: key, name, display text, type, required (with duplicate key guard)
- Templates with inline help and validation

### Validation
- JSON syntax correctness
- Required fields present
- Unique keys for groups/fields
- Reference checks (configs → groups, groups → fields)
- Enum validation (resourceType, fieldType)
- Schema compliance

### Server Integration
- Load from Server (GET /api/dff/configurations)
- Apply to Server (POST /api/dff/configurations)
- Confirmation dialog before apply
- Error handling with clear messages

### Keyboard Shortcuts
- Alt+F: Format document
- Alt+V: Validate document
- Ctrl/Cmd+S: Save to server
- Ctrl+F: Find
- Ctrl+H: Find and replace

### Persistence & Safety
- Auto-save to localStorage every 30 seconds
- Auto-recovery prompt for drafts <24h old
- Unsaved changes warning on navigation
- Download JSON export

### Toolbar Actions
- Format, Validate, Load Example, Download JSON, Reset

## Configuration Structure

### Configurations
```json
{
  "name": "Work Order Configuration",
  "workspace": "workspace-id",
  "resourceType": "workorder:workorder",
  "groupKeys": ["group1", "group2"],
  "properties": {}
}
```
Resource types: workorder:workorder, workorder:testplan, asset:asset, system:system, testmonitor:product

### Groups
```json
{
  "key": "basicInfo",
  "workspace": "workspace-id",
  "name": "Basic Information",
  "displayText": "Basic Information",
  "fieldKeys": ["field1", "field2"],
  "properties": {}
}
```

### Fields
```json
{
  "key": "deviceId",
  "workspace": "workspace-id",
  "name": "Device ID",
  "displayText": "Device Identifier",
  "fieldType": "STRING",
  "required": true,
  "validation": { "maxLength": 50 },
  "properties": {}
}
```
Field types: STRING, NUMBER, BOOLEAN, DATE, DATETIME, SELECT, MULTISELECT
Validation options: STRING (minLength, maxLength, pattern), NUMBER (min, max, step), DATE/DATETIME (min, max), SELECT/MULTISELECT (options)

## Example Workflow
1. Load example or start empty
2. Add configuration (resource type)
3. Add groups
4. Add fields
5. Link fields to groups via fieldKeys
6. Link groups to configuration via groupKeys
7. Validate
8. Apply to server

## Technical Details
- Monaco Editor 0.45.0 via CDN
- Pure vanilla JS; no build step
- Uses fetch for API calls; localStorage for drafts
- Customize `serverUrl`, schema, and templates in editor.js

## Troubleshooting
- Editor not loading: check console/CDN access
- Validation errors: ensure unique keys and valid references
- Server issues: check port, CORS, network tab
- Auto-save: ensure localStorage is available

## Future Enhancements
- Drag-and-drop reordering
- Visual preview
- Diff view (local vs server)
- Undo/redo history
- Import from file
- Field/group duplication
- Bulk operations
- Search/filter in tree
- Theme toggle
- Version history

---
Version: 2.0 | Updated: January 7, 2026
