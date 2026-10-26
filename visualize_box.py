
import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def main():
    parser = argparse.ArgumentParser(
        description="Draw a bounding box on a screenshot."
    )
    parser.add_argument("image", help="Path to the input screenshot")
    parser.add_argument("--left", type=int, required=True)
    parser.add_argument("--top", type=int, required=True)
    parser.add_argument("--right", type=int, required=True)
    parser.add_argument("--bottom", type=int, required=True)
    parser.add_argument(
        "--output",
        help="Output image path (default: <image>_annotated.png)",
    )

    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.is_file():
        parser.error(f"Image not found: {image_path}")

    output_path = (
        Path(args.output)
        if args.output
        else image_path.with_name(
            f"{image_path.stem}_annotated.png"
        )
    )

    with Image.open(image_path) as original:
        image = original.convert("RGB")

    width, height = image.size

    if not (
        0 <= args.left < args.right <= width
        and 0 <= args.top < args.bottom <= height
    ):
        parser.error(
            f"Bounding box must be within image bounds "
            f"(width={width}, height={height})"
        )

    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (args.left, args.top, args.right, args.bottom),
        outline="red",
        width=4,
    )

    image.save(output_path)
    print(f"Saved annotated image: {output_path}")


if __name__ == "__main__":
    main()
