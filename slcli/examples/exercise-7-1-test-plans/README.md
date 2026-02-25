# Exercise 7-1: Create and Schedule Test Plans — Instructor Setup Guide

Supporting training data for **Exercise 7-1: Create and Schedule Test Plans**.

## Overview

This example provisions the infrastructure needed for the guided and unguided
scheduling exercise. Students create a test plan for a battery pack product,
schedule it on an environmental chamber using the Scheduling Assistant, and
review work across multiple calendar views.

## Quick Start

```bash
# Preview what will be created (recommended before running)
slcli example install exercise-7-1-test-plans -w <workspace> --dry-run

# Install into the target workspace
slcli example install exercise-7-1-test-plans -w <workspace>

# Remove all provisioned resources when the session ends
slcli example delete exercise-7-1-test-plans -w <workspace>
```

## Resources Provisioned

| Type       | Count | Details                                                |
| ---------- | ----- | ------------------------------------------------------ |
| Location   | 1     | Battery Testing Lab (Austin, TX)                       |
| Product    | 1     | Model ABC — Battery Packs family                       |
| System     | 1     | Chamber B (thermal cycle test stand)                   |
| Asset      | 1     | Slot_01 — Fixture on Chamber B                         |
| DUT        | 1     | BAT-DUT-C01                                            |
| Workflow   | 1     | Battery Test Plan Workflow (full state machine)        |
| Template   | 1     | Blank Test Plan                                        |
| Work Order | 1     | Battery Validation – Model ABC                         |
| Work Item  | 1     | Thermal Cycle Test (pre-created test plan, state: NEW) |

**Total: 9 resources**

## Exercise Alignment

### Guided Steps

| Exercise section                      | Resource used                                     |
| ------------------------------------- | ------------------------------------------------- |
| Start from Work Orders                | Work Order: **Battery Validation – Model ABC**    |
| Create test plan — product family     | Product: **Model ABC** (family: Battery Packs)    |
| Create test plan — select template    | Template: **Blank Test Plan**                     |
| Create test plan — select DUT         | DUT: **BAT-DUT-C01**                              |
| Scheduling Assistant — select system  | System: **Chamber B**                             |
| Scheduling Assistant — select fixture | Asset/Fixture: **Slot_01**                        |
| Verify Fixture Allocation             | Fixture column shows **Slot_01** on the work item |
| Adjust schedule from DUT              | Assets > **BAT-DUT-C01** > Work Items             |
| View schedule for a specific system   | Systems > **Chamber B** > Schedule tab            |

### Unguided / Assess Your Skills

| Skill step                         | Resource used                                  |
| ---------------------------------- | ---------------------------------------------- |
| Create test plan from a work order | Work Order: **Battery Validation – Model ABC** |
| Create test plan from a DUT        | DUT: **BAT-DUT-C01** > Work Items tab          |

## Instructor Notes

- The **Thermal Cycle Test** work item is pre-created (linked to the work order)
  so students can practice the Scheduling Assistant steps immediately after
  completing the Create test plan wizard.
- **Slot_01** is an `asset` with `assetType: FIXTURE` on Chamber B.
  It appears in the Scheduling Assistant's fixture picker and in the
  Fixtures column of the Work Items table.
- **BAT-DUT-C01** shares the same naming convention as the DUTs
  in exercise-5-1-parametric-insights (e.g. `BAT-DUT-C01`).
- All resources share the tag `exercise-7-1-test-plans`, which the cleanup
  command uses to delete only exercise resources without touching other data.

## Cleanup

```bash
slcli example delete exercise-7-1-test-plans -w <workspace>
```

Deletion order (respects dependencies):

1. `work_item`
2. `work_order`
3. `testtemplate`
4. `workflow`
5. `dut`
6. `asset` (fixture Slot_01)
7. `system` (Chamber B)
8. `product` (Model ABC)
9. `location` (Battery Testing Lab)
