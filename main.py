"""
Memo Filler Service - Fairbridge Deal Memo Generator

FastAPI service that fills Word templates using Jinja2/docxtpl engine.
Designed for complex templates with loops, conditionals, and nested data.

Version: 1.0.0
"""

import os
import re
import base64
from io import BytesIO
from typing import Dict, Any, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import boto3
from botocore.config import Config
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Inches, Mm
from PIL import Image

app = FastAPI(title="Memo Filler Service", version="1.0.0")

# =============================================================================
# S3 Configuration (same as IDS Template Filler)
# =============================================================================
S3_ENDPOINT = "https://nyc3.digitaloceanspaces.com"
S3_BUCKET = "fam.workspace"
S3_REGION = "nyc3"

s3_client = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
    region_name=S3_REGION,
    config=Config(s3={'addressing_style': 'path'})
)

# =============================================================================
# Image dimension constraints
# =============================================================================
MAX_WIDTH_INCHES = 6.5   # Content area of letter page with 1" margins
MAX_HEIGHT_INCHES = 8.0  # Leave room for captions/spacing

# Default widths for known image types
IMAGE_WIDTHS = {
    "IMAGE_SOURCES_USES": 6.5,
    "IMAGE_CAPITAL_STACK_CLOSING": 6.5,
    "IMAGE_CAPITAL_STACK_MATURITY": 6.5,
    "IMAGE_LOAN_TO_COST": 6.0,
    "IMAGE_LTV_LTC": 6.0,
    "IMAGE_AERIAL_MAP": 4.5,
    "IMAGE_LOCATION_MAP": 4.5,
    "IMAGE_REGIONAL_MAP": 4.5,
    "IMAGE_SITE_PLAN": 5.5,
    "IMAGE_STREET_VIEW": 5.5,
    "IMAGE_FORECLOSURE_DEFAULT": 6.5,
    "IMAGE_FORECLOSURE_NOTE": 6.5,
}


# =============================================================================
# Request/Response Models
# =============================================================================
class FillRequest(BaseModel):
    """Request model for template filling."""
    data: Dict[str, Any]  # The schema data object
    images: Dict[str, str] = {}  # Base64-encoded images
    template_key: str = "_Templates/Fairbridge_Memo_Template_v1_0.docx"
    output_filename: str = "Deal_Memo_Generated.docx"


class FillAndUploadRequest(BaseModel):
    """Request model for fill + S3 upload."""
    data: Dict[str, Any]
    images: Dict[str, str] = {}
    template_key: str = "_Templates/Fairbridge_Memo_Template_v1_0.docx"
    output_key: str


class HealthResponse(BaseModel):
    status: str
    version: str
    engine: str


# =============================================================================
# Helper Functions
# =============================================================================
def calculate_image_dimensions(image_bytes: bytes, preferred_width: float) -> tuple[float, float]:
    """
    Calculate optimal image dimensions that fit within page constraints.
    Maintains aspect ratio while fitting within max width/height.
    """
    try:
        image = Image.open(BytesIO(image_bytes))
        original_width, original_height = image.size
        aspect_ratio = original_height / original_width

        # Start with preferred width, constrain to max
        width_inches = min(preferred_width, MAX_WIDTH_INCHES)
        height_inches = width_inches * aspect_ratio

        # If too tall, scale down to fit max height
        if height_inches > MAX_HEIGHT_INCHES:
            height_inches = MAX_HEIGHT_INCHES
            width_inches = height_inches / aspect_ratio

            if width_inches > MAX_WIDTH_INCHES:
                width_inches = MAX_WIDTH_INCHES
                height_inches = width_inches * aspect_ratio

        return width_inches, height_inches

    except Exception as e:
        print(f"Warning: Could not process image dimensions: {e}")
        return min(preferred_width, MAX_WIDTH_INCHES), min(4.0, MAX_HEIGHT_INCHES)


def download_template(template_key: str) -> bytes:
    """Download template from S3."""
    try:
        response = s3_client.get_object(Bucket=S3_BUCKET, Key=template_key)
        return response['Body'].read()
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Template not found: {template_key} - {str(e)}")


def get_unique_output_key(output_key: str) -> str:
    """
    If output_key exists in S3, return a unique version with _2, _3, etc.
    """
    try:
        s3_client.head_object(Bucket=S3_BUCKET, Key=output_key)
    except:
        return output_key

    base, ext = os.path.splitext(output_key)

    match = re.match(r'(.+)_(\d+)$', base)
    if match:
        base = match.group(1)
        start = int(match.group(2)) + 1
    else:
        start = 2

    for i in range(start, 1000):
        new_key = f"{base}_{i}{ext}"
        try:
            s3_client.head_object(Bucket=S3_BUCKET, Key=new_key)
        except:
            return new_key

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f"{base}_{timestamp}{ext}"


def upload_to_s3(content: bytes, key: str) -> str:
    """Upload content to S3 and return URL."""
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=content,
            ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        return f"{S3_ENDPOINT}/{S3_BUCKET}/{key}"
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload to S3: {str(e)}")


def prepare_images_for_template(
    doc: DocxTemplate,
    images: Dict[str, str]
) -> Dict[str, InlineImage]:
    """
    Convert base64 images to docxtpl InlineImage objects.
    """
    inline_images = {}

    for key, base64_data in images.items():
        try:
            image_bytes = base64.b64decode(base64_data)
            preferred_width = IMAGE_WIDTHS.get(key, 5.0)
            width_inches, height_inches = calculate_image_dimensions(image_bytes, preferred_width)

            image_stream = BytesIO(image_bytes)
            inline_images[key] = InlineImage(
                doc,
                image_stream,
                width=Inches(width_inches),
                height=Inches(height_inches)
            )
            print(f"Prepared image {key}: {width_inches:.2f}\" x {height_inches:.2f}\"")

        except Exception as e:
            print(f"Warning: Failed to prepare image {key}: {e}")
            continue

    return inline_images


def fill_template(template_bytes: bytes, data: Dict[str, Any], images: Dict[str, str]) -> bytes:
    """
    Fill the template using docxtpl engine.

    Args:
        template_bytes: The Word template file content
        data: The schema data to fill into the template
        images: Dict of image_key -> base64 encoded image data

    Returns:
        Filled document as bytes
    """
    # Load template
    template_stream = BytesIO(template_bytes)
    doc = DocxTemplate(template_stream)

    # Prepare images as InlineImage objects
    inline_images = prepare_images_for_template(doc, images)

    # Merge data and images into context
    context = {**data, **inline_images}

    # Render template
    try:
        doc.render(context)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Template rendering failed: {str(e)}")

    # Save to bytes
    output = BytesIO()
    doc.save(output)
    output.seek(0)
    return output.getvalue()


# =============================================================================
# API Endpoints
# =============================================================================
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": "1.0.0",
        "engine": "docxtpl"
    }


@app.post("/fill")
async def fill_template_endpoint(request: FillRequest):
    """
    Fill template and return as download.

    Request body:
    - data: The schema data object (nested dict matching template placeholders)
    - images: Optional dict of image_key -> base64 encoded image
    - template_key: S3 key for template file
    - output_filename: Name for downloaded file
    """
    # Download template from S3
    template_bytes = download_template(request.template_key)

    # Fill template
    filled_bytes = fill_template(template_bytes, request.data, request.images)

    # Return as download
    return StreamingResponse(
        BytesIO(filled_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={request.output_filename}"}
    )


@app.post("/fill-and-upload")
async def fill_and_upload_endpoint(request: FillAndUploadRequest):
    """
    Fill template and upload to S3.

    Request body:
    - data: The schema data object
    - images: Optional dict of image_key -> base64 encoded image
    - template_key: S3 key for template file
    - output_key: S3 key for output file

    Returns:
    - success: bool
    - output_key: Actual S3 key used (may differ if original existed)
    - output_url: Full URL to the uploaded file
    """
    # Download template from S3
    template_bytes = download_template(request.template_key)

    # Fill template
    filled_bytes = fill_template(template_bytes, request.data, request.images)

    # Get unique output key if needed
    output_key = get_unique_output_key(request.output_key)

    # Upload to S3
    output_url = upload_to_s3(filled_bytes, output_key)

    return {
        "success": True,
        "output_key": output_key,
        "output_url": output_url,
        "original_key": request.output_key
    }


@app.get("/template-info")
async def get_template_info(template_key: str = "_Templates/Fairbridge_Memo_Template_v1_0.docx"):
    """
    Get information about a template (useful for debugging).
    Returns the template's undeclared variables.
    """
    try:
        template_bytes = download_template(template_key)
        template_stream = BytesIO(template_bytes)
        doc = DocxTemplate(template_stream)

        # Get variables used in template
        variables = doc.get_undeclared_template_variables()

        return {
            "template_key": template_key,
            "variables": list(variables),
            "variable_count": len(variables)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to analyze template: {str(e)}")


# =============================================================================
# Main
# =============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
