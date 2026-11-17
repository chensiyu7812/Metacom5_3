"""Build only the unverified RS category catalog; never rebuild bank assets."""
import argparse
from pathlib import Path
from metacom_pm.rl1v3.bank.rs_v0_catalog import build, save
from metacom_pm.rl1v3.bank.v0_port import load_bank


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    bank, _ = load_bank(args.root)
    catalog = build(args.root, bank)
    save(catalog, args.out)
    print(catalog.catalog_id, catalog.data["counts"])


if __name__ == "__main__":main()
