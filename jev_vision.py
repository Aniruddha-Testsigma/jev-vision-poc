
import base64
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TYPESAFE_API_KEY")
ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.14.0"

PRESENCE_THRESHOLD = 0.60
BOX_CONFIDENCE_THRESHOLD = 0.60


def detect_element(
    screenshot_path: str,
    target_description: str,
) -> dict:
    """
    Check whether a UI element is visible in a screenshot
    and, when sufficiently likely to be present, return
    its approximate pixel bounding box.
    """
    if not API_KEY:
        raise RuntimeError("Set TYPESAFE_API_KEY in your .env file")

    image_path = Path(screenshot_path)

    if not image_path.is_file():
        raise FileNotFoundError(
            f"Screenshot not found: {image_path}"
        )

    image_format = image_path.suffix.lower().lstrip(".")

    if image_format not in {"png", "jpg", "jpeg"}:
        raise ValueError("Screenshot must be PNG or JPEG")

    image_bytes = image_path.read_bytes()
    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    payload = {
        "model": MODEL,
        "state": {
            "screenshot": "target_image",
            "target": target_description,
        },
        "assets": {
            "target_image": {
                "type": "image",
                "data_base64": image_b64,
                "format": image_format,
            }
        },
        "questions": {
            "presence": {
                "type": "noul",
                "instructions": (
                "Determine whether a visible Login button exists "
                "anywhere in the screenshot. Look for buttons labeled "
                "'Login', 'Log in', or 'Sign in'. Consider common button "
                "styles and capitalization. Do not assume the button "
                "exists if it cannot be seen."
            ),
            },
            "location": {
                "type": "box",
                "instructions": (
                    f"Locate this UI element in the screenshot: "
                    f"{target_description}. Return the tight "
                    "bounding box around the target."
                ),
            },
        },
    }

    response = requests.post(
        ENDPOINT,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "TypeSafe-Danger-Zone-Images": "true",
        },
        json=payload,
        timeout=45,
    )

    if response.status_code in (429, 529):
        raise RuntimeError(
            f"Jev temporarily unavailable: HTTP "
            f"{response.status_code}. Retry with backoff."
        )

    response.raise_for_status()
    result = response.json()

    answers = result.get("answers", {})
    presence_answer = answers.get("presence", {})
    location_answer = answers.get("location", {})

    if "noul" not in presence_answer:
        raise ValueError(
            f"Unexpected presence response: {json.dumps(result)}"
        )

    presence_probability = float(presence_answer["noul"])

    output = {
        "target": target_description,
        "present_probability": presence_probability,
        "present": presence_probability >= PRESENCE_THRESHOLD,
        "box": None,
        "pixel_box": None,
        "box_confidence": None,
        "usage": result.get("usage"),
        "model": result.get("model"),
    }

    # Never trust the box when the element is unlikely to be present.
    if not output["present"]:
        return output

    box = location_answer.get("box")

    if not isinstance(box, dict):
        output["localization_error"] = (
            "The API did not return a valid bounding box."
        )
        return output

    confidence = location_answer.get("confidence")
    output["box"] = box
    output["box_confidence"] = confidence

    if confidence is None or float(confidence) < BOX_CONFIDENCE_THRESHOLD:
        output["localization_error"] = (
            "Bounding-box confidence is too low."
        )
        return output

    from PIL import Image

    with Image.open(image_path) as image:
        width, height = image.size

    # Jev's coordinates are normalized to the image dimensions.
    left = round(float(box["left"]) * width)
    top = round(float(box["top"]) * height)
    right = round(float(box["right"]) * width)
    bottom = round(float(box["bottom"]) * height)

    # Reject malformed or out-of-bounds boxes.
    if not (
        0 <= left < right <= width
        and 0 <= top < bottom <= height
    ):
        output["localization_error"] = (
            "Bounding box is outside the valid image bounds."
        )
        return output

    output["pixel_box"] = {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": right - left,
        "height": bottom - top,
    }

    return output


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            'Usage: python jev_vision.py '
            '"screenshot.png" "Submit button"'
        )
        sys.exit(2)

    try:
        detection = detect_element(
            screenshot_path=sys.argv[1],
            target_description=" ".join(sys.argv[2:]),
        )
        print(json.dumps(detection, indent=2))
    except (requests.RequestException, ValueError, RuntimeError,
            FileNotFoundError) as error:
        print(f"Detection failed: {error}", file=sys.stderr)
        sys.exit(1)
