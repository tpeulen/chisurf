"""Print what FPbase's protein and dye spectra endpoints return for one dye (developer probe)."""

import json
import urllib.request


def main() -> None:
    """Query FPbase and print the result."""
    slug = "atto-488"
    url = f"https://www.fpbase.org/api/proteins/spectra/?format=json&protein__slug={slug}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (ChiSurf)"})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read())
            print(f"Atto 488 in proteins/spectra: {len(data) > 0}")
    except Exception:
        print("Atto 488 fetch failed")

    url_dye = f"https://www.fpbase.org/api/dyes/spectra/?format=json&dye__slug={slug}"
    try:
        req = urllib.request.Request(url_dye, headers={"User-Agent": "Mozilla/5.0 (ChiSurf)"})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read())
            print(f"Atto 488 in dyes/spectra: {len(data) > 0}")
    except Exception:
        print("Atto 488 dyes/spectra fetch failed or 404")


if __name__ == "__main__":
    main()
