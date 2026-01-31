# Memo template

**`FB_Deal_Memo_Template.docx`** is the Fairbridge deal memo Word template (Jinja2/docxtpl compatible).

- **Source:** `~/Downloads/FB Deal Memo_Template.docx` (canonical copy).
- **In repo:** This folder holds the template for version control and local reference.

The memo filler service **pulls the template from S3** (bucket `fam.workspace`), then **fills it with the Layer 3 input** and uploads the result. It does not read from this folder at runtime. To use this template in production:

1. Upload this file to S3 at the default key the service expects:  
   **`_Templates/FB_Deal_Memo_Template.docx`**
2. If you use a different key, pass `template_key` in the request (body or query) when calling `/fill-from-deal`.
