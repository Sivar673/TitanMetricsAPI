"""AI Physique Coach — vision evaluation against Men's Physique judging
standards.

Separation of concerns: the router owns HTTP (auth, upload validation,
status codes); this module owns everything model-related (prompt, image
encoding, the Anthropic call, schema enforcement).
"""

import base64
from functools import lru_cache
from typing import List, Tuple

import anthropic

from app.config import settings
from app.schemas import PhysiqueEvaluation

POSES = ("front", "side", "back")

# Anthropic API limit for base64 image sources.
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

SYSTEM_PROMPT = """\
You are an experienced Men's Physique judge on an IFBB/NPC-style panel, \
acting as an automated coach for competitors who train without a human coach. \
You will receive three photos of the same athlete — front, side, and back — \
and must evaluate the physique strictly against Men's Physique divisional \
criteria. Board shorts are the expected attire; legs are not judged in this \
division.

Evaluate only these four criteria:

1. STRUCTURE (primary emphasis). The V-taper is the deciding factor in this \
division: shoulder-to-waist ratio, lat width framing a tight waist, and how \
the silhouette reads from the front and back. A small waist with wide, \
capped shoulders outranks raw mass every time.

2. MUSCULARITY. Look for broad shoulders with round, full deltoid caps, \
developed arms, a full chest, and tapered lats. Men's Physique penalizes \
excessive size: if the physique reads as a Classic/Open bodybuilding look — \
blocky, overly thick through the mid-section, or mass that compromises \
lines — score it down and say so.

3. CONDITIONING. Look for clearly visible abdominal separation, delt \
separation, and overall tightness. This division rewards a beach-body look, \
not contest shreds: explicitly penalize a physique that appears excessively \
dry, striated, grainy, or shredded, exactly as a judging panel would.

4. SYMMETRY. Left-right upper-body balance, front-to-back balance (chest \
vs. back development), and whether any single body part visually dominates \
or lags the package.

Ground rules:
- Judge only what is visible in the photos. Do not guess at bodyweight, \
body-fat percentage, or drug use, and do not comment on anything outside \
the four criteria.
- Be direct and specific, like round feedback from a judge who wants the \
athlete to place higher next time. Reference what you can see ("rear delts \
disappear in the back pose"), never generic filler ("keep up the good work").
- Every weakness must map to at least one concrete training adjustment with \
an exercise and a volume or frequency prescription where sensible.
- Scoring guide: 9-10 pro-level package, 7-8 regional contender, 5-6 solid \
base with clear gaps, 3-4 early development, 1-2 not yet contest-relevant.
- If the images are not a valid submission (not the same person, missing or \
wrong poses, obstructed, not a physique photo at all), set \
is_valid_submission to false, explain in validity_notes, set overall_score \
to 1, leave strengths empty, and use weaknesses/training_adjustments only \
if something can still be said. Never invent feedback for what you cannot \
see.\
"""


class PhysiqueAIError(Exception):
    """Service-level failure with an HTTP-friendly status suggestion."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise PhysiqueAIError(
            "AI Physique Coach is not configured (TITAN_ANTHROPIC_API_KEY is unset).",
            status_code=503,
        )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def evaluate_physique(images: List[Tuple[str, bytes, str]]) -> PhysiqueEvaluation:
    """Evaluate three pose images.

    `images` is [(pose_name, raw_bytes, media_type), ...] in front/side/back
    order, already validated for type and size by the router.
    """
    content = []
    for pose, raw, media_type in images:
        content.append({"type": "text", "text": f"{pose.upper()} POSE:"})
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.standard_b64encode(raw).decode("utf-8"),
                },
            }
        )
    content.append(
        {
            "type": "text",
            "text": (
                "Evaluate this Men's Physique package per your judging "
                "criteria and return the structured evaluation."
            ),
        }
    )

    try:
        response = _client().messages.parse(
            model=settings.anthropic_model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            output_format=PhysiqueEvaluation,
        )
    except anthropic.AuthenticationError:
        raise PhysiqueAIError(
            "AI provider rejected the configured API key.", status_code=503
        )
    except anthropic.RateLimitError:
        raise PhysiqueAIError(
            "AI provider is rate-limiting us — try again in a minute.",
            status_code=429,
        )
    except anthropic.APIStatusError as exc:
        raise PhysiqueAIError(
            f"AI provider error ({exc.status_code}).", status_code=502
        )
    except anthropic.APIConnectionError:
        raise PhysiqueAIError(
            "Could not reach the AI provider.", status_code=502
        )

    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise PhysiqueAIError(
            "The AI declined to evaluate these images.", status_code=422
        )

    return response.parsed_output
