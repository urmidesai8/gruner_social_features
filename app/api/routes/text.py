from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    GenerateQuoteCardRequest,
    GenerateQuoteCardResponse,
)
from app.services.text import generate_quote_card_base64


router = APIRouter(prefix="/api", tags=["text"])


@router.post("/generate-quote-card", response_model=GenerateQuoteCardResponse)
async def generate_quote_card(req: GenerateQuoteCardRequest) -> GenerateQuoteCardResponse:
    prompt = (req.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Missing prompt.")
    try:
        quote_text, mime_type, image_base64 = await generate_quote_card_base64(prompt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return GenerateQuoteCardResponse(
        prompt=prompt,
        quote_text=quote_text,
        mime_type=mime_type,
        image_base64=image_base64,
    )

