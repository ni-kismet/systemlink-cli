# Datasheet-to-specifications workflow

Use this workflow when the user wants to create a product and upload specifications
from a datasheet (PDF, CSV, or structured text). This covers the full path from
raw document to live SystemLink specs.

> **Validation-first mindset.** SystemLink specifications are designed primarily
> for **pre-production validation and verification** — defining what parameters
> a test lab must confirm before a product enters production. Think of each spec
> as a test requirement: it tells the lab what to measure, under what conditions,
> and what limits determine pass or fail. Not every datasheet parameter needs a
> spec — focus on parameters that are testable, measurable, and relevant to the
> user's acceptance criteria.

## Step 1 — Clarify product identity and workspace

Before touching any data, ask the user:

1. **Product name and part number.** Extract a candidate from the datasheet title
   page or cover. Propose a short friendly name (part number + concise
   description) and the raw part number, then **ask the user to confirm or
   adjust both values**.
2. **Product family.** Suggest a family based on the datasheet application domain
   (e.g. "Audio", "Power", "Sensor", "Semiconductor", "Passive", "Connector",
   "Test Equipment", "Module") but **always ask the user to confirm** — do not
   silently infer the family.
3. **Existing product check.** Search by name _and_ part number:
   ```bash
   slcli testmonitor product list --name "<candidate>" -f json
   slcli testmonitor product list --part-number "<part>" -f json
   ```
   If a match exists, tell the user the product name, part number, workspace, and
   ask whether to add specs to it or create a new product (possibly in a different
   workspace).
4. **Workspace.** Default to the user's profile workspace. If an existing product
   was found, show which workspace it lives in and ask the user to confirm or
   specify a different one by name. Never silently pick a workspace.
5. **Multi-variant detection.** Many datasheets cover multiple part numbers
   (e.g. Si8230/1/2/3/4/5/7/8, SN54HC595/SN74HC595). Check the title page,
   ordering guide, or device overview table for multiple variants. If found,
   ask the user which approach to use:

   **Option A — Single product (default).** Create one product using the
   family part number (e.g. "Si823x"). Shared specs have no device condition.
   Variant-specific specs get a STRING condition `"Device"` listing the
   applicable variants. Best for cataloging/reference.

   **Option B — One product per variant.** Create a separate product for each
   variant (Si8230, Si8231, ...) with the same `family`. Shared specs are
   duplicated across all products. Variant-specific specs appear only on
   their product. Best for production test workflows where test results are
   filed per specific part number.

   **Option C — Single variant only.** Create one product for a specific
   variant the user selects (e.g. just "Si8233"). Import only the specs that
   apply to that variant (shared specs + that variant's specific specs).
   Variant-specific specs for other devices are skipped entirely. Best when
   the user only cares about one part number from a multi-variant datasheet.

   Default to Option A unless the user requests otherwise.

## Step 2 — Create the product (if needed)

```bash
slcli testmonitor product create \
  --part-number "<PART>" \
  --name "<FRIENDLY_NAME>" \
  --family "<FAMILY>" \
  --workspace "<WORKSPACE_NAME>" \
  --keyword "<kw1>" --keyword "<kw2>" \
  --property "manufacturer=<MFG>" \
  --property "package=<PKG>" \
  -f json
```

Populate product fields from the datasheet:

| Product field | Where to find it on a datasheet                                   |
| ------------- | ----------------------------------------------------------------- |
| `partNumber`  | Title page, ordering info, or device summary table                |
| `name`        | Short form of the title (part number + concise description)       |
| `family`      | Application domain (Audio, Power, Sensor, Passive, Module, etc.)  |
| `keywords`    | From "Applications", "Features", or "Description" sections        |
| `properties`  | manufacturer, package type, form factor from device summary table |

## Step 3 — Extract specification data

### PDF datasheets

1. Install a PDF extraction library if needed (e.g. `pip install pymupdf`).
2. Scan the table of contents or page headings to identify all specification
   sections. Do **not** hard-code a fixed list — different product domains use
   different section names.
3. Extract text from pages containing specification tables. Write extracted
   text to `build/ai/<partnum>-specs-raw.txt` for review.

**Ask the user which sections to import.**

Common section names vary by product domain. Search the document for headings
that match typical patterns and present the discovered sections to the user:

| Domain            | Common section names                                         |
| ----------------- | ------------------------------------------------------------ |
| Semiconductor ICs | Absolute Maximum Ratings, ESD Ratings, Recommended Operating |
|                   | Conditions, Thermal Information, Electrical Characteristics, |
|                   | Switching Characteristics, DC/AC Characteristics             |
| Passive (C, R, L) | Ratings, Electrical Characteristics, Temperature Derating,   |
|                   | Environmental Characteristics                                |
| Sensors           | Performance Specifications, Accuracy, Sensitivity,           |
|                   | Operating Conditions, Environmental Specifications           |
| Power supplies    | Input Characteristics, Output Characteristics, Protection,   |
|                   | Efficiency, Derating                                         |
| Connectors        | Electrical Ratings, Mechanical Specifications,               |
|                   | Environmental Specifications                                 |
| Test equipment    | Accuracy Specifications, Measurement Ranges,                 |
|                   | Environmental Operating Conditions                           |

> **Guideline:** Scan for any heading followed by a table containing MIN, MAX,
> TYP, NOM, VALUE, UNIT, or LIMIT columns — that is a specification table
> regardless of its name.

#### Testability filter

After identifying sections, help the user decide which parameters to import
by considering testability:

- **Include** parameters the lab can measure with standard equipment (voltages,
  currents, timing, power, temperature thresholds, accuracy tolerances).
- **Include** absolute maximum ratings when they define damage thresholds the
  lab needs to verify operating margin against.
- **Consider skipping** informational-only parameters that no test will check
  (package dimensions, pin descriptions, ordering codes, thermal resistance
  values that are fab-dependent and not testable by the customer).
- **Ask the user** if you're unsure whether a section is relevant to their
  validation plan. Some users want comprehensive cataloging; others want only
  the parameters their test station will actually measure.

When in doubt, include the parameter — it's easier to delete unused specs later
than to re-extract them from the datasheet.

### Flat / key-value datasheets

Some datasheets (especially for batteries, connectors, and simple passives)
present specs as a **key-value list** rather than a table with columns:

```
Nominal voltage      3V
Nominal capacity     225mAh
Diameter(Max.)       20.0mm
```

When the datasheet has no MIN/TYP/MAX table structure:

- Treat each key-value pair as one spec row.
- Parse the unit from the value string (e.g. "225mAh" → value=225, unit="mAh").
- Check for **qualifiers in the label** that indicate which limit field to use:
  - `(Max.)` or `(max)` → `limit.max`
  - `(Min.)` or `(min)` → `limit.min`
  - `(Typ.)`, `(typ)`, `(Nom.)`, `Nominal` → `limit.typical`
  - `Approx.` / `approximately` → `limit.typical` (add "Approx." to `properties.notes`)
- If no qualifier is present, default to `limit.typical` for single values.
- **Footnotes** (e.g. "*1 Without tabs", "*2 Consult manufacturer at 70°C+")
  go into `properties.notes`. Do not discard them — they contain important
  measurement conditions and caveats.
- Ranges like "-30°C to +85°C" should be split into `limit.min` and `limit.max`.

### CSV files

Inspect headers and rows. Common column mappings:

| CSV column            | Spec field         |
| --------------------- | ------------------ |
| Spec Name / Parameter | `name`             |
| Nominal Value         | `limit.typical`    |
| Lower Limit / Min     | `limit.min`        |
| Upper Limit / Max     | `limit.max`        |
| Units                 | `unit`             |
| Category              | `category`         |
| Notes                 | `properties.notes` |

If a cell contains a range like "-0.5 to +0.5", parse it into `min` and `max`.

## Step 4 — Map datasheet rows to spec JSON

### Symbol field

Many datasheet spec tables have a **symbol** column (often the first column)
containing short engineering notation like `PO`, `IO`, `VCC`, `ICC`, `THD+N`,
`RθJA`, or `ESR`. When present, always map it to the spec `symbol` field.
This is distinct from `specId` — the symbol is the notation from the datasheet,
while specId is a unique identifier you generate.

Not all datasheets have symbols. Passive component datasheets, sensor spec
tables, and test equipment manuals often omit them. When no symbol column
exists, leave `symbol` null and rely on `specId` and `name`.

### Spec ID conventions

Generate a short, unique `specId` from the datasheet symbol or parameter name:

- Use the datasheet symbol when available (e.g. `VCC`, `PO`, `ICC`, `ESR`).
- Prefix with a short category abbreviation derived from the section name for
  disambiguation. Choose a 2-4 character prefix that makes sense for the
  product domain. Examples:

  | Section type               | Prefix examples |
  | -------------------------- | --------------- |
  | Absolute Maximum Ratings   | `AMR-`          |
  | ESD Ratings                | `ESD-`          |
  | Recommended Operating      | `ROC-`          |
  | Thermal Information        | `TH-`           |
  | Electrical Characteristics | `EC-`           |
  | Switching Characteristics  | `SW-`           |
  | Input Characteristics      | `IN-`           |
  | Output Characteristics     | `OUT-`          |
  | Accuracy Specifications    | `ACC-`          |
  | Environmental Specs        | `ENV-`          |
  | Dimensions / Mechanical    | `DIM-`          |

  When a datasheet has only one section (e.g. "Specifications"), omit the
  prefix entirely and use short descriptive IDs like `VNOM`, `CNOM`, `TEMP-OP`.

- Append a disambiguator when the same parameter appears under different
  conditions (e.g. `EC-PO-BTL-10-74` for output power BTL at 10% THD, 7.4V).
- Keep specIds short but human-readable. Never fabricate numeric values.

### Field mapping

| Datasheet column       | Spec field      |
| ---------------------- | --------------- |
| Symbol (first column)  | `symbol`        |
| Parameter (second col) | `name`          |
| MIN                    | `limit.min`     |
| TYP / NOM              | `limit.typical` |
| MAX                    | `limit.max`     |
| UNIT                   | `unit`          |
| Test Conditions        | `conditions`    |

Only include limit fields that have actual values. Do not set missing limits to 0.

### Category and block

- **`category`** — Set to the datasheet section name the spec was extracted from
  (e.g. "Electrical Characteristics", "Absolute Maximum Ratings", "Switching
  Characteristics"). This groups specs by their source section.
- **`block`** — Set to the functional subsystem or circuit block of the product
  that the spec belongs to. For simple single-function devices (e.g. a gate
  driver, voltage regulator, or passive component), leave `block` empty or omit
  it — there is only one logical block. For complex multi-function products
  (e.g. a USB hub with power delivery, an SoC with RF + baseband, or a mixed-
  signal IC with ADC + DAC sections), set `block` to the relevant subsystem
  name (e.g. `"USB"`, `"Power"`, `"RF Front End"`, `"ADC"`, `"DAC"`).

  Use the same block name consistently across all specs belonging to that
  subsystem. Choose short, descriptive names that match how the datasheet
  organizes its sections or how the product's functional blocks are described
  in the block diagram.

> **Limits as acceptance criteria.** The min/max values in a spec define the
> pass/fail boundaries for automated test results. When a test measurement is
> compared against these limits, it must fall within the range to pass.
> Datasheet limits are a starting point — some users apply **guard-banding**
> (tighter limits than the datasheet) to build in manufacturing margin. If the
> user mentions guard bands or tighter tolerances, adjust the limits accordingly
> and note the original datasheet values in `properties.notes`.
>
> Every PARAMETRIC spec should have at least one limit bound (min, max, or
> typical) so that test results can be automatically evaluated. A spec with no
> limits cannot drive pass/fail decisions — flag these to the user.

Some tables use a single VALUE column instead of MIN/TYP/MAX (e.g. ESD Ratings).
When a value is prefixed with ± (e.g. "±1000"), convert it to `limit.min = -1000`
and `limit.max = 1000`. When a section uses VALUE alone without ±, treat it as
`limit.typical` unless context (like ESD ratings) implies it is a threshold.

### Conditions

> **Conditions as test setup instructions.** Each condition on a spec tells the
> test lab exactly how to configure the equipment before measuring. A supply
> voltage condition means "set the power supply to this value"; a load condition
> means "connect this load impedance"; a temperature condition means "set the
> chamber to this temperature." Complete, accurate conditions are essential —
> without them, the lab cannot reproduce the measurement that the spec's limits
> are defined against.

**Ask the user** whether to include test conditions. Many electrical specs have
conditions like "PVCC = 12 V, RL = 8 Ω, f = 1 kHz, 1SPW mode". When conditions
are requested:

- Use `conditionType: "NUMERIC"` for measurable quantities with units.
- Use `conditionType: "STRING"` for modes, configurations, pin states.
- Group related conditions on the same spec entry.
- When a parameter row has multiple test condition variants (e.g. output power
  at different voltages/loads), create a **separate spec entry per variant** with
  the conditions and a unique specId suffix.

#### Device variant conditions (multi-variant datasheets)

When using Option A (single product) for a multi-variant datasheet, specs that
apply only to specific variants need a `"Device"` condition:

```json
{
  "name": "Device",
  "value": {
    "conditionType": "STRING",
    "discrete": ["Si8233", "Si8234", "Si8235", "Si8238"]
  }
}
```

Specs that apply to **all** variants should omit the Device condition entirely.
Do not add `"Device": ["all"]` or list every variant — absence means universal.

When the datasheet writes a shorthand like "Si8230/1/2/7", expand it to the
full part numbers in the discrete list: `["Si8230", "Si8231", "Si8232", "Si8237"]`.

#### Table-header (default) conditions

Most datasheet sections list **default conditions outside the table** in a
preamble line, for example:

> _T<sub>A</sub> = 25°C, V<sub>CC</sub> = 5 V, unless otherwise noted._

The exact parameters vary by product type (voltage, temperature, load,
frequency, humidity, etc.) but the pattern is the same across all domains.
Parse them and attach them to each spec as conditions, following these rules:

1. **Apply to all rows** — every spec in the section inherits the table-header
   conditions unless the row's own TEST CONDITIONS column explicitly overrides
   a value.
2. **Row overrides header** — if a row specifies `RL = 4 Ω`, drop the
   `RL = 8 Ω` header condition for that spec and use the row value instead.
3. **Merge, don't duplicate** — if the same condition name appears in both the
   header and the row, keep only the row value.
4. **Qualitative notes** — phrases like "ferrite beads used" or "unless otherwise
   noted" become a `STRING` condition (e.g. `"Output filter": "ferrite beads"`)
   or go into `properties.notes` if they aren't a measurable quantity.

Example: A table header says `TA = 25°C, VCC = 5 V, RL = 10 kΩ`. A row in
that table has TEST CONDITIONS "VCC = 3.3 V, CL = 50 pF". The merged
conditions for that spec should be:

- `TA = 25°C` (from header — not overridden)
- `VCC = 3.3 V` (row overrides `VCC = 5 V` from header)
- `RL = 10 kΩ` (from header — not overridden)
- `CL = 50 pF` (from row — new condition)

#### Per-row condition examples

Numeric condition (measurable quantity with a unit):

```json
{
  "name": "VCC",
  "value": { "conditionType": "NUMERIC", "discrete": [5], "unit": "V" }
}
```

String condition (mode, configuration, or qualitative setting):

```json
{
  "name": "Mode",
  "value": { "conditionType": "STRING", "discrete": ["Normal"] }
}
```

### Keywords and properties

- Set `keywords` to `["datasheet", "<part-number-lowercase>"]` by default.
- Set `properties.source` to the input filename.
- Set `properties.notes` to any footnotes or clarifications from the datasheet.
- Set `properties.manufacturer` on the product, not on each spec.

## Step 5 — Build and import the JSON payload

Write the import payload to `build/ai/<partnum>-specs.json`:

```python
import json

specs = []
# ... build spec dicts ...
with open('build/ai/<partnum>-specs.json', 'w', encoding='utf-8') as f:
    json.dump({'specs': specs}, f, indent=2)
    f.write('\n')
```

Every spec must have at least: `productId`, `specId`, `type`.

### Choosing `type`: PARAMETRIC vs FUNCTIONAL

Use **PARAMETRIC** when the spec has numeric limits (min/typ/max) that a test
system can measure and automatically compare against bounds. Use **FUNCTIONAL**
when the spec describes a pass/fail behavior, capability, classification, or
qualitative characteristic that isn't a single numeric range.

**Decision rule:** If you can express the value as a number with a unit and
compare a measured result against min/typ/max bounds → PARAMETRIC. If the
pass/fail determination requires logic, enumeration, or human judgment →
FUNCTIONAL.

| Indicator                                      | Type       |
| ---------------------------------------------- | ---------- |
| Row has numeric Min/Typ/Max columns filled     | PARAMETRIC |
| Value with a measurable unit (V, A, Ω, ns, °C) | PARAMETRIC |
| ESD classification/rating (e.g. HBM ±2000 V)   | FUNCTIONAL |
| Regulatory compliance (UL, CSA, VDE)           | FUNCTIONAL |
| Insulation/safety rating or certification      | FUNCTIONAL |
| Truth table, pin behavior, logic description   | FUNCTIONAL |
| Package type, pin count, form factor           | FUNCTIONAL |
| Feature presence (e.g. "shutdown mode")        | FUNCTIONAL |

Most specs from Electrical Characteristics and Absolute Maximum Ratings tables
are PARAMETRIC. Specs from Regulatory, Insulation, Safety, and ESD Rating
tables are typically FUNCTIONAL.

Validate before import:

- No duplicate specIds.
- All numeric limit values are actual numbers (not strings).
- All condition values match their `conditionType`.
- The `productId` matches the product created in Step 2.
- Every PARAMETRIC spec has at least one limit bound (min, max, or typical).
  Specs with no limits cannot drive automated pass/fail — flag them to the user.
- Traceability: `properties.source` should reference the datasheet filename.
  For detailed traceability, include the section name or page number in
  `properties.notes` (e.g. "Table 3, p.12") so specs can be audited back to
  their source.

Import with:

```bash
slcli spec import --file build/ai/<partnum>-specs.json
```

Use `slcli spec create ...` only for one-off interactive entry.

## Step 6 — Upload source file and attach to product

Upload the original datasheet (PDF, CSV, etc.) to SystemLink and link it to
the product so users can trace specs back to the source document.

### Check for existing file

Before uploading, check whether the product already has a file with the same
name to avoid duplicates. Retrieve the product's current `fileIds`, then query
each file's metadata:

```bash
# Get product details including fileIds
slcli testmonitor product list --part-number "<PART>" --format json

# For each fileId, check the file name
slcli file get <FILE_ID> --format json
```

If a file with the same name already exists on the product, **skip the upload**
and tell the user. If a file with a different name exists (e.g. an older
revision), ask the user whether to keep both or replace the old one.

### Upload and attach

> **Use the workspace ID** (UUID), not the workspace name, in the `-w` flag.
> The file-upload endpoint rejects workspace names — resolve IDs first with
> `slcli workspace list -f json`.

> **Always include the file extension** (e.g. `.pdf`, `.csv`) in the `-n` name.
> SystemLink derives the file type from the Name property. If the name contains
> a `.` but no proper extension (e.g. `"Rev 2.15"`), the service will
> misidentify the file type.

```bash
# Upload the file (use workspace ID, not name)
slcli file upload "<LOCAL_PATH>" \
  -w "<WORKSPACE_ID>" \
  -n "<PART_NUMBER> Datasheet (<DOC_ID>).pdf"
```

Capture the file ID from the upload output, then attach it to the product
using the update-products API:

```python
from slcli.utils import make_api_request, get_base_url

resp = make_api_request(
    "POST",
    f"{get_base_url()}/nitestmonitor/v2/update-products",
    payload={
        "products": [{"id": "<PRODUCT_ID>", "fileIds": ["<FILE_ID>"]}],
        "replace": False,
    },
)
```

This preserves any existing `fileIds` on the product while adding the new one.

## Step 7 — Verify

```bash
slcli spec list --product <PART_NUMBER_OR_NAME> --take 100
```

The `--product` option accepts a product name, part number, or ID.

## Reference payload shape

Use `docs/examples/specifications/import-specs.json` as the canonical
create-compatible payload template.
