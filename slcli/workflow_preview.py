"""Workflow preview (Mermaid diagram) generation utilities.

Separated from workflows_click.py to keep command module concise.
"""

from __future__ import annotations

from typing import Dict, Any, List, Tuple, Optional

# Public-ish constants (imported by tests / commands)
ACTION_TYPE_EMOJI: Dict[str, str] = {
    "MANUAL": "🧑",
    "NOTEBOOK": "📓",
    "SCHEDULE": "📅",
    "JOB": "🛠️",
}
LEGEND_ROWS: List[Tuple[str, str]] = [
    ("🧑", "Manual action"),
    ("📓", "Notebook action"),
    ("📅", "Schedule action"),
    ("🛠️", "Job action"),
    ("(priv1, priv2)", "Privileges required"),
    ("NB abcdef..", "Truncated Notebook ID"),
    ("⚡️ NAME", "UI icon class"),
    ("hidden", "Hidden (not shown in UI)"),
]


def sanitize_mermaid_label(label: str) -> str:
    """Sanitize label text for Mermaid diagram compatibility.

    Args:
        label: Raw label text
    Returns:
        Sanitized label safe for inclusion inside Mermaid stateDiagram labels
    """
    if not label:
        return label
    sanitized = label.replace("[", "(").replace("]", ")").replace("🔗", "")
    # Keep backslashes (needed for Mermaid newline escapes) but normalize forward slashes
    sanitized = sanitized.replace("/", "-")
    sanitized = sanitized.replace('"', "'").replace("`", "'")
    sanitized = sanitized.replace(":", " ")
    sanitized = sanitized.replace(";", ",")
    sanitized = sanitized.replace("|", " ")
    sanitized = sanitized.replace("&", "and")
    sanitized = " ".join(sanitized.split())
    return sanitized


def generate_mermaid_diagram(workflow_data: Dict[str, Any], enable_emoji: bool = True) -> str:
    """Generate Mermaid stateDiagram-v2 source for a workflow.

    Now produces hierarchical composite states instead of flattening substates.

    Args:
        workflow_data: Parsed workflow JSON dict
        enable_emoji: Whether to include emoji for action types
    """
    states: List[Dict[str, Any]] = workflow_data.get("states", [])
    actions: List[Dict[str, Any]] = workflow_data.get("actions", [])
    type_emojis = ACTION_TYPE_EMOJI if enable_emoji else {}

    # Build action lookup for transition label enrichment
    action_lookup: Dict[str, Dict[str, Any]] = {}
    for action in actions:
        name = action.get("name", "")
        execution_action = action.get("executionAction", {})
        info = {
            "display": action.get("displayText", name),
            "type": execution_action.get("type", ""),
            "privileges": action.get("privilegeSpecificity", []),
            "icon": action.get("iconClass"),
            "notebook_id": execution_action.get("notebookId"),
        }
        action_lookup[name] = info
        action_lookup[name.strip()] = info

    lines: List[str] = ["stateDiagram-v2", ""]

    # Mapping (state, substate) -> node identifier used in transitions
    node_id_map: Dict[Tuple[str, str], str] = {}

    def make_node_id(parent: str, sub: str) -> str:
        # Ensure internal substate id never collides with the composite container name
        if sub == parent:
            base = f"{parent}_BASE"
        else:
            base = f"{parent}_{sub}"
        # Sanitize ID: replace spaces and disallowed chars with underscores
        safe = "".join(c if c.isalnum() or c in ("_",) else "_" for c in base)
        return safe

    # First pass: declare states (simple or composite) and internal nodes
    for state in states:
        raw_state_name = state.get("name")
        if not isinstance(raw_state_name, str) or not raw_state_name:
            # Skip invalid state entries
            continue
        state_name: str = raw_state_name
        substates: List[Dict[str, Any]] = state.get("substates", [])
        if not substates:
            # No substates: simple state
            display_label = state_name.replace("_", " ").title()
            lines.append(f"    {state_name}: {sanitize_mermaid_label(display_label)}")
            continue

        # Determine if this should be composite: more than one substate OR differing names
        unique_sub_names = {s.get("name") for s in substates if isinstance(s.get("name"), str)}
        composite = len(unique_sub_names) > 1 or (
            len(unique_sub_names) == 1 and state_name not in unique_sub_names
        )
        ds_val = state.get("defaultSubstate")
        default_sub: Optional[str] = ds_val if isinstance(ds_val, str) else None
        if composite:
            lines.append(f"    state {state_name} {{")
            # Add initial pointer if default specified
            if default_sub and any(s.get("name") == default_sub for s in substates):
                default_id = make_node_id(state_name, default_sub)
                lines.append(f"        [*] --> {default_id}")
        # Emit substate nodes
        for sub in substates:
            raw_sub_name = sub.get("name")
            if not isinstance(raw_sub_name, str) or not raw_sub_name:
                continue
            sub_name: str = raw_sub_name
            node_id = make_node_id(state_name, sub_name)
            node_id_map[(state_name, sub_name)] = node_id
            display = sub.get("displayText") or (
                sub_name.replace("_", " ") if sub_name else state_name
            )
            metadata_parts: List[str] = []
            if state.get("dashboardAvailable"):
                metadata_parts.append("Dashboard")
            available_actions = sub.get("availableActions", [])
            visible_actions = len([a for a in available_actions if a.get("showInUI", True)])
            hidden_actions = len([a for a in available_actions if not a.get("showInUI", True)])
            if available_actions:
                if hidden_actions:
                    metadata_parts.append(f"{visible_actions}+{hidden_actions} actions")
                else:
                    metadata_parts.append(
                        f"{visible_actions} action{'s' if visible_actions != 1 else ''}"
                    )
            if metadata_parts:
                label_main = sanitize_mermaid_label(display)
                label_meta = sanitize_mermaid_label(f"({', '.join(metadata_parts)})")
                label = f"{label_main}\\n{label_meta}"
            else:
                label = sanitize_mermaid_label(display)
            indent = "        " if composite else "    "
            lines.append(f"{indent}{node_id}: {sanitize_mermaid_label(label)}")
        if composite:
            lines.append("    }")

    # Second pass: transitions using node_id_map
    for state in states:
        raw_state_name = state.get("name")
        if not isinstance(raw_state_name, str) or not raw_state_name:
            continue
        state_name = raw_state_name
        for sub in state.get("substates", []):
            source_sub = sub.get("name")
            if not isinstance(source_sub, str) or not source_sub:
                continue
            source_id = node_id_map.get((state_name, source_sub)) or state_name
            for a in sub.get("availableActions", []):
                next_state = a.get("nextState")
                if not next_state:
                    continue
                next_sub = a.get("nextSubstate") or next_state
                if not isinstance(next_state, str) or not isinstance(next_sub, str):
                    continue
                target_id = (
                    node_id_map.get((next_state, next_sub))
                    or node_id_map.get((next_state, next_state))
                    or next_state
                )
                action_name = a.get("action", "")
                show_in_ui = a.get("showInUI", True)
                info = (
                    action_lookup.get(action_name) or action_lookup.get(action_name.strip()) or {}
                )
                emoji = type_emojis.get(info.get("type", ""), "")
                segs: List[str] = []
                if emoji:
                    segs.append(emoji)
                segs.append(info.get("display", action_name))
                if info.get("type"):
                    segs.append(f"({info['type']})")
                privs = info.get("privileges", [])
                if privs:
                    segs.append(f"({', '.join(privs)})")
                nb = info.get("notebook_id")
                if info.get("type") == "NOTEBOOK" and nb:
                    segs.append(f"NB {nb[:8]}...")
                icon = info.get("icon")
                if icon:
                    segs.append(f"⚡️ {icon}")
                segs = [sanitize_mermaid_label(s) for s in segs if s]
                action_label = "\\n".join(segs)
                if show_in_ui:
                    lines.append(f"    {source_id} --> {target_id} : {action_label}")
                else:
                    lines.append(f"    {source_id} --> {target_id} : {action_label}\\nhidden")

    lines.append("")
    return "\n".join(lines)


def build_legend_html() -> str:
    """Return legend HTML using LEGEND_ROWS constant."""
    rows = "\n".join(f"                <tr><td>{k}</td><td>{v}</td></tr>" for k, v in LEGEND_ROWS)
    return (
        '    <div class="legend" style="text-align:left; max-width:400px; margin:0 0 20px 0; background:#fafafa; border:1px solid #ddd; padding:12px; border-radius:6px; font-size:0.9em;">\n'
        "            <strong>Legend</strong>\n"
        '            <table class="legend-table">\n'
        f"{rows}\n"
        "            </table>\n"
        "        </div>"
    )


def generate_html_with_mermaid(
    workflow_data: Dict[str, Any], mermaid_code: str, include_legend: bool = True
) -> str:
    """Generate HTML document for a workflow diagram.

    Args:
        workflow_data: Workflow JSON
        mermaid_code: Mermaid diagram source
        include_legend: Whether to include legend block
    """
    workflow_name = workflow_data.get("name", "Workflow")
    workflow_description = workflow_data.get("description", "")
    legend_block = build_legend_html() if include_legend else ""
    # Precompute optional HTML fragments to avoid nested f-strings inside expression braces
    description_html = (
        f'<p class="workflow-description">{workflow_description}</p>'
        if workflow_description
        else ""
    )
    workspace_value = workflow_data.get("workspace")
    if workspace_value:
        workspace_html = f"<p><strong>Workspace:</strong> {workspace_value}</p>"
    else:
        workspace_html = ""
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>Workflow Preview: {workflow_name}</title>
    <script src=\"https://cdn.jsdelivr.net/npm/mermaid@10.6.1/dist/mermaid.min.js\"></script>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header {{ margin-bottom: 20px; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
        .workflow-title {{ color: #333; margin: 0; }}
        .workflow-description {{ color: #666; margin: 5px 0 0 0; }}
        .diagram-container {{ text-align: center; margin: 20px 0; }}
        .metadata {{ margin-top: 20px; font-size: 0.9em; color: #666; }}
        .legend-table {{ width: 100%; border-collapse: collapse; margin: 8px 0 0 0; }}
        .legend-table td {{ padding: 4px 8px; border-bottom: 1px solid #eee; vertical-align: top; }}
        .legend-table td:first-child {{ font-family: monospace; font-weight: bold; width: 120px; }}
    </style>
</head>
<body>
    <div class=\"container\">
        <div class=\"header\">
            <h1 class=\"workflow-title\">{workflow_name}</h1>
                {description_html}
        </div>
        <div class=\"diagram-container\">
            <div class=\"mermaid\">\n{mermaid_code}\n            </div>
        </div>
{legend_block}
        <div class=\"metadata\">
            <h3>Workflow Details</h3>
            <p><strong>States:</strong> {len(workflow_data.get('states', []))}</p>
            <p><strong>Actions:</strong> {len(workflow_data.get('actions', []))}</p>
            {workspace_html}
        </div>
    </div>
    <script>mermaid.initialize({{ startOnLoad: true, theme: 'default', fontFamily: 'Arial, sans-serif' }});</script>
</body>
</html>"""
