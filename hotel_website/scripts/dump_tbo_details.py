"""Dump raw TBO HotelDetails response to inspect image structure."""
import json
import sys

from db.tbo_client import tbo_request


def main(code: str) -> None:
    data = tbo_request("POST", "HotelDetails", {"Hotelcodes": code, "Language": "EN"})
    path = f"tbo_details_{code}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"-> {path}  ({len(json.dumps(data))} bytes)")
    print()

    # Top-level keys
    print("top-level keys:", list(data.keys()))
    # Walk and find image-ish fields
    def walk(node, path="$"):
        if isinstance(node, dict):
            for k, v in node.items():
                kl = k.lower()
                if "image" in kl or "photo" in kl or "url" in kl:
                    sample = repr(v)[:120] if not isinstance(v, (list, dict)) else f"<{type(v).__name__} len={len(v)}>"
                    print(f"  {path}.{k} = {sample}")
                walk(v, f"{path}.{k}")
        elif isinstance(node, list) and node:
            walk(node[0], f"{path}[0]")
    walk(data)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "5015627")
