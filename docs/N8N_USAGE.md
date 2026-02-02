# Using the Memo Filler service from n8n

The service exposes REST endpoints. Use n8n **HTTP Request** nodes to call them.

## 1. Run the service

Start the API (e.g. locally or on your server):

```bash
cd /path/to/memo_filler
uvicorn main:app --host 0.0.0.0 --port 8000
```

Base URL: `http://localhost:8000` (or your deployed URL).

---

## 2. Fill memo from deal JSON (recommended: `/fill-from-deal`)

Use this when you have **Layer 3 deal JSON** (one object per deal with `deal_id`, `cover`, `deal_facts`, `loan_terms`, `sponsor`, `property`, `narratives`, etc.). The service fills the template and **uploads the .docx to S3**.

### n8n HTTP Request node

- **Method:** `POST`
- **URL:** `http://localhost:8000/fill-from-deal` (or your base URL + `/fill-from-deal`)
- **Body Content Type:** `JSON`
- **Body:**

**Option A – Wrapped (good when you have one item from a previous node)**

```json
{
  "payload": [ {{ $json }} ],
  "output_key": "deals/{{ $json.deal_id }}/Investment_Memo.docx",
  "deal_index": 0,
  "template_key": "_Templates/FB_Deal_Memo_Template.docx",
  "images": {}
}
```

If the previous node already has the full deal object as `$json`, use an **Expression** for the body and build the object, e.g.:

- `payload`: `[ $json ]` (array with current item)
- `output_key`: `deals/{{ $json.deal_id }}/Investment_Memo.docx`
- `deal_index`: `0`
- `template_key`: `_Templates/FB_Deal_Memo_Template.docx` (optional; this is the default)
- `images`: `{}` (optional)

**Option B – Raw deal (body = deal object)**

- **Body:** the deal object directly (e.g. `{{ $json }}` if that’s the deal).
- Optional: query param `?output_key=deals/my-deal/Investment_Memo.docx` (otherwise default is `deals/{deal_id}/Investment_Memo.docx`).

**Option C – Array of deals (no wrapper)**

- **Body:** `[ deal1, deal2, ... ]`
- Optional: query param `?output_key=...` (otherwise first deal’s `deal_id` is used for the path).

### Response

```json
{
  "success": true,
  "output_key": "deals/broward-blvd/Investment_Memo.docx",
  "output_url": "https://nyc3.digitaloceanspaces.com/fam.workspace/deals/broward-blvd/Investment_Memo.docx",
  "deal_id": "broward-blvd",
  "deal_folder": "7001 and 7007-7181 W. Broward Blvd....",
  "sponsors_found": 2,
  "sponsor_names": ["Steve Hudson", "Charlie Ladd Jr."],
  "template_used": "_Templates/FB_Deal_Memo_Template.docx"
}
```

Use `output_url` in later nodes (e.g. to notify or link to the memo).

---

## 3. Other endpoints

| Endpoint | Method | Use case |
|----------|--------|----------|
| `/health` | GET | Health check (e.g. n8n “Check URL” or first node). |
| `/fill-from-layer2` | POST | Layer 2 extraction array → transform → fill → upload to S3. Body: `{ "layer2_data": [...], "output_key": "...", "template_key": "...", "images": {} }`. |
| `/fill` | POST | Pre-built schema + template from S3 → **download** .docx (no S3 upload). Body: `{ "data": { ... }, "template_key": "...", "output_filename": "memo.docx", "images": {} }`. |
| `/fill-and-upload` | POST | Same as `/fill` but uploads result to S3. Body: `{ "data": { ... }, "template_key": "...", "output_key": "path/to.docx", "images": {} }`. |
| `/transform-deal-to-schema` | POST | Debug: send deal JSON, get back the schema that would be used for the template (no fill, no S3). Body: single deal object or `[ deal ]`. |

---

## 4. Environment / S3

- **Template:** By default the service loads the template from S3 (`_Templates/FB_Deal_Memo_Template.docx`). Set `S3_ACCESS_KEY` and `S3_SECRET_KEY` (and bucket/endpoint as in code) where the app runs.
- **Output:** `/fill-from-deal` and `/fill-and-upload` write to that same S3 bucket; `output_key` is the object key (e.g. `deals/{deal_id}/Investment_Memo.docx`).

---

## 5. Example n8n flow (high level)

1. **Trigger or previous workflow** – provides deal JSON (e.g. from Layer 3 or DB).
2. **HTTP Request**
   - URL: `{{ $env.MEMO_FILLER_URL }}/fill-from-deal` (or fixed URL)
   - Method: POST
   - Body (JSON):  
     `{ "payload": [ {{ $json }} ], "output_key": "deals/{{ $json.deal_id }}/Investment_Memo.docx" }`
3. **Next node** – use `$json.output_url` (or handle error if `$json.success` is false).

For **Option B (raw deal)**:

- Body: `{{ $json }}`  
- Optionally add query parameter: `Output Key` = `deals/{{ $json.deal_id }}/Investment_Memo.docx` in the URL or as a query field if your n8n HTTP node supports it.
