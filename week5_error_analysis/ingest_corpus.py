"""Ingest the Week 5 corpus into the multi-doc store (idempotent-ish: skips
identical content hashes)."""

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag_core.store import DocStore


def main():
    store = DocStore()
    for path in sorted(glob.glob("corpus/nimbus_sdk/v*/*.md")):
        with open(path, "rb") as f:
            report = store.add_document(path, f.read())
        print(report["status"], path)

    pdf = "documents/Complete_Guide_to_Major_World_Sports.pdf"
    if os.path.exists(pdf):
        with open(pdf, "rb") as f:
            report = store.add_document(pdf, f.read())
        print(report["status"], pdf)

    print(store.stats())


if __name__ == "__main__":
    main()
