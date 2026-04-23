---
name: systemlink-dashboard
description: >-
  Create and refine dashboards in NI SystemLink using Grafana and the SystemLink Grafana plugins.
  Use this skill whenever a user asks to build, troubleshoot, or improve a SystemLink dashboard,
  choose the right SystemLink Grafana datasource, configure datasource authentication,
  design panel layouts and variables, or convert SystemLink operational questions into Grafana queries.
  Also use it when the user mentions Grafana in a SystemLink context even if they do not explicitly ask for a dashboard.
argument-hint: >-
  Describe the metric, audience, timeframe, and SystemLink data domain (results, assets, tags, systems, etc.)
---

# SystemLink Dashboard Creation (Grafana)

SystemLink dashboards are Grafana dashboards backed by SystemLink datasources.
This skill helps map business questions to the right datasource, build clear panels, and avoid common setup mistakes.

Primary datasource and plugin reference:
- https://github.com/ni/systemlink-grafana-plugins

## When to use

Use this skill when the user asks to:
- Build a new dashboard in SystemLink
- Pick or configure a SystemLink Grafana datasource
- Create template variables and panel queries
- Improve dashboard readability or troubleshooting
- Debug datasource connection and auth issues in Grafana

## Step 1: Capture dashboard intent

Before proposing queries or panels, gather:

1. Goal: What decision should this dashboard enable?
2. Audience: Operator, test engineer, manager, reliability engineer, etc.
3. Time horizon: Real-time, last 24h, weekly trend, monthly KPI.
4. Scope: Workspace(s), product line, site, test plan, asset family.
5. Actions: What should someone do if a panel turns red or spikes?

If these are missing, ask concise clarifying questions first.

## Step 2: Map the question to the right SystemLink datasource

Prefer datasource selection based on domain:

- Results datasource: yield, failures, step statistics, test throughput
- Test Plans datasource: plan status, assignment, duration, planning queues
- Work Orders datasource: execution flow, queue health, ownership
- Assets datasource: inventory and calibration-related insights
- Systems datasource: system status and fleet health
- Tags datasource: live/near-live process values and trends
- Alarms datasource: alarm volume, severity, and transitions
- Notebooks datasource: notebook outputs and derived analytics
- Products datasource: product-centric rollups
- Workspace datasource: workspace metadata for filtering and selection
- Data Frames datasource: table-like queries for test monitor style analyses

Out-of-box plugin list source:
- https://github.com/ni/systemlink-grafana-plugins (see README Data sources section)

## Dashboard archetypes from bundled examples

When the user asks for a dashboard, classify the request into one of these archetypes first,
then generate a panel plan that matches the same structure and interaction style.

Example sources:
- `slcli/examples/dashboards/System Health-1776974297952.json`
- `slcli/examples/dashboards/Product Summary-1776974375454.json`
- `slcli/examples/dashboards/Lab Test Overview-1776974389923.json`

### Archetype A: System health dashboard (single system operational view)

Use this when users ask for:
- machine health
- alarms + telemetry for a selected system
- calibration and instrument readiness for a station

Panel pattern:
1. Identity and status strip (System Name, Connection Status, Locked Status)
2. Real-time/near-real-time health trend (CPU, memory, disk history)
3. Active alarms table filtered to selected system and workspace
4. Instrument table (location/system filtered) with calibration status coloring

Datasource bundle:
- Systems datasource for system properties
- Tags datasource for telemetry history
- Alarms datasource for active alarm list
- Assets datasource for instrument inventory and calibration
- Workspace datasource for workspace variable

Variable pattern:
- `workspace` query variable from workspace datasource
- `system` query variable from systems datasource, filtered by selected workspace

Interaction pattern:
- Use table/stat links to open system, alarm, asset detail pages
- Reuse a base panel with `-- Dashboard --` datasource for derivative stat panels when practical

### Archetype B: Product summary dashboard (executive + failure funnel view)

Use this when users ask for:
- product-level quality summary
- failures by program/system/DUT/step
- top-N defect concentration views

Panel pattern:
1. Product identity strip (name, part number, family)
2. KPI counters (test plans, test results, DUT count, DUTs under test)
3. State distribution donuts (test result status, test plan status)
4. Assignment/workload matrix by DUT and template
5. Failure sections by dimension (program, system, DUT, step), usually top 25

Datasource bundle:
- Products datasource for product identity
- Test results datasource for failure and status breakdowns
- Test plans datasource for plan-state and assignment context
- Assets datasource for DUT counts
- Workspace datasource for scoping

Variable pattern:
- `workspace` (often include All)
- `product` (required)
- hidden drill variables for cross-panel navigation such as `hostName`, `dut`, `testProgram`,
  `testProgramSystemFilter`, `testProgramDutFilter`

Interaction pattern:
- Use hierarchical drill-down links: product -> system/DUT -> program -> step
- Preserve time range and key filters in links using query params
- Use consistent status color mapping across all failure panels

### Archetype C: Lab test overview dashboard (planning + execution operations)

Use this when users ask for:
- scheduling and overdue test plan tracking
- who owns what in a lab
- operational queue visibility for next time window

Panel pattern:
1. Summary tiles by lifecycle state (New, Defined, Scheduled, In Progress, etc.)
2. Time-window tiles (due start/completion and past due variants)
3. Dynamic test plan table tied to selected summary tile
4. Capacity/assignment charts by system and by user
5. Personal action tables (assigned to me, created by me)

Datasource bundle:
- Test plans datasource as primary source
- Products datasource for product selection
- Workspace datasource for workspace scoping

Variable pattern:
- visible: `workspace`, `product`
- hidden helper variables for tile-driven filtering and field selection
  (for example selected tile, selected state, selected table field set)

Interaction pattern:
- Clicking a summary tile rewrites hidden variables and drives downstream tables
- Preserve date range and context variables in drill links
- Prefer state normalization mappings for readable labels in tables/charts

## Cross-dashboard conventions learned from examples

Apply these conventions by default unless the user asks otherwise:

1. Put summary KPIs first, drill tables/charts second.
2. Use row panels to separate major sections in dense dashboards.
3. Keep status color semantics consistent across panels:
  - green for healthy/completed
  - red for failed/past due/critical
  - orange for pending/warning
  - blue for in-progress/running
4. Add direct links from key cells to SystemLink detail pages.
5. Use `groupBy`, `groupingToMatrix`, `calculateField`, and `limit` transforms
  for top-N and matrix-style breakdowns.
6. Use record limits (commonly 1000) and top-N limits (commonly 25) to keep panels responsive.
7. Include table footers with row counts for operational tables.
8. When aggregating many status queries, use one panel to fetch and derivative panels
  from `-- Dashboard --` to avoid duplicate query logic.

## Archetype selection hints

Choose the starting archetype from user language:

- mentions `health`, `telemetry`, `alarms`, `system status` -> Archetype A
- mentions `yield`, `failures`, `product quality`, `top failing` -> Archetype B
- mentions `schedule`, `due`, `past due`, `assignment`, `lab operations` -> Archetype C

If user intent spans multiple archetypes, start with the dominant one and add one section from
the secondary archetype rather than blending all patterns at once.

## Step 3: Configure datasource authentication correctly

For SystemLink Grafana datasource setup, follow the plugin repo guidance.

Common working patterns:

1. API ingress:
- URL like `https://<environment>-api.lifecyclesolutions.ni.com`
- Add header `x-ni-api-key: <api-key>`

2. UI ingress:
- URL like `https://<environment>.lifecyclesolutions.ni.com`
- Enable With Credentials
- Add header `cookie: <copied-session-cookie>`

If Save and Test fails, verify:
- URL points to the intended ingress
- Header names are exact (`x-ni-api-key` or `cookie`)
- API key/session has permission for the target service
- Workspace and service endpoints are reachable

## Step 4: Design the first dashboard slice

Start with a thin vertical slice (3 to 5 panels), not a full wall of charts.

Recommended first slice:
1. KPI panel: current headline metric
2. Trend panel: same metric over time
3. Breakdown panel: by workspace/system/product/state
4. Exception panel: top failures, alarms, or overdue items
5. Context table: records backing the aggregate views

Prefer this sequence because it supports detect -> diagnose -> act.

## Step 5: Build robust variables and filters

Use variables to make dashboards reusable:
- `workspace`
- `product` or `test_plan`
- `system`
- `time_window` (when practical)

Guidelines:
- Keep variable names stable and descriptive
- Use multi-select only where needed
- Include an All option for executive views
- Ensure every panel respects key variables

## Step 6: Query and panel conventions

When composing queries:
- Align aggregations with panel type (single value, time series, table, bar)
- Keep units explicit (percent, seconds, count)
- Limit cardinality in legend-heavy panels
- Use sensible row limits for tables
- Add panel descriptions when semantics are not obvious

For troubleshooting-oriented dashboards, include both:
- A high-level aggregate panel
- A drill-down table panel with identifiers

## Step 7: Validation checklist before handoff

Validate dashboard quality using this checklist:

1. Every panel has a clear title and unit.
2. Time range and refresh behavior match use case.
3. Variables are applied consistently.
4. At least one panel supports drill-down behavior.
5. Empty-state behavior is understandable.
6. Datasource test passes and queries return expected shape.

## Troubleshooting playbook

If dashboard panels fail or show no data:

1. Confirm datasource Save and Test succeeds.
2. Check query time range is broad enough.
3. Temporarily remove variable filters to isolate bad predicates.
4. Validate workspace or entity IDs used in filters.
5. Test query in Grafana Explore before embedding in dashboard.
6. Verify credentials have access to the specific SystemLink service.

## Response format for this skill

When responding to the user, structure output as:

1. Dashboard intent summary (goal, audience, scope)
2. Recommended datasource(s) and why
3. Proposed panel set (3 to 7 panels)
4. Variable strategy
5. First implementation steps
6. Risks or unknowns needing user input

If the user asks for implementation details, provide concrete Grafana steps and example query strategy tailored to the chosen datasource.
