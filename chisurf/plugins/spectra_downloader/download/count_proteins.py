"""Print how many proteins FPbase lists (a developer probe; run as a script)."""

import argparse
import json
import urllib.request


def main() -> None:
    """Query FPbase and print the result."""
    parser = argparse.ArgumentParser(description="Count FPbase proteins")
    parser.add_argument("--db", help="Ignored compatibility option", default=None)
    parser.parse_args()

    url = "https://www.fpbase.org/api/proteins/?format=json&limit=1"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (ChiSurf)"})
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read())
        if isinstance(data, dict):
            print(f"Total proteins: {data.get('count')}")
        else:
            print(f"Total proteins: {len(data)}")


if __name__ == "__main__":
    main()
