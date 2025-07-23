#!/usr/bin/env python3
"""Test script to demonstrate workspace filtering functionality."""

# Simulate workspace filtering logic
templates = [
    {"name": "Battery Test 1", "workspace": "Production Workspace"},
    {"name": "Battery Test 2", "workspace": "Development Workspace"},
    {"name": "Functional Test", "workspace": "Testing Lab"},
    {"name": "Performance Test", "workspace": "Production Workspace"},
]


def filter_by_workspace(templates, workspace_filter):
    """Filter templates by workspace name (case-insensitive partial match)."""
    if not workspace_filter:
        return templates

    filtered = []
    for template in templates:
        ws_name = template["workspace"]
        if workspace_filter.lower() in ws_name.lower():
            filtered.append(template)
    return filtered


# Test different filter scenarios
print("All templates:")
for t in templates:
    print(f"  - {t['name']} (in {t['workspace']})")

print("\nFiltering by 'production':")
filtered = filter_by_workspace(templates, "production")
for t in filtered:
    print(f"  - {t['name']} (in {t['workspace']})")

print("\nFiltering by 'dev':")
filtered = filter_by_workspace(templates, "dev")
for t in filtered:
    print(f"  - {t['name']} (in {t['workspace']})")

print("\nFiltering by 'workspace':")
filtered = filter_by_workspace(templates, "workspace")
for t in filtered:
    print(f"  - {t['name']} (in {t['workspace']})")
