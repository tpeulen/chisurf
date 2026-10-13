"""Print the first FPbase spectra records (a developer probe; run as a script)."""

import json
import urllib.request


def main() -> None:
    """Query FPbase and print the result."""
    url = "https://www.fpbase.org/api/proteins/spectra/?format=json&limit=5"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (ChiSurf)"})
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read())
        results = data if isinstance(data, list) else data.get("results", [])
        for s in results:
            print(f"Protein: {s.get('protein')}")
            print(f"Name: {s.get('name')}")
            print(f"Data length: {len(s.get('data', []))}")
            print("-" * 20)


if __name__ == "__main__":
    main()
