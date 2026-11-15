"""Synthetic data generator entry point (run with: make data)."""

from p2p.config import settings
from p2p.data_gen.master_data import make_materials, make_vendors


def main() -> None:
    out = settings.generated_dir
    out.mkdir(parents=True, exist_ok=True)

    vendors = make_vendors(settings.seed)
    materials = make_materials(settings.seed)
    vendors.to_csv(out / "vendors.csv", index=False)
    materials.to_csv(out / "materials.csv", index=False)

    print(f"seed={settings.seed}: {len(vendors)} vendors, {len(materials)} materials -> {out}")


if __name__ == "__main__":
    main()
