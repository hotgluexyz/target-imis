# Configuration Guide for target-imis

This directory contains a template configuration file for the `target-imis` Singer target. Copy `config.json` to your desired location and update it with your IMIS credentials and settings.

## Configuration Options

### Required Settings

#### `username` (string, required)
- **Description**: Your IMIS username for authentication
- **Example**: `"john.doe@example.com"`

#### `password` (string, required)
- **Description**: Your IMIS password for authentication
- **Example**: `"your_secure_password"`

#### `site_url` (string, required)
- **Description**: The base URL of your IMIS instance (without trailing slash)
- **Example**: `"https://your-imis-instance.com"`
- **Note**: The target will automatically append `/Token` for authentication and `/api/` for API endpoints.

### Optional Settings

#### `lookup_fields` (object, optional)
- **Description**: Defines which fields to use when looking up existing records before upserting. This helps prevent duplicate records.
- **Format**: An object where keys are stream names and values are either a string (single field) or an array of strings (multiple fields)
- **Supported Streams**:
  - `"Contact"`: Lookup fields for the Contacts stream
- **Supported Field Names**:
  - `"email"`: Look up by email address
  - `"first_name"`: Look up by first name
  - `"last_name"`: Look up by last name
  - `"id"`: Look up by ID
- **Examples**:
  ```json
  {
    "Contact": "email"
  }
  ```
  ```json
  {
    "Contact": ["email", "first_name", "last_name"]
  }
  ```
- **Default**: If not specified, the Contacts stream defaults to using `"email"` for lookups.

#### `lookup_method` (string, optional)
- **Description**: Determines how multiple lookup fields are processed when `lookup_fields` contains an array.
- **Valid Values**:
  - `"all"`: All specified fields must match (AND logic). This is the default.
  - `"sequential"`: Try each field in order until a match is found (OR logic with priority).
- **Example**: `"all"`
- **Default**: `"all"`
- **Note**: This setting only applies when `lookup_fields` contains an array of fields. For single field lookups, this setting is ignored.

#### `only_upsert_empty_fields` (boolean, optional)
- **Description**: When enabled, the target will only update fields in existing records if those fields are currently empty/null. This prevents overwriting existing data.
- **Use Cases**:
  - Preserve existing data when syncing partial updates
  - Prevent accidental data loss from incomplete source records
- **Example**: `false`
- **Default**: `false`
- **Note**: When `true`, fields that already have values in IMIS will not be overwritten, even if the source record contains new values for those fields.

## Example Configuration

### Minimal Configuration (Required Fields Only)
```json
{
  "username": "your_imis_username",
  "password": "your_imis_password",
  "site_url": "https://your-imis-instance.com"
}
```

### Full Configuration (All Options)
```json
{
  "username": "your_imis_username",
  "password": "your_imis_password",
  "site_url": "https://your-imis-instance.com",
  "lookup_fields": {
    "Contact": ["email", "first_name", "last_name"]
  },
  "lookup_method": "sequential",
  "only_upsert_empty_fields": true
}
```

## Using Environment Variables

Instead of storing credentials in the config file, you can use environment variables. The target supports loading configuration from environment variables when using `--config=ENV`.

Set the following environment variables:
- `TARGET_IMIS_USERNAME`
- `TARGET_IMIS_PASSWORD`
- `TARGET_IMIS_SITE_URL`
- `TARGET_IMIS_LOOKUP_FIELDS` (JSON string)
- `TARGET_IMIS_LOOKUP_METHOD`
- `TARGET_IMIS_ONLY_UPSERT_EMPTY_FIELDS`

Or create a `.env` file in your working directory:
```
TARGET_IMIS_USERNAME=your_imis_username
TARGET_IMIS_PASSWORD=your_imis_password
TARGET_IMIS_SITE_URL=https://your-imis-instance.com
```
