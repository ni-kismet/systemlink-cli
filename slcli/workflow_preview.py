"""Workflow preview (Mermaid diagram) generation utilities.

Separated from workflows_click.py to keep command module concise.
"""

from __future__ import annotations

from typing import Dict, Any, List

# Public-ish constants (imported by tests / commands)
ACTION_TYPE_EMOJI: Dict[str, str] = {
    "MANUAL": "🧑",
    "NOTEBOOK": "📓",
    "SCHEDULE": "📅",
    "JOB": "🛠️",
}

LEGEND_ROWS: List[tuple[str, str]] = [
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
    sanitized = sanitized.replace("/", "-").replace("\\", "-")
    sanitized = sanitized.replace('"', "'").replace("`", "'")
    sanitized = sanitized.replace(":", " ")
    sanitized = sanitized.replace(";", ",")
    sanitized = sanitized.replace("|", " ")
    sanitized = sanitized.replace("&", "and")
    sanitized = " ".join(sanitized.split())
    return sanitized


def generate_mermaid_diagram(workflow_data: Dict[str, Any], enable_emoji: bool = True) -> str:
    """Generate Mermaid stateDiagram-v2 source for a workflow.

    Args:
        workflow_data: Parsed workflow JSON dict
        enable_emoji: Whether to include emoji for action types
    """
    states = workflow_data.get("states", [])
    actions = workflow_data.get("actions", [])
    type_emojis = ACTION_TYPE_EMOJI if enable_emoji else {}

    action_lookup: Dict[str, Dict[str, Any]] = {}
    for action in actions:
        action_name = action["name"]
        execution_action = action.get("executionAction", {})
        action_info = {
            "display": action.get("displayText", action_name),
            "type": execution_action.get("type", ""),
            "privileges": action.get("privilegeSpecificity", []),
            "icon": action.get("iconClass"),
            "notebook_id": execution_action.get("notebookId"),
        }
        action_lookup[action_name] = action_info
        action_lookup[action_name.strip()] = action_info

    lines: List[str] = ["stateDiagram-v2", ""]

    for state in states:
        state_name = state["name"]
        substates = state.get("substates", [])
        if not substates:
            lines.append(f"    {state_name}")
            continue
        for substate in substates:
            sub_name = substate["name"]
            display = substate.get("displayText") or state_name.replace("_", " ").title()
            metadata_parts: List[str] = []
            if state.get("dashboardAvailable"):
                metadata_parts.append("Dashboard")
            available_actions = substate.get("availableActions", [])
            visible_actions = len([a for a in available_actions if a.get("showInUI", True)])
            hidden_actions = len([a for a in available_actions if not a.get("showInUI", True)])
            total_actions = len(available_actions)
            if total_actions:
                if hidden_actions:
                    metadata_parts.append(f"{visible_actions}+{hidden_actions} actions")
                else:
                    metadata_parts.append(
                        f"{visible_actions} action{'s' if visible_actions != 1 else ''}"
                    )
            if metadata_parts:
                label = f"{display}\\n({', '.join(metadata_parts)})"
            else:
                label = display
            if sub_name == state_name:
                lines.append(f"    {state_name} : {label}")
            else:
                lines.append(f"    {state_name}_{sub_name} : {state_name}\\n{label}")
            # Transitions
            for a in available_actions:
                action_name = a.get("action", "")
                next_state = a.get("nextState", "")
                next_sub = a.get("nextSubstate", "")
                show_in_ui = a.get("showInUI", True)
                if not next_state:
                    continue
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
                source = state_name if sub_name == state_name else f"{state_name}_{sub_name}"
                if next_sub and next_sub == next_state:
                    target = next_state
                elif next_sub:
                    target = f"{next_state}_{next_sub}"
                else:
                    target = next_state
                if show_in_ui:
                    lines.append(f"    {source} --> {target} : {action_label}")
                else:
                    lines.append(f"    {source} --> {target} : {action_label}\\nhidden")
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
            {f'<p class=\"workflow-description\">{workflow_description}</p>' if workflow_description else ''}
        </div>
        <div class=\"diagram-container\">
            <div class=\"mermaid\">\n{mermaid_code}\n            </div>
        </div>
{legend_block}
        <div class=\"metadata\">
            <h3>Workflow Details</h3>
            <p><strong>States:</strong> {len(workflow_data.get('states', []))}</p>
            <p><strong>Actions:</strong> {len(workflow_data.get('actions', []))}</p>
            {f'<p><strong>Workspace:</strong> {workflow_data.get("workspace", "N/A")}</p>' if workflow_data.get("workspace") else ''}
        </div>
    </div>
    <script>mermaid.initialize({{ startOnLoad: true, theme: 'default', fontFamily: 'Arial, sans-serif' }});</script>
</body>
</html>"""
