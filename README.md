# Memo Filler Service

Fairbridge Deal Memo Generator - FastAPI service that fills Word templates using Jinja2/docxtpl engine.

## Overview

This service fills Word document templates with complex data structures including:
- Nested data paths (`sections.property.description_narrative`)
- Loops (`{% for row in rows %}...{% endfor %}`)
- Conditionals (`{% if enabled %}...{% endif %}`)
- Inline images with auto-scaling

## Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export S3_ACCESS_KEY="your-access-key"
export S3_SECRET_KEY="your-secret-key"

# Run server
python main.py
# or
uvicorn main:app --reload --port 8000
```

### Docker Deployment (Coolify)

```bash
# Build
docker build -t memo-filler .

# Run
docker run -p 8000:8000 \
  -e S3_ACCESS_KEY="your-key" \
  -e S3_SECRET_KEY="your-secret" \
  memo-filler
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `S3_ACCESS_KEY` | DigitalOcean Spaces access key | Yes |
| `S3_SECRET_KEY` | DigitalOcean Spaces secret key | Yes |

## API Endpoints

### `GET /health`

Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "engine": "docxtpl"
}
```

### `POST /fill`

Fill template and return as download.

**Request Body:**
```json
{
  "data": {
    "cover": {
      "memo_title": "INVESTMENT MEMORANDUM",
      "property_name": "Example Property"
    },
    "sections": {
      "transaction_overview": {
        "deal_facts": [
          {"label": "Property Address", "value": "123 Main St"},
          {"label": "Loan Amount", "value": "$10,000,000"}
        ]
      }
    }
  },
  "images": {
    "IMAGE_AERIAL_MAP": "base64-encoded-image-data..."
  },
  "template_key": "_Templates/Fairbridge_Memo_Template_v1_0.docx",
  "output_filename": "Deal_Memo.docx"
}
```

**Response:** Word document download

### `POST /fill-and-upload`

Fill template and upload to S3.

**Request Body:**
```json
{
  "data": { /* same as /fill */ },
  "images": { /* same as /fill */ },
  "template_key": "_Templates/Fairbridge_Memo_Template_v1_0.docx",
  "output_key": "deals/output/Deal_Memo_2026-01-29.docx"
}
```

**Response:**
```json
{
  "success": true,
  "output_key": "deals/output/Deal_Memo_2026-01-29.docx",
  "output_url": "https://nyc3.digitaloceanspaces.com/fam.workspace/deals/output/Deal_Memo_2026-01-29.docx",
  "original_key": "deals/output/Deal_Memo_2026-01-29.docx"
}
```

### `GET /template-info`

Get template variables for debugging.

**Query Parameters:**
- `template_key` (optional): S3 key to template file

**Response:**
```json
{
  "template_key": "_Templates/Fairbridge_Memo_Template_v1_0.docx",
  "variables": ["cover.memo_title", "sections.executive_summary.narrative", ...],
  "variable_count": 150
}
```

## Template Syntax (Jinja2/docxtpl)

### Simple Values
```
{{ cover.memo_title }}
{{ sections.property.description_narrative }}
```

### Loops (Regular)
```
{% for highlight in sections.executive_summary.key_highlights %}
• {{ highlight }}
{% endfor %}
```

### Loops (Table Rows)
```
{%tr for fact in sections.transaction_overview.deal_facts %}
  {{ fact.label }}  |  {{ fact.value }}
{%tr endfor %}
```

### Conditionals
```
{% if sections.market.enabled %}
6. MARKET OVERVIEW
{{ sections.market.narrative }}
{% endif %}
```

### Images
```
{{ IMAGE_AERIAL_MAP }}
```

## Image Handling

Images are passed as base64-encoded strings in the `images` object. The service:
1. Decodes the base64 data
2. Calculates optimal dimensions (max 6.5" wide × 8.0" tall)
3. Maintains aspect ratio
4. Inserts as InlineImage at placeholder location

**Supported Image Keys:**
- `IMAGE_SOURCES_USES`
- `IMAGE_CAPITAL_STACK_CLOSING`
- `IMAGE_CAPITAL_STACK_MATURITY`
- `IMAGE_AERIAL_MAP`
- `IMAGE_LOCATION_MAP`
- `IMAGE_REGIONAL_MAP`
- `IMAGE_SITE_PLAN`
- `IMAGE_STREET_VIEW`
- `IMAGE_FORECLOSURE_DEFAULT`
- `IMAGE_FORECLOSURE_NOTE`

## S3 Configuration

- **Endpoint:** `https://nyc3.digitaloceanspaces.com`
- **Bucket:** `fam.workspace`
- **Region:** `nyc3`

Templates are stored in `_Templates/` prefix.

## Differences from IDS Template Filler

| Feature | IDS Template Filler | Memo Filler |
|---------|---------------------|-------------|
| Template Engine | Custom regex replacement | docxtpl (Jinja2) |
| Loops | Custom SPONSOR_SECTION handler | Native `{% for %}` |
| Conditionals | None | Native `{% if %}` |
| Nested Data | Flat placeholders only | Full dot notation |
| Use Case | Simple IDS documents | Complex deal memos |

## Dependencies

- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `docxtpl` - Word template engine (Jinja2-based)
- `python-docx` - Word document manipulation
- `boto3` - AWS S3 / DigitalOcean Spaces
- `Pillow` - Image processing

## Version History

- **1.0.0** - Initial release with docxtpl support
