#!/usr/bin/env python3
"""Test script to demonstrate enhanced error output format."""

# Simulate the enhanced error handling with the actual error response
error_response = {
    "failedTestPlanTemplates": [{"name": "freds-test", "templateGroup": "Default"}],
    "error": {
        "name": "Skyline.OneOrMoreErrorsOccurred",
        "message": "One or more errors occurred. See the contained list for details of each error.",
        "innerErrors": [
            {
                "name": "Skyline.WorkOrder.WorkspaceNotFoundOrNoAccess",
                "message": "Workspace // UUID of the workspace where this template belongs does not exist or you do not have permission to perform the create operation.",
                "resourceType": "test plan template",
                "resourceId": "freds-test",
            }
        ],
    },
}

# Simulate the error processing logic
failed_templates = error_response.get("failedTestPlanTemplates", [])
main_error = error_response.get("error", {})
inner_errors = main_error.get("innerErrors", [])

print("✗ Template import failed:")

# Create mapping of resource IDs to error details
error_details = {}
for inner_error in inner_errors:
    resource_id = inner_error.get("resourceId", "Unknown")
    error_name = inner_error.get("name", "")
    error_message = inner_error.get("message", "Unknown error")

    error_details[resource_id] = {"name": error_name, "message": error_message}

# Report errors for each failed template
for failed_template in failed_templates:
    template_name = failed_template.get("name", "Unknown")
    error_info = error_details.get(template_name, {})
    error_name = error_info.get("name", "")
    error_message = error_info.get("message", "Unknown error")

    if error_name:
        error_type = error_name.split(".")[-1] if "." in error_name else error_name
        print(f"  - {template_name}: {error_type} - {error_message}")
    else:
        print(f"  - {template_name}: {error_message}")

print("\nTemplate import failed. See errors above.")
