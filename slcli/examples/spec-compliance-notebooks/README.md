# Specification Compliance Analysis Notebooks

Complete set of Jupyter notebooks for performing specification compliance analysis on test data within SystemLink.

## Notebooks Included

### 1. Spec Compliance Calculation

- **Purpose**: Calculate compliance metrics (min, max, mean, median) for parametric specifications
- **Inputs**: Specification data and measurement results
- **Outputs**: Compliance report (uploaded to product)
- **Interface**: File Analysis

### 2. Spec Analysis & Compliance Calculation

- **Purpose**: Combined workflow for specification analysis and compliance calculation
- **Inputs**: Spec files and measurement data
- **Outputs**: Detailed compliance analysis
- **Interface**: File Analysis

### 3. Specfile Extraction and Ingestion

- **Purpose**: Extract specification data and ingest into SystemLink
- **Inputs**: Excel specification files (see template below)
- **Outputs**: Structured specification data ingested into SystemLink
- **Interface**: File Analysis

## Template File

A sample specification template file (`spec_template.xlsx`) is included in this example directory. This file demonstrates the required Excel format for the **Specfile Extraction and Ingestion** notebook.

### Template Structure

The template includes two sheets:

1. **SpecTemplate** (Documentation)

   - Instructions for the spec file format
   - Column type definitions
   - Data structure requirements
   - Condition format examples

2. **Example Part** (Sample Data)
   - Complete example with 5 sample specifications
   - Demonstrates all column types (STD, COND, INF)
   - Shows proper formatting and data types

### Excel Format Requirements

**Column Types:**

- **STD (Standard)**: Core specification fields (Spec ID, Name, Min, Max, etc.)
- **COND (Condition)**: Conditional specifications (temperature ranges, voltage conditions, etc.)
- **INF (Information)**: Custom properties and metadata

**File Structure:**

```
Row 1: Column type designation (STD, COND, or INF)
Row 2: Category (column B) and Spec Type (column C) - e.g., "parametric" or "functional"
Row 3: Column headers (mapped to spec fields)
Row 4+: Specification data
```

**Standard Columns (STD):**

- Spec ID (required, unique identifier)
- Name (specification name)
- Min, Typical, Max (limits for parametric specs)
- Unit (measurement unit)
- Category, Block, Symbol (organization fields)

**Condition Format Examples:**

- Discrete values: `[1,2,3]` or `[A,B,C]`
- Numeric range: `[0..10]` (min to max)
- Range with discrete: `[1..5,2.5]` (range plus intermediate values)

## Usage

After installation, notebooks are available in your workspace with the File Analysis interface configured.

### Running via CLI

```bash
# List published notebooks
slcli notebook list -w <workspace-id>

# Execute a notebook
slcli notebook execute run -i <notebook-id> -w <workspace-id>
```

### Running via SystemLink Web Interface

1. Navigate to File Analysis in your workspace
2. Select a specification compliance notebook
3. Upload your specification file or measurement data
4. Run the notebook

## Requirements

- SystemLink Enterprise 2024.1 or later
- Python 3.9+ with required scientific packages
- Access to measurement data and specification definitions
- Excel files (.xlsx) for spec file ingestion

## Key Features

- **Condition Mapping**: Intelligent mapping between specification and measurement conditions
- **Unit Conversion**: Automatic unit conversion for compatible measurements
- **Compliance Calculation**: Min/Max/Mean/Median compliance across measurement sets
- **Report Generation**: Excel report generation with compliance results
- **Data Validation**: Comprehensive validation of input data formats
- **Flexible Schema**: Support for parametric and functional specifications

## Rules and Constraints

### Condition Mapping

- Spec and measurement conditions must have compatible units or both be unitless
- Unit conversion only supported for compatible base units
- Missing conditions handled gracefully

### Measurement Data

- Measurement data should be stored in base units
- Non-numeric or empty values are filtered out
- Unit compatibility checked before inclusion

### Compliance Calculation

- Only valid, unit-compatible measurements included
- Statistical functions (min, max, mean, median) calculated per specification
- Results formatted for Excel export

## Notes

- Each notebook includes detailed documentation about its operation
- Examples and usage patterns are embedded in each notebook
- Refer to SystemLink documentation for File Analysis interface details
