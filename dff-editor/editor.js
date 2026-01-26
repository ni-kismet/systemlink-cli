// Dynamic Form Fields Editor - Main JavaScript

let editor;
let currentConfig = null;
let selectedTreeNode = 'root';
let modalType = null;
let currentConfigId = null;  // Track the loaded config ID
// Use current origin so the editor works regardless of chosen port.
let serverUrl = window.location.origin;
let undoStack = [];
let redoStack = [];
let isDirty = false;
let editorSecret = null;  // Global variable for editor session secret

const apiUrl = (path) => `${serverUrl}${path}`;

// Removed hydrateServerUrl function and its invocation

// Initialize Monaco Editor
require.config({ paths: { vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs' } });

require(['vs/editor/editor.main'], async function () {
    // Load editor secret from config
    try {
        const respCfg = await fetch('slcli-config.json');
        if (respCfg.ok) {
            const cfg = await respCfg.json();
            editorSecret = cfg.secret || null;
        }
    } catch (e) { /* ignore */ }

    // Define JSON schema for DFF configuration
    const dffSchema = {
        type: 'object',
        properties: {
            // New shape: singular configuration object
            configuration: {
                type: 'object',
                properties: {
                    id: { type: 'string' },
                    name: { type: 'string' },
                    workspace: { type: 'string' },
                    resourceType: { 
                        type: 'string',
                        enum: ['workorder:workorder', 'workitem:workitem', 'asset:asset', 'system:system', 'testmonitor:product']
                    },
                    groupKeys: { type: 'array', items: { type: 'string' } },
                    key: { type: 'string' },
                    displayRule: { type: 'string' },
                    views: {
                        type: 'array',
                        items: {
                            type: 'object',
                            properties: {
                                key: { type: 'string' },
                                displayText: { type: 'string' },
                                helpText: { type: 'string' },
                                order: { type: 'number' },
                                editable: { type: 'boolean' },
                                visible: { type: 'boolean' },
                                retainWhenHidden: { type: 'boolean' },
                                i18n: { type: 'array' },
                                displayLocations: { type: 'array', items: { type: 'string' } },
                                groups: { type: 'array', items: { type: 'string' } }
                            },
                            required: ['key', 'displayText']
                        }
                    },
                    rules: { type: 'array' },
                    properties: { type: 'object' }
                },
                required: ['name', 'workspace', 'resourceType']
            },
            // Backward compatibility: legacy array shape
            configurations: {
                type: 'array',
                items: {
                    type: 'object',
                    properties: {
                        id: { type: 'string' },
                        name: { type: 'string' },
                        workspace: { type: 'string' },
                        resourceType: { 
                            type: 'string',
                            enum: ['workorder:workorder', 'workitem:workitem', 'asset:asset', 'system:system', 'testmonitor:product']
                        },
                        groupKeys: { type: 'array', items: { type: 'string' } },
                        key: { type: 'string' },
                        displayRule: { type: 'string' },
                        views: {
                            type: 'array',
                            items: {
                                type: 'object',
                                properties: {
                                    key: { type: 'string' },
                                    displayText: { type: 'string' },
                                    helpText: { type: 'string' },
                                    order: { type: 'number' },
                                    editable: { type: 'boolean' },
                                    visible: { type: 'boolean' },
                                    retainWhenHidden: { type: 'boolean' },
                                    i18n: { type: 'array' },
                                    displayLocations: { type: 'array', items: { type: 'string' } },
                                    groups: { type: 'array', items: { type: 'string' } }
                                },
                                required: ['key', 'displayText']
                            }
                        },
                        rules: { type: 'array' },
                        properties: { type: 'object' }
                    },
                    required: ['name', 'workspace', 'resourceType']
                }
            },
            groups: {
                type: 'array',
                items: {
                    type: 'object',
                    properties: {
                        key: { type: 'string' },
                        workspace: { type: 'string' },
                        displayText: { type: 'string' },
                        helpText: { type: 'string' },
                        i18n: { type: 'array' },
                        editable: { type: 'boolean' },
                        visible: { type: 'boolean' },
                        retainWhenHidden: { type: 'boolean' },
                        fields: { type: 'array', items: { type: 'string' } },
                        properties: { type: 'object' },
                        createdBy: { type: 'string' },
                        updatedBy: { type: 'string' },
                        createdAt: { type: 'string' },
                        updatedAt: { type: 'string' }
                    },
                    required: ['key', 'workspace']
                }
            },
            fields: {
                type: 'array',
                items: {
                    type: 'object',
                    properties: {
                        key: { type: 'string' },
                        workspace: { type: 'string' },
                        displayText: { type: 'string' },
                        helpText: { type: 'string' },
                        placeHolder: { type: 'string' },
                        i18n: { type: 'array' },
                        fieldType: { 
                            type: 'string',
                            enum: ['STRING', 'NUMBER', 'BOOLEAN', 'DATE', 'DATETIME', 'SELECT', 'MULTISELECT', 'TEXT']
                        },
                        type: { type: 'string' },
                        editable: { type: 'boolean' },
                        mandatory: { type: 'boolean' },
                        visible: { type: 'boolean' },
                        retainWhenHidden: { type: 'boolean' },
                        columns: { type: 'array', items: { type: 'string' } },
                        defaultValue: {},
                        validation: { type: ['object', 'null'] },
                        allowedValues: { type: 'array' },
                        requestConfiguration: { type: 'object' },
                        properties: { type: 'object' },
                        createdBy: { type: 'string' },
                        updatedBy: { type: 'string' },
                        createdAt: { type: 'string' },
                        updatedAt: { type: 'string' }
                    },
                    required: ['key', 'workspace']
                }
            }
        }
    };
    
    monaco.languages.json.jsonDefaults.setDiagnosticsOptions({
        validate: true,
        schemas: [{
            uri: 'http://myserver/dff-schema.json',
            fileMatch: ['*'],
            schema: dffSchema
        }]
    });
    
    editor = monaco.editor.create(document.getElementById('editor'), {
        value: getDefaultConfig(),
        language: 'json',
        theme: 'vs-dark',
        automaticLayout: true,
        minimap: { enabled: true },
        scrollBeyondLastLine: false,
        formatOnPaste: true,
        formatOnType: true,
        tabSize: 2,
        insertSpaces: true
    });
    
    // Update status bar on cursor position change
    editor.onDidChangeCursorPosition((e) => {
        document.getElementById('statusInfo').textContent = `Ln ${e.position.lineNumber}, Col ${e.position.column}`;
    });
    
    // Auto-validate on content change
    editor.onDidChangeModelContent(() => {
        isDirty = true;
        setTimeout(validateDocument, 500);
    });
    
    // Keyboard shortcuts
    editor.addAction({
        id: 'format-document',
        label: 'Format Document',
        keybindings: [monaco.KeyMod.Alt | monaco.KeyCode.KeyF],
        run: formatDocument
    });
    
    editor.addAction({
        id: 'validate-document',
        label: 'Validate Document',
        keybindings: [monaco.KeyMod.Alt | monaco.KeyCode.KeyV],
        run: validateDocument
    });
    
    editor.addAction({
        id: 'save-document',
        label: 'Save to Server',
        keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS],
        run: (ed) => {
            saveToServer();
            return null;
        }
    });
    
    // Auto-save to local storage every 30 seconds
    setInterval(autoSave, 30000);
    
    // Load editor metadata if available (configId)
    try {
        const resp = await fetch('.editor-metadata.json');
        if (resp.ok) {
            const metadata = await resp.json();
            if (metadata.configId) {
                currentConfigId = metadata.configId;
            }
            if (metadata.configFile) {
                // Try to load the saved config file
                try {
                    const configResp = await fetch(metadata.configFile);
                    if (configResp.ok) {
                        const savedConfig = await configResp.json();
                        editor.setValue(JSON.stringify(savedConfig, null, 2));
                        currentConfig = savedConfig;
                        isDirty = false;
                        showStatus('Configuration loaded from file', 'success');
                        refreshTree();
                        return;
                    }
                } catch (e) {
                    console.warn('Could not load saved config file:', e);
                }
            }
        }
    } catch (e) {
        // Metadata file not found, use default
    }
    
    // Load from auto-save if available
    loadAutoSave();
    
    // Initial validation
    validateDocument();
    refreshTree();
});

function getDefaultConfig() {
    return JSON.stringify({
        configurations: [],
        groups: [],
        fields: []
    }, null, 2);
}

function getExampleConfig() {
    return {
        configurations: [
            {
                name: "Example Work Item Configuration",
                key: "exampleConfiguration",
                workspace: "your-workspace-id",
                resourceType: "workitem:workitem",
                groupKeys: ["basicInfo", "measurements"],
                properties: {},
                displayRule: "name == 'NI'",
                views: [
                    {
                        key: "defaultView",
                        displayText: "Default View",
                        helpText: "Shows all basic information and measurements",
                        order: 10,
                        editable: true,
                        visible: true,
                        retainWhenHidden: false,
                        i18n: [],
                        displayLocations: ["compact", "full"],
                        groups: ["basicInfo", "measurements"]
                    }
                ]
            }
        ],
        groups: [
            {
                key: "basicInfo",
                workspace: "your-workspace-id",
                displayText: "Basic Information",
                helpText: "General identifiers",
                fields: ["deviceId", "operator"],
                editable: true,
                visible: true,
                retainWhenHidden: false,
                properties: {}
            },
            {
                key: "measurements",
                workspace: "your-workspace-id",
                displayText: "Test Measurements",
                helpText: "Captured measurements",
                fields: ["voltage", "current"],
                editable: true,
                visible: true,
                retainWhenHidden: false,
                properties: {}
            }
        ],
        fields: [
            {
                key: "deviceId",
                workspace: "your-workspace-id",
                displayText: "Device Identifier",
                helpText: "Unique device identifier",
                placeHolder: "Enter device ID",
                fieldType: "STRING",
                required: true,
                validation: { maxLength: 50 },
                properties: {}
            },
            {
                key: "operator",
                workspace: "your-workspace-id",
                displayText: "Operator Name",
                helpText: "Person running the test",
                placeHolder: "Enter operator",
                fieldType: "STRING",
                required: false,
                validation: {},
                properties: {}
            },
            {
                key: "voltage",
                workspace: "your-workspace-id",
                displayText: "Voltage (V)",
                helpText: "Measured voltage",
                fieldType: "NUMBER",
                required: true,
                validation: { min: 0, max: 500 },
                properties: {}
            },
            {
                key: "current",
                workspace: "your-workspace-id",
                displayText: "Current (A)",
                helpText: "Measured current",
                fieldType: "NUMBER",
                required: false,
                validation: { min: 0 },
                properties: {}
            }
        ]
    };
}

// Configuration Templates
const TEMPLATES = {
    configuration: {
        name: "",
        workspace: "",
        resourceType: "workitem:workitem",
        groupKeys: [],
        properties: {}
    },
    group: {
        key: "",
        workspace: "",
        displayText: "",
        helpText: "",
        fields: [],
        properties: {}
    },
    field: {
        key: "",
        workspace: "",
        displayText: "",
        helpText: "",
        placeHolder: "",
        fieldType: "STRING",
        required: false,
        validation: {},
        properties: {}
    }
};

function formatDocument() {
    editor.getAction('editor.action.formatDocument').run();
    showStatus('Document formatted', 'success');
}

function validateDocument() {
    try {
        const content = editor.getValue();
        const config = JSON.parse(content);
        currentConfig = config;
        
        // Validate structure
        const errors = validateConfig(config);
        if (errors.length > 0) {
            showStatus(`Validation errors: ${errors.join(', ')}`, 'error');
            return false;
        } else {
            showStatus('Configuration valid ✓', 'success');
            // Don't call refreshTree here to avoid infinite recursion
            // refreshTree is called explicitly when needed
            return true;
        }
    } catch (e) {
        showStatus('Invalid JSON: ' + e.message, 'error');
        return false;
    }
}

function validateConfig(config) {
    const errors = [];
    
    if (!config.configurations) errors.push('Missing configurations array');
    if (!config.groups) errors.push('Missing groups array');
    if (!config.fields) errors.push('Missing fields array');
    
    // Validate unique keys
    if (config.groups) {
        const groupKeys = config.groups.map(g => g.key);
        if (groupKeys.length !== new Set(groupKeys).size) {
            errors.push('Duplicate group keys found');
        }
    }
    
    if (config.fields) {
        const fieldKeys = config.fields.map(f => f.key);
        if (fieldKeys.length !== new Set(fieldKeys).size) {
            errors.push('Duplicate field keys found');
        }
    }
    
    // Validate unique view keys within each configuration
    if (config.configurations) {
        config.configurations.forEach((conf, i) => {
            if (conf.views) {
                const viewKeys = conf.views.map(v => v.key);
                if (viewKeys.length !== new Set(viewKeys).size) {
                    errors.push(`Configuration ${i}: Duplicate view keys found`);
                }
            }
        });
    }
    
    // Validate references
    if (config.configurations && config.groups) {
        config.configurations.forEach((conf, i) => {
            if (conf.groupKeys) {
                conf.groupKeys.forEach(gk => {
                    if (!config.groups.some(g => g.key === gk)) {
                        errors.push(`Configuration ${i}: references non-existent group '${gk}'`);
                    }
                });
            }
            // Validate view group references
            if (conf.views) {
                conf.views.forEach((view, vi) => {
                    if (view.groups) {
                        view.groups.forEach(gk => {
                            if (!config.groups.some(g => g.key === gk)) {
                                errors.push(`Configuration ${i}, View '${view.key}': references non-existent group '${gk}'`);
                            }
                        });
                    }
                });
            }
        });
    }
    
    if (config.groups && config.fields) {
        config.groups.forEach((group, i) => {
            if (group.fields) {
                group.fields.forEach(fk => {
                    if (!config.fields.some(f => f.key === fk)) {
                        errors.push(`Group '${group.key}': references non-existent field '${fk}'`);
                    }
                });
            }
        });
    }
    
    return errors;
}

function loadExample() {
    const example = getExampleConfig();
    editor.setValue(JSON.stringify(example, null, 2));
    showStatus('Example configuration loaded', 'success');
}

function downloadConfiguration() {
    try {
        const content = editor.getValue();
        const config = JSON.parse(content);
        const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'dff-configuration.json';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showStatus('Configuration downloaded', 'success');
    } catch (e) {
        showStatus('Cannot download: Invalid JSON', 'error');
    }
}

function resetEditor() {
    if (confirm('Reset editor to empty configuration? This will lose all unsaved changes.')) {
        editor.setValue(getDefaultConfig());
        isDirty = false;
        showStatus('Editor reset', 'success');
    }
}

function refreshTree() {
    if (!validateDocument()) return;
    
    const treeView = document.getElementById('treeView');
    const config = currentConfig;
    
    if (!config) return;
    
    let html = '<div class="tree-node" onclick="selectTreeNode(\'root\')"><span class="tree-icon">📄</span><span>Root Configuration</span></div>';
    
    // Configurations
    if (config.configurations && config.configurations.length > 0) {
        config.configurations.forEach((conf, i) => {
            const confLabel = conf.displayText || conf.name || conf.key || ('Configuration ' + (i + 1));
            html += `<div class="tree-node indent-1" onclick="selectTreeNode('config-${i}')"><span class="tree-icon">⚙️</span><span>${confLabel}</span></div>`;
            // Show views under each configuration
            if (conf.views && conf.views.length > 0) {
                conf.views.forEach((view, vi) => {
                    html += `<div class="tree-node indent-2" onclick="selectTreeNode('config-${i}-view-${vi}')"><span class="tree-icon">👁️</span><span>${view.displayText || view.key}</span><button class="edit-btn" onclick="event.stopPropagation(); showEditDialog('view', ${i}, ${vi})">✎</button></div>`;
                });
            }
        });
    }
    
    // Groups
    if (config.groups && config.groups.length > 0) {
        html += '<div class="tree-node indent-1"><span class="tree-icon">📁</span><span>Groups (' + config.groups.length + ')</span></div>';
        config.groups.forEach((group, i) => {
            const groupLabel = group.displayText || group.key;
            html += `<div class="tree-node indent-2" onclick="selectTreeNode('group-${i}')"><span class="tree-icon">📦</span><span>${groupLabel}</span><button class="edit-btn" onclick="event.stopPropagation(); showEditDialog('group', ${i})">✎</button></div>`;
        });
    }
    
    // Fields
    if (config.fields && config.fields.length > 0) {
        html += '<div class="tree-node indent-1"><span class="tree-icon">📁</span><span>Fields (' + config.fields.length + ')</span></div>';
        config.fields.forEach((field, i) => {
            const icon = field.required ? '🏷️' : '🔖';
            const fieldLabel = field.displayText || field.key;
            html += `<div class="tree-node indent-2" onclick="selectTreeNode('field-${i}')"><span class="tree-icon">${icon}</span><span>${fieldLabel}</span><button class="edit-btn" onclick="event.stopPropagation(); showEditDialog('field', ${i})">✎</button></div>`;
        });
    }
    
    treeView.innerHTML = html;
}

function selectTreeNode(nodeId) {
    selectedTreeNode = nodeId;
    
    // Update visual selection
    document.querySelectorAll('.tree-node').forEach(node => {
        node.classList.remove('selected');
    });
    event.currentTarget.classList.add('selected');
    
    // Highlight corresponding JSON in editor
    selectNodeInEditor(nodeId);
    
    showStatus(`Selected: ${nodeId}`, 'success');
}

function selectNodeInEditor(nodeId) {
    if (!currentConfig || !editor) return;
    
    const content = editor.getValue();
    const lines = content.split('\n');
    
    try {
        // Handle nested views: config-X-view-Y pattern
        const nestedMatch = nodeId.match(/^config-(\d+)-view-(\d+)$/);
        if (nestedMatch) {
            const [, configIdx, viewIdx] = nestedMatch;
            const conf = currentConfig.configurations?.[parseInt(configIdx)];
            const view = conf?.views?.[parseInt(viewIdx)];
            if (!view) return;
            
            const searchKey = view.key;
            if (!searchKey) return;
            
            // Find this view's key in the JSON within the configuration's views array
            let inViewsArray = false;
            for (let i = 0; i < lines.length; i++) {
                const line = lines[i];
                // Look for the configuration first, then views array, then the specific view
                if (line.includes(`"views":`)) {
                    inViewsArray = true;
                }
                if (inViewsArray && (line.includes(`"key": "${searchKey}"`) || line.includes(`'key': '${searchKey}'`))) {
                    // Find the opening brace of this object
                    let startLine = i;
                    for (let j = i; j >= 0; j--) {
                        if (lines[j].includes('{')) {
                            startLine = j + 1;
                            break;
                        }
                    }
                    // Find the closing brace
                    let endLine = i;
                    let braceCount = 0;
                    for (let j = startLine - 1; j < lines.length; j++) {
                        const l = lines[j];
                        if (l.includes('{')) braceCount++;
                        if (l.includes('}')) {
                            braceCount--;
                            if (braceCount === 0) {
                                endLine = j + 1;
                                break;
                            }
                        }
                    }
                    editor.revealLineInCenter(startLine);
                    editor.setSelection({
                        startLineNumber: startLine,
                        startColumn: 1,
                        endLineNumber: endLine,
                        endColumn: lines[endLine - 1].length + 1
                    });
                    return;
                }
            }
            return;
        }
        
        // Parse node type and index for top-level items
        const match = nodeId.match(/^(config|group|field)-(\d+)$/);
        if (!match) return;
        
        const [, type, index] = match;
        const idx = parseInt(index);
        
        let arrayName = type === 'config' ? 'configurations' : type + 's';
        let targetItem = currentConfig[arrayName]?.[idx];
        if (!targetItem) return;
        
        // Find the item's key (preferred) or display text in the JSON
        const searchKey = targetItem.key || targetItem.displayText || '';
        if (!searchKey) return;
        
        // Search for the line containing this key
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            if (line.includes(`"key": "${searchKey}"`) || line.includes(`"displayText": "${searchKey}"`)) {
                // Find the opening brace of this object (go backwards)
                let startLine = i;
                let braceCount = 0;
                for (let j = i; j >= 0; j--) {
                    const l = lines[j];
                    if (l.includes('{')) {
                        braceCount++;
                        if (braceCount === 1) {
                            startLine = j + 1; // Monaco uses 1-based line numbers
                            break;
                        }
                    }
                }
                
                // Find the closing brace (go forwards)
                let endLine = i;
                braceCount = 0;
                for (let j = startLine - 1; j < lines.length; j++) {
                    const l = lines[j];
                    const openCount = (l.match(/{/g) || []).length;
                    const closeCount = (l.match(/}/g) || []).length;
                    braceCount += openCount - closeCount;
                    if (braceCount === 0 && j > i) {
                        endLine = j + 1;
                        break;
                    }
                }
                
                // Select the range in Monaco
                editor.setSelection({
                    startLineNumber: startLine,
                    startColumn: 1,
                    endLineNumber: endLine,
                    endColumn: lines[endLine - 1].length + 1
                });
                editor.revealLineInCenter(startLine);
                break;
            }
        }
    } catch (e) {
        console.error('Error selecting node in editor:', e);
    }
}

function showAddDialog(type) {
    modalType = type;
    const overlay = document.getElementById('modalOverlay');
    const title = document.getElementById('modalTitle');
    const body = document.getElementById('modalBody');
    
    if (type === 'view') {
        const defaultKey = generateTempKey('NewView');
        title.textContent = 'Add View';
        body.innerHTML = `
            <div class="form-group">
                <label>Key *</label>
                <input type="text" id="viewKey" placeholder="e.g., defaultView" value="${defaultKey}">
                <small>Unique identifier</small>
            </div>
            <div class="form-group">
                <label>Display Text *</label>
                <input type="text" id="viewDisplayText" placeholder="e.g., Default View">
                <small>Text shown to users</small>
            </div>
            <div class="form-group">
                <label>Help Text</label>
                <input type="text" id="viewHelpText" placeholder="Optional help text">
            </div>
            <div class="form-group">
                <label>Order</label>
                <input type="number" id="viewOrder" value="10">
                <small>Display order (lower numbers appear first)</small>
            </div>
            <div class="form-group">
                <label>Display Locations (comma-separated)</label>
                <input type="text" id="viewDisplayLocations" placeholder="e.g., compact, full, split, global" value="compact">
                <small>Valid values: compact, full, split, global</small>
            </div>
            <div class="form-group">
                <label>Group Keys (comma-separated)</label>
                <input type="text" id="viewGroups" placeholder="e.g., group1, group2">
                <small>Keys of groups to include in this view</small>
            </div>
            <div class="form-group checkbox-group">
                <input type="checkbox" id="viewEditable" checked>
                <label for="viewEditable">Editable</label>
            </div>
            <div class="form-group checkbox-group">
                <input type="checkbox" id="viewVisible" checked>
                <label for="viewVisible">Visible</label>
            </div>
        `;
    } else if (type === 'group') {
        const workspace = getCurrentWorkspace();
        const defaultKey = generateTempKey('NewGroup');
        title.textContent = 'Add Group';
        body.innerHTML = `
            <div class="form-group">
                <label>Key *</label>
                <input type="text" id="groupKey" placeholder="e.g., basicInfo" value="${defaultKey}">
                <small>Unique identifier (lowercase, no spaces)</small>
            </div>
            <div class="form-group">
                <label>Display Text *</label>
                <input type="text" id="groupDisplayText" placeholder="e.g., Basic Information">
                <small>Text shown to users</small>
            </div>
            <div class="form-group">
                <label>Help Text</label>
                <input type="text" id="groupHelpText" placeholder="Optional help text">
            </div>
            <div class="form-group">
                <label>Workspace ID *</label>
                <input type="text" id="groupWorkspace" placeholder="e.g., workspace-123" value="${workspace}">
            </div>
            <div class="form-group">
                <label>Field Keys (comma-separated)</label>
                <input type="text" id="groupFieldKeys" placeholder="e.g., field1, field2">
                <small>Optional: Keys of fields to include</small>
            </div>
        `;
    } else if (type === 'field') {
        const workspace = getCurrentWorkspace();
        const defaultKey = generateTempKey('NewField');
        title.textContent = 'Add Field';
        body.innerHTML = `
            <div class="form-group">
                <label>Key *</label>
                <input type="text" id="fieldKey" placeholder="e.g., deviceId" value="${defaultKey}">
                <small>Unique identifier (lowercase, no spaces)</small>
            </div>
            <div class="form-group">
                <label>Display Text *</label>
                <input type="text" id="fieldDisplayText" placeholder="e.g., Device Identifier">
                <small>Text shown to users</small>
            </div>
            <div class="form-group">
                <label>Help Text</label>
                <input type="text" id="fieldHelpText" placeholder="Optional help text">
            </div>
            <div class="form-group">
                <label>Placeholder</label>
                <input type="text" id="fieldPlaceholder" placeholder="Optional placeholder text">
            </div>
            <div class="form-group">
                <label>Workspace ID *</label>
                <input type="text" id="fieldWorkspace" placeholder="e.g., workspace-123" value="${workspace}">
            </div>
            <div class="form-group">
                <label>Field Type *</label>
                <select id="fieldType">
                    <option value="STRING">String</option>
                    <option value="NUMBER">Number</option>
                    <option value="BOOLEAN">Boolean</option>
                    <option value="DATE">Date</option>
                    <option value="DATETIME">DateTime</option>
                    <option value="SELECT">Select</option>
                    <option value="MULTISELECT">Multi-Select</option>
                    <option value="TEXT">Text</option>
                </select>
            </div>
            <div class="form-group checkbox-group">
                <input type="checkbox" id="fieldRequired">
                <label for="fieldRequired">Required field</label>
            </div>
        `;
    }
    
    overlay.classList.add('active');
}

function showEditDialog(type, configIdx, viewIdx = null) {
    modalType = `edit-${type}`;
    const overlay = document.getElementById('modalOverlay');
    const title = document.getElementById('modalTitle');
    const body = document.getElementById('modalBody');
    
    if (type === 'view' && viewIdx !== null) {
        const conf = currentConfig.configurations?.[configIdx];
        const view = conf?.views?.[viewIdx];
        if (!view) {
            showStatus('View not found', 'error');
            return;
        }
        
        title.textContent = 'Edit View';
        body.innerHTML = `
            <div class="form-group">
                <label>Key *</label>
                <input type="text" id="viewKey" placeholder="e.g., defaultView" value="${view.key || ''}">
                <small>Unique identifier</small>
            </div>
            <div class="form-group">
                <label>Display Text *</label>
                <input type="text" id="viewDisplayText" placeholder="e.g., Default View" value="${view.displayText || ''}">
                <small>Text shown to users</small>
            </div>
            <div class="form-group">
                <label>Help Text</label>
                <input type="text" id="viewHelpText" placeholder="Optional help text" value="${view.helpText || ''}">
            </div>
            <div class="form-group">
                <label>Order</label>
                <input type="number" id="viewOrder" value="${view.order || 10}">
                <small>Display order (lower numbers appear first)</small>
            </div>
            <div class="form-group">
                <label>Display Locations (comma-separated)</label>
                <input type="text" id="viewDisplayLocations" placeholder="e.g., compact, full, split, global" value="${(view.displayLocations || []).join(', ')}">
                <small>Valid values: compact, full, split, global</small>
            </div>
            <div class="form-group">
                <label>Group Keys (comma-separated)</label>
                <input type="text" id="viewGroups" placeholder="e.g., group1, group2" value="${(view.groups || []).join(', ')}">
                <small>Keys of groups to include in this view</small>
            </div>
            <div class="form-group checkbox-group">
                <input type="checkbox" id="viewEditable" ${view.editable ? 'checked' : ''}>
                <label for="viewEditable">Editable</label>
            </div>
            <div class="form-group checkbox-group">
                <input type="checkbox" id="viewVisible" ${view.visible ? 'checked' : ''}>
                <label for="viewVisible">Visible</label>
            </div>
        `;
        
        // Store indices in modal for use during submit
        overlay.dataset.editType = 'view';
        overlay.dataset.configIdx = configIdx;
        overlay.dataset.viewIdx = viewIdx;
        
    } else if (type === 'group') {
        const group = currentConfig.groups?.[configIdx];
        if (!group) {
            showStatus('Group not found', 'error');
            return;
        }
        
        title.textContent = 'Edit Group';
        body.innerHTML = `
            <div class="form-group">
                <label>Key *</label>
                <input type="text" id="groupKey" placeholder="e.g., basicInfo" value="${group.key || ''}">
                <small>Unique identifier (lowercase, no spaces)</small>
            </div>
            <div class="form-group">
                <label>Display Text *</label>
                <input type="text" id="groupDisplayText" placeholder="e.g., Basic Information" value="${group.displayText || ''}">
                <small>Text shown to users</small>
            </div>
            <div class="form-group">
                <label>Help Text</label>
                <input type="text" id="groupHelpText" placeholder="Optional help text" value="${group.helpText || ''}">
            </div>
            <div class="form-group">
                <label>Workspace ID *</label>
                <input type="text" id="groupWorkspace" placeholder="e.g., workspace-123" value="${group.workspace || ''}">
            </div>
            <div class="form-group">
                <label>Field Keys (comma-separated)</label>
                <input type="text" id="groupFieldKeys" placeholder="e.g., field1, field2" value="${(group.fields || []).join(', ')}">
                <small>Optional: Keys of fields to include</small>
            </div>
        `;
        
        overlay.dataset.editType = 'group';
        overlay.dataset.groupIdx = configIdx;
        
    } else if (type === 'field') {
        const field = currentConfig.fields?.[configIdx];
        if (!field) {
            showStatus('Field not found', 'error');
            return;
        }
        
        title.textContent = 'Edit Field';
        body.innerHTML = `
            <div class="form-group">
                <label>Key *</label>
                <input type="text" id="fieldKey" placeholder="e.g., deviceId" value="${field.key || ''}">
                <small>Unique identifier (lowercase, no spaces)</small>
            </div>
            <div class="form-group">
                <label>Display Text *</label>
                <input type="text" id="fieldDisplayText" placeholder="e.g., Device Identifier" value="${field.displayText || ''}">
                <small>Text shown to users</small>
            </div>
            <div class="form-group">
                <label>Help Text</label>
                <input type="text" id="fieldHelpText" placeholder="Optional help text" value="${field.helpText || ''}">
            </div>
            <div class="form-group">
                <label>Placeholder</label>
                <input type="text" id="fieldPlaceholder" placeholder="Optional placeholder text" value="${field.placeHolder || ''}">
            </div>
            <div class="form-group">
                <label>Workspace ID *</label>
                <input type="text" id="fieldWorkspace" placeholder="e.g., workspace-123" value="${field.workspace || ''}">
            </div>
            <div class="form-group">
                <label>Field Type *</label>
                <select id="fieldType">
                    <option value="STRING" ${field.fieldType === 'STRING' ? 'selected' : ''}>String</option>
                    <option value="NUMBER" ${field.fieldType === 'NUMBER' ? 'selected' : ''}>Number</option>
                    <option value="BOOLEAN" ${field.fieldType === 'BOOLEAN' ? 'selected' : ''}>Boolean</option>
                    <option value="DATE" ${field.fieldType === 'DATE' ? 'selected' : ''}>Date</option>
                    <option value="DATETIME" ${field.fieldType === 'DATETIME' ? 'selected' : ''}>DateTime</option>
                    <option value="SELECT" ${field.fieldType === 'SELECT' ? 'selected' : ''}>Select</option>
                    <option value="MULTISELECT" ${field.fieldType === 'MULTISELECT' ? 'selected' : ''}>Multi-Select</option>
                    <option value="TEXT" ${field.fieldType === 'TEXT' ? 'selected' : ''}>Text</option>
                </select>
            </div>
            <div class="form-group checkbox-group">
                <input type="checkbox" id="fieldRequired" ${field.required ? 'checked' : ''}>
                <label for="fieldRequired">Required field</label>
            </div>
        `;
        
        overlay.dataset.editType = 'field';
        overlay.dataset.fieldIdx = configIdx;
    }
    
    overlay.classList.add('active');
}

function getCurrentWorkspace() {
    if (!currentConfig) return '';
    if (currentConfig.configuration && currentConfig.configuration.workspace) {
        return currentConfig.configuration.workspace;
    }
    if (currentConfig.configurations && currentConfig.configurations.length > 0) {
        return currentConfig.configurations[0].workspace || '';
    }
    return '';
}

function generateTempKey(prefix) {
    const rand = Math.random().toString(36).slice(2, 9);
    return `(${prefix}_${rand})`;
}

function closeModal() {
    document.getElementById('modalOverlay').classList.remove('active');
}

function submitModal() {
    if (!currentConfig) {
        currentConfig = { configurations: [], groups: [], fields: [] };
    }
    
    // Ensure arrays exist
    if (!currentConfig.configurations) currentConfig.configurations = [];
    if (!currentConfig.groups) currentConfig.groups = [];
    if (!currentConfig.fields) currentConfig.fields = [];
    
    // Check if we're in edit mode
    const overlay = document.getElementById('modalOverlay');
    const isEdit = modalType && modalType.startsWith('edit-');
    
    try {
        if (modalType === 'view' || modalType === 'edit-view') {
            const key = document.getElementById('viewKey').value.trim();
            const displayText = document.getElementById('viewDisplayText').value.trim();
            const helpText = document.getElementById('viewHelpText').value.trim();
            const order = parseInt(document.getElementById('viewOrder').value) || 10;
            const editable = document.getElementById('viewEditable').checked;
            const visible = document.getElementById('viewVisible').checked;
            const displayLocationsStr = document.getElementById('viewDisplayLocations').value.trim();
            const groupsStr = document.getElementById('viewGroups').value.trim();
            
            if (!key || !displayText) {
                showStatus('Please fill in all required fields', 'error');
                return;
            }
            
            if (!currentConfig.configurations || currentConfig.configurations.length === 0) {
                showStatus('Please add a configuration first before adding/editing views', 'error');
                return;
            }
            
            const targetConfig = currentConfig.configurations[0];
            if (!targetConfig.views) {
                targetConfig.views = [];
            }
            
            const displayLocations = displayLocationsStr ? displayLocationsStr.split(',').map(k => k.trim()).filter(k => k) : ['compact'];
            const groupsList = groupsStr ? groupsStr.split(',').map(k => k.trim()).filter(k => k) : [];
            
            const viewData = {
                key,
                displayText,
                helpText,
                order,
                editable,
                visible,
                retainWhenHidden: false,
                i18n: [],
                displayLocations,
                groups: groupsList
            };
            
            if (isEdit) {
                // Edit mode: replace the existing view
                const viewIdx = parseInt(overlay.dataset.viewIdx);
                if (viewIdx >= 0 && viewIdx < targetConfig.views.length) {
                    // Check for duplicate key only if key has changed
                    const originalKey = targetConfig.views[viewIdx].key;
                    if (key !== originalKey && targetConfig.views.some((v, i) => i !== viewIdx && v.key === key)) {
                        showStatus(`View key '${key}' already exists`, 'error');
                        return;
                    }
                    targetConfig.views[viewIdx] = viewData;
                    showStatus('View updated successfully', 'success');
                }
            } else {
                // Add mode: check for duplicate and push new view
                if (targetConfig.views.some(v => v.key === key)) {
                    showStatus(`View key '${key}' already exists`, 'error');
                    return;
                }
                targetConfig.views.push(viewData);
                showStatus('View added successfully', 'success');
            }
            
        } else if (modalType === 'group' || modalType === 'edit-group') {
            const key = document.getElementById('groupKey').value.trim();
            const displayText = document.getElementById('groupDisplayText').value.trim();
            const helpText = document.getElementById('groupHelpText').value.trim();
            let workspace = document.getElementById('groupWorkspace').value.trim();
            if (!workspace) {
                workspace = getCurrentWorkspace();
            }
            const fieldKeysStr = document.getElementById('groupFieldKeys').value.trim();
            
            if (!key || !displayText || !workspace) {
                showStatus('Please fill in all required fields', 'error');
                return;
            }
            
            const fieldKeys = fieldKeysStr ? fieldKeysStr.split(',').map(k => k.trim()).filter(k => k) : [];
            
            const groupData = {
                key,
                workspace,
                displayText,
                helpText,
                fields: fieldKeys,
                properties: {}
            };
            
            if (isEdit) {
                // Edit mode: replace the existing group
                const groupIdx = parseInt(overlay.dataset.groupIdx);
                if (groupIdx >= 0 && groupIdx < currentConfig.groups.length) {
                    // Check for duplicate key only if key has changed
                    const originalKey = currentConfig.groups[groupIdx].key;
                    if (key !== originalKey && currentConfig.groups.some((g, i) => i !== groupIdx && g.key === key)) {
                        showStatus(`Group key '${key}' already exists`, 'error');
                        return;
                    }
                    currentConfig.groups[groupIdx] = groupData;
                    showStatus('Group updated successfully', 'success');
                }
            } else {
                // Add mode: check for duplicate and push new group
                if (currentConfig.groups.some(g => g.key === key)) {
                    showStatus(`Group key '${key}' already exists`, 'error');
                    return;
                }
                currentConfig.groups.push(groupData);
                showStatus('Group added successfully', 'success');
            }
            
        } else if (modalType === 'field' || modalType === 'edit-field') {
            const key = document.getElementById('fieldKey').value.trim();
            const displayText = document.getElementById('fieldDisplayText').value.trim();
            const helpText = document.getElementById('fieldHelpText').value.trim();
            const placeHolder = document.getElementById('fieldPlaceholder').value.trim();
            let workspace = document.getElementById('fieldWorkspace').value.trim();
            if (!workspace) {
                workspace = getCurrentWorkspace();
            }
            const fieldType = document.getElementById('fieldType').value;
            const required = document.getElementById('fieldRequired').checked;
            
            if (!key || !displayText || !workspace) {
                showStatus('Please fill in all required fields', 'error');
                return;
            }
            
            const fieldData = {
                key,
                workspace,
                displayText,
                helpText,
                placeHolder,
                fieldType,
                required,
                validation: {},
                properties: {}
            };
            
            if (isEdit) {
                // Edit mode: replace the existing field
                const fieldIdx = parseInt(overlay.dataset.fieldIdx);
                if (fieldIdx >= 0 && fieldIdx < currentConfig.fields.length) {
                    // Check for duplicate key only if key has changed
                    const originalKey = currentConfig.fields[fieldIdx].key;
                    if (key !== originalKey && currentConfig.fields.some((f, i) => i !== fieldIdx && f.key === key)) {
                        showStatus(`Field key '${key}' already exists`, 'error');
                        return;
                    }
                    currentConfig.fields[fieldIdx] = fieldData;
                    showStatus('Field updated successfully', 'success');
                }
            } else {
                // Add mode: check for duplicate and push new field
                if (currentConfig.fields.some(f => f.key === key)) {
                    showStatus(`Field key '${key}' already exists`, 'error');
                    return;
                }
                currentConfig.fields.push(fieldData);
                showStatus('Field added successfully', 'success');
            }
        }
        
        // Update editor with new config
        editor.setValue(JSON.stringify(currentConfig, null, 2));
        refreshTree();
        closeModal();
    } catch (e) {
        showStatus(`Error ${isEdit ? 'updating' : 'adding'} item: ` + e.message, 'error');
    }
}

async function loadFromServer() {
    try {
        let configId = currentConfigId;
        
        // If no config ID is currently loaded, prompt the user
        if (!configId) {
            configId = window.prompt('Enter the Configuration ID to load:');
            if (!configId) {
                showStatus('Load cancelled', 'info');
                return;
            }
        } else {
            // If we have a config ID, confirm we're reloading it
            const confirmReload = window.confirm(`Reload configuration: ${configId}?`);
            if (!confirmReload) {
                showStatus('Reload cancelled', 'info');
                return;
            }
        }
        
        showStatus('Loading configuration from server...', 'info');
        
        // Fetch the resolved configuration by ID (matches CLI behavior)
        const response = await fetch(apiUrl(`/nidynamicformfields/v1/resolved-configuration?configurationId=${encodeURIComponent(configId)}`), { headers: { 'X-Editor-Secret': editorSecret || '' } });
        
        if (!response.ok) {
            throw new Error(`Server returned ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        currentConfig = data;
        currentConfigId = configId;  // Update the loaded config ID
        editor.setValue(JSON.stringify(data, null, 2));
        isDirty = false;
        refreshTree();
        showStatus(`Configuration loaded: ${configId}`, 'success');
    } catch (e) {
        showStatus('Failed to load from server: ' + e.message, 'error');
        console.error(e);
    }
}

function mergeResponseIntoDocument(doc, responseData) {
    // Build maps of successful and failed items by key
    const successConfigs = new Map();
    const successGroups = new Map();
    const successFields = new Map();
    const failedConfigKeys = new Set();
    const failedGroupKeys = new Set();
    const failedFieldKeys = new Set();
    
    // Map successful items
    (responseData?.configurations || []).forEach(cfg => {
        if (cfg.key) successConfigs.set(cfg.key, cfg);
    });
    (responseData?.groups || []).forEach(grp => {
        if (grp.key) successGroups.set(grp.key, grp);
    });
    (responseData?.fields || []).forEach(fld => {
        if (fld.key) successFields.set(fld.key, fld);
    });
    
    // Track failed items by their key
    (responseData?.failedConfigurations || []).forEach(cfg => {
        if (cfg.key) failedConfigKeys.add(cfg.key);
    });
    (responseData?.failedGroups || []).forEach(grp => {
        if (grp.key) failedGroupKeys.add(grp.key);
    });
    (responseData?.failedFields || []).forEach(fld => {
        if (fld.key) failedFieldKeys.add(fld.key);
    });
    
    // Merge configurations: successful get new data, failed keep original
    if (Array.isArray(doc.configurations)) {
        doc.configurations = doc.configurations.map(cfg => {
            const key = cfg.key || cfg.name;
            const serverCfg = successConfigs.get(key);
            // Merge: keep original as base, overlay server data (includes new ID)
            return serverCfg ? { ...cfg, ...serverCfg } : cfg;
        });
    } else if (doc.configuration) {
        const key = doc.configuration.key || doc.configuration.name;
        const serverCfg = successConfigs.get(key);
        if (serverCfg) {
            doc.configuration = { ...doc.configuration, ...serverCfg };
        }
    }
    
    // Merge groups: successful get new data, failed keep original for retry
    if (Array.isArray(doc.groups)) {
        doc.groups = doc.groups.map(grp => {
            const serverGrp = successGroups.get(grp.key);
            // Merge: keep original as base, overlay server data (includes new ID)
            return serverGrp ? { ...grp, ...serverGrp } : grp;
        });
    }
    
    // Merge fields: successful get new data, failed keep original for retry
    if (Array.isArray(doc.fields)) {
        doc.fields = doc.fields.map(fld => {
            const serverFld = successFields.get(fld.key);
            // Merge: keep original as base, overlay server data (includes new ID)
            return serverFld ? { ...fld, ...serverFld } : fld;
        });
    }
    
    return doc;
}

function buildSummary(responseData) {
    const successes = {
        configs: (responseData?.configurations || []).length,
        groups: (responseData?.groups || []).length,
        fields: (responseData?.fields || []).length
    };
    const failures = {
        configs: (responseData?.failedConfigurations || []).length,
        groups: (responseData?.failedGroups || []).length,
        fields: (responseData?.failedFields || []).length
    };
    
    const totalSuccessful = successes.configs + successes.groups + successes.fields;
    const totalFailed = failures.configs + failures.groups + failures.fields;
    
    let text = '';
    if (totalFailed > 0) {
        text = `${totalSuccessful} created, ${totalFailed} failed`;
    } else if (totalSuccessful > 0) {
        text = `All ${totalSuccessful} items created successfully`;
    } else {
        text = 'No items created';
    }
    
    let details = '';
    if (successes.configs > 0) details += `✓ Configurations: ${successes.configs}\n`;
    if (successes.groups > 0) details += `✓ Groups: ${successes.groups}\n`;
    if (successes.fields > 0) details += `✓ Fields: ${successes.fields}\n`;
    
    // Add detailed error information for failed items
    if (failures.configs > 0) {
        details += `\n✗ Failed Configurations: ${failures.configs}\n`;
        (responseData?.failedConfigurations || []).forEach(cfg => {
            details += `  • ${cfg.key || cfg.name || 'Unknown'}: ${cfg.error?.message || 'Unknown error'}\n`;
        });
    }
    if (failures.groups > 0) {
        details += `\n✗ Failed Groups: ${failures.groups}\n`;
        (responseData?.failedGroups || []).forEach(grp => {
            details += `  • ${grp.key || 'Unknown'}: ${grp.error?.message || 'Unknown error'}\n`;
        });
    }
    if (failures.fields > 0) {
        details += `\n✗ Failed Fields: ${failures.fields}\n`;
        (responseData?.failedFields || []).forEach(fld => {
            details += `  • ${fld.key || 'Unknown'}: ${fld.error?.message || 'Unknown error'}`;
        });
    }
    
    return { text, details, failed: totalFailed };
}

async function saveToServer() {
    if (!validateDocument()) {
        showStatus('Cannot save: Configuration has errors', 'error');
        return;
    }

    const content = editor.getValue();
    const doc = JSON.parse(content);

    // Helpers to read/write ID across supported shapes
    const getConfigId = (d) => {
        if (d?.configuration?.id) return d.configuration.id;
        if (d?.id) return d.id;
        if (Array.isArray(d?.configurations) && d.configurations.length > 0) {
            return d.configurations[0]?.id || null;
        }
        return null;
    };

    const setConfigId = (d, id) => {
        if (d.configuration) {
            d.configuration.id = id;
            return;
        }
        if (Array.isArray(d.configurations) && d.configurations.length > 0) {
            d.configurations[0].id = id;
            return;
        }
        d.id = id;
    };

    const existingId = getConfigId(doc);
    const isNewConfig = !existingId; // rely on document state only
    const operation = isNewConfig ? 'create' : 'update';
    const confirmMessage = isNewConfig
        ? 'Create this configuration on the server?'
        : 'Apply this configuration to the server? This will update the live configuration.';

    if (!confirm(confirmMessage)) {
        return;
    }

    showStatus(`${isNewConfig ? 'Creating' : 'Updating'} configuration on server...`, 'info');

    try {
        const endpoint = isNewConfig
            ? '/api/dff/configurations'
            : '/nidynamicformfields/v1/update-configurations';

        const response = await fetch(apiUrl(endpoint), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Editor-Secret': editorSecret || '' },
            body: JSON.stringify(doc)
        });

        const responseData = await response.json();

        // Check for HTTP errors
        if (!response.ok) {
            const errorMsg = responseData?.error?.message || responseData?.message || `Server returned ${response.status}`;
            throw new Error(errorMsg);
        }

        // Check for DFF API errors even in 200 responses (with possible partial success)
        if (responseData?.error?.innerErrors && responseData.error.innerErrors.length > 0) {
            const errorMessages = responseData.error.innerErrors
                .map(err => err.message)
                .join('\n');
            
            // NOTE: We don't throw here - we continue to merge successful items
            // The error will be shown after merge and editor update
            const hasSuccesses = (responseData?.configurations?.length || 0) + 
                                (responseData?.groups?.length || 0) + 
                                (responseData?.fields?.length || 0) > 0;
            
            if (!hasSuccesses) {
                // Only throw if there were no successful items to merge
                throw new Error(`Server errors:\n${errorMessages}`);
            }
        }

        if (isNewConfig) {
            let newConfigId = null;
            if (Array.isArray(responseData?.configurations) && responseData.configurations.length > 0) {
                newConfigId = responseData.configurations[0]?.id || null;
            } else if (responseData?.configuration?.id) {
                newConfigId = responseData.configuration.id;
            } else if (responseData?.id) {
                newConfigId = responseData.id;
            }

            // Check if configuration creation failed
            if (!newConfigId) {
                const failedCount = (responseData?.failedConfigurations?.length || 0);
                if (failedCount > 0) {
                    throw new Error(`Configuration creation failed. Check workspace permissions and configuration validity.`);
                }
                showStatus('Configuration created successfully ✓', 'success');
            } else {
                currentConfigId = newConfigId;
                await saveMetadata(newConfigId);

                // Merge successful items from response back into document
                const updatedDoc = JSON.parse(content);
                const mergedDoc = mergeResponseIntoDocument(updatedDoc, responseData);
                
                editor.setValue(JSON.stringify(mergedDoc, null, 2));
                isDirty = false;
                refreshTree();
                
                // Display summary of what succeeded and what failed
                const successSummary = buildSummary(responseData);
                if (successSummary.failed > 0) {
                    showStatus(`Configuration created (ID: ${newConfigId}). ${successSummary.text}`, 'warning');
                    showErrorPanel(`Creation Summary:\n${successSummary.details}`);
                } else {
                    showStatus(`Configuration created successfully (ID: ${newConfigId}) ✓`, 'success');
                }
            }
        } else {
            // Update: track current ID using doc or response
            const updatedId = existingId || (Array.isArray(responseData?.configurations) && responseData.configurations[0]?.id)
                || responseData?.configuration?.id || responseData?.id || null;
            if (updatedId) currentConfigId = updatedId;
            
            // Check if configuration update failed
            if (!updatedId) {
                const failedCount = (responseData?.failedConfigurations?.length || 0);
                if (failedCount > 0) {
                    throw new Error(`Configuration update failed. Check configuration validity.`);
                }
            }
            
            // Merge successful items from response back into document
            const updatedDoc = JSON.parse(content);
            const mergedDoc = mergeResponseIntoDocument(updatedDoc, responseData);
            editor.setValue(JSON.stringify(mergedDoc, null, 2));
            isDirty = false;
            refreshTree();
            
            // Display summary of what succeeded and what failed
            const successSummary = buildSummary(responseData);
            if (successSummary.failed > 0) {
                showStatus(`Configuration updated. ${successSummary.text}`, 'warning');
                showErrorPanel(`Update Summary:\n${successSummary.details}`);
            } else {
                showStatus('Configuration successfully updated on server ✓', 'success');
            }
        }

        return;
    } catch (e) {
        showStatus(`Failed to ${operation} configuration: ` + e.message, 'error');
        console.error(e);
    }
}

async function saveMetadata(configId) {
    try {
        const metadata = {
            configId: configId,
            configFile: 'config.json',
            timestamp: new Date().toISOString()
        };

        const response = await fetch(apiUrl('/api/dff/save-metadata'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Editor-Secret': editorSecret || '' },
            body: JSON.stringify(metadata)
        });

        if (!response.ok) {
            console.warn('Failed to save metadata:', await response.text());
        }
    } catch (e) {
        console.warn('Failed to save metadata:', e);
    }
}

function autoSave() {
    if (isDirty && editor) {
        try {
            const content = editor.getValue();
            // Avoid saving excessively large documents (>2MB)
            const byteLen = new Blob([content]).size;
            if (byteLen > 2 * 1024 * 1024) {
                showStatus('Auto-save skipped: document > 2MB', 'warning');
                return;
            }
            localStorage.setItem('dff-editor-autosave', content);
            localStorage.setItem('dff-editor-autosave-time', new Date().toISOString());
            console.log('Auto-saved at', new Date().toLocaleTimeString());
        } catch (e) {
            if (e && (e.name === 'QuotaExceededError' || e.name === 'NS_ERROR_DOM_QUOTA_REACHED')) {
                showStatus('Auto-save failed: storage quota exceeded. Please download your JSON.', 'error');
            } else {
                console.error('Auto-save failed:', e);
            }
        }
    }
}

function loadAutoSave() {
    try {
        const saved = localStorage.getItem('dff-editor-autosave');
        const savedTime = localStorage.getItem('dff-editor-autosave-time');
        
        if (saved && savedTime) {
            const timeDiff = Date.now() - new Date(savedTime).getTime();
            const hoursDiff = timeDiff / (1000 * 60 * 60);
            
            if (hoursDiff < 24) {
                if (confirm(`Found auto-saved content from ${new Date(savedTime).toLocaleString()}. Restore it?`)) {
                    editor.setValue(saved);
                    showStatus('Auto-saved content restored', 'success');
                }
            }
        }
    } catch (e) {
        console.error('Failed to load auto-save:', e);
    }
}

function showStatus(message, type = 'info') {
    const statusBar = document.getElementById('statusBar');
    const statusText = document.getElementById('statusText');
    
    statusBar.className = 'status-bar ' + type;
    statusText.textContent = message;
    
    // For errors, show detailed panel if message has multiple lines
    if (type === 'error') {
        if (message.includes('\n')) {
            showErrorPanel(message);
            // Keep status bar for 10 seconds
            setTimeout(() => {
                statusBar.className = 'status-bar';
                statusText.textContent = 'Ready';
            }, 10000);
        } else {
            // Keep short errors for 10 seconds
            setTimeout(() => {
                statusBar.className = 'status-bar';
                statusText.textContent = 'Ready';
            }, 10000);
        }
    } else if (type === 'success') {
        // Success messages disappear after 5 seconds
        setTimeout(() => {
            statusBar.className = 'status-bar';
            statusText.textContent = 'Ready';
        }, 5000);
    }
}

function showErrorPanel(message) {
    const errorPanel = document.getElementById('errorPanel');
    const errorContent = document.getElementById('errorPanelContent');
    errorContent.textContent = message;
    errorPanel.classList.add('active');
}

function closeErrorPanel() {
    const errorPanel = document.getElementById('errorPanel');
    errorPanel.classList.remove('active');
}

// Warn before leaving with unsaved changes
window.addEventListener('beforeunload', (e) => {
    if (isDirty) {
        e.preventDefault();
        e.returnValue = '';
    }
});
