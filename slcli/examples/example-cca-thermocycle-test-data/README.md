# Exercise 5-1: Parametric Insights — Instructor Setup Guide

Supporting training data for **Exercise 5-1: Query and Visualize Parametric Test Data**.

## Overview

This example provisions a realistic six-week dataset of thermal cycle test results for a
lithium-ion battery pack product (**Model ABC**) collected across three test stands.
Students use Test Insights to locate the product, group results by system, visualize
parametric measurements in a data space, and save their work.

## Quick Start

```bash
# Preview what will be created (recommended before running)
slcli example install exercise-5-1-parametric-insights -w <workspace> --dry-run

# Install into the target workspace
slcli example install exercise-5-1-parametric-insights -w <workspace>

# Remove all provisioned resources when the session ends
slcli example delete exercise-5-1-parametric-insights -w <workspace>
```

## Resources Provisioned

| Type               | Count | Details                                            |
| ------------------ | ----- | -------------------------------------------------- |
| Location           | 1     | Battery Testing Lab (Austin, TX)                   |
| Products           | 3     | Model ABC (primary), Model XYZ, Model ABC Rev B    |
| Systems            | 3     | Thermal Cycle Tester TC-01, TC-02, TC-03           |
| DUTs               | 5     | One per system + XYZ and Rev B units               |
| Test results       | 18    | Model ABC: 6 cycles per stand, Jan 6 – Feb 13 2026 |
| Test results       | 4     | Model XYZ acceptance tests (distractor)            |
| Test results       | 3     | Model ABC Rev B qualification (distractor)         |
| Incomplete results | 3     | Aborted/skipped runs (realism)                     |

**Total: 28 test results across 3 products**

## Measurements Recorded per Model ABC Result

Each of the 18 Model ABC results carries the following measurement properties:

| Field                                           | Unit | Spec limit    |
| ----------------------------------------------- | ---- | ------------- |
| `cycle_count`                                   | —    | informational |
| `cell_temperature_1_c` … `cell_temperature_4_c` | °C   | max 42 °C     |
| `ambient_temperature_c`                         | °C   | informational |
| `terminal_voltage_v`                            | V    | min 3.70 V    |
| `charge_current_a`                              | A    | 1.20 – 1.60 A |
| `capacity_ah`                                   | Ah   | min 50.0 Ah   |
| `internal_resistance_mohm`                      | mΩ   | max 20.0 mΩ   |
| `state_of_charge_pct`                           | %    | min 98.0 %    |

## Deliberate Data Patterns for Student Discovery

The dataset contains several anomalies that students should discover through the
visualization tasks in the exercise:

### TC-03 Temperature Offset (Step 3.13 — Color by System)

TC-03 consistently runs **3–4 °C warmer** than TC-01 and TC-02 across all six cycles.
When students color a scatter plot by System, this offset becomes immediately visible.
Instructors can prompt: _"What might cause one stand to run consistently hotter?"_
(Suggested answer: chamber thermocouple calibration drift.)

### TC-01 Cycle 5 — Internal Resistance Spike (Feb 4, FAIL)

`internal_resistance_mohm` spikes to **21.4 mΩ** (spec: ≤ 20.0 mΩ), causing the only
FAIL result on TC-01. The value returns to 15.8 mΩ in Cycle 6 after maintenance.
Visible in a line chart with Time on X-axis and `internal_resistance_mohm` on Y-axis.

### TC-03 Cycle 4 — Cell Temperature Spike (Jan 30, FAIL)

`cell_temperature_3_c` spikes to **44.8 °C** (spec: ≤ 42 °C) while the other three
channels remain normal (~41 °C). This isolated channel spike, visible in a line chart,
suggests a faulty cell or mounting contact rather than an ambient condition.

### Capacity and Voltage Aging Trend

Both `capacity_ah` and `terminal_voltage_v` show a slow monotonic decrease across all
three stands (approximately 1 Ah and 0.05 V over six cycles). This is consistent with
normal lithium-ion aging and is visible when plotting with Time on X-axis.

### Distractor Products

The Products table will show **Model ABC**, **Model XYZ**, and **Model ABC Rev B**.
Students must identify the correct product by part number `BAT-MODEL-ABC-001`, not just
by name. Model XYZ uses different measurement fields (capacitor bank); Model ABC Rev B
uses the same fields but with noticeably lower internal resistance (~10 mΩ vs ~12–15 mΩ),
illustrating the design improvement.

## Estimated Setup Time

~5 minutes

## Requirements

- SystemLink Enterprise 2024.1 or later
- Test Insights module with Data Spaces enabled
- Target workspace must exist before running install
