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
- **Inputs**: Specification files (various formats)
- **Outputs**: Structured specification data
- **Interface**: File Analysis

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
3. Run with your measurement data

## Requirements

- SystemLink Enterprise 2024.1 or later
- Python 3.9+ with required scientific packages
- Access to measurement data and specification definitions

## Key Features

- **Condition Mapping**: Intelligent mapping between specification and measurement conditions
- **Unit Conversion**: Automatic unit conversion for compatible measurements
- **Compliance Calculation**: Min/Max/Mean/Median compliance across measurement sets
- **Report Generation**: Excel report generation with compliance results
- **Data Validation**: Comprehensive validation of input data formats

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
