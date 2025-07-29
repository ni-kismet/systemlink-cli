# Dynamic Form Fields Editor

This directory contains a standalone web editor for SystemLink Dynamic Form Fields configurations.

## Files

- `index.html` - The main editor interface
- `README.md` - This file

## Usage

1. Start the editor server:
   ```
   slcli dff edit --output-dir dff-editor --port 8080
   ```

2. Open your browser to: http://localhost:8080

3. Edit your configuration in the JSON editor

4. Use the tools to validate, format, and download your configuration

## Future Enhancements

This editor is currently a basic JSON editor. Future versions will include:

- Visual form builder
- Field type validation
- Real-time preview
- Schema validation
- Direct save to file
- Integration with SystemLink API

## Configuration Structure

Dynamic Form Fields configurations consist of:

- **Configurations**: Top-level configuration objects that define how forms are structured
- **Groups**: Logical groupings of fields within a configuration
- **Fields**: Individual form fields with types, validation rules, and properties

See the example configuration in the editor for a sample structure.
