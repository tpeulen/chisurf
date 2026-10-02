"""Isolated native MEM worker; cancellation terminates only this owned process."""

import json
import pickle
import sys

from .model import execute_job


def main():
    request, result = sys.argv[1:3]
    with open(request, "rb") as stream:
        job = pickle.load(stream)

    def progress(done, total):
        print(json.dumps({"done": done, "total": total}), flush=True)

    value = execute_job(job, progress)
    with open(result, "wb") as stream:
        pickle.dump(value, stream)


if __name__ == "__main__":
    main()
