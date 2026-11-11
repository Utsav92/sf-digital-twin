"""Download CC0 PBR texture sets from Poly Haven (no account needed) into data/raw/textures/<id>/.
Maps: diffuse (sRGB), roughness, OpenGL normal; 2K JPG. License: CC0 1.0 (polyhaven.com/license).
Records data/raw/textures/textures_manifest.json. Idempotent.
"""
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402
from fetch.fetch_all import download, log  # noqa: E402

OUT = crs.ROOT / "data/raw/textures"
SETS = {  # role: (poly haven id, real-world size of one texture repeat in metres)
    "asphalt": ("asphalt_02", 4.0),
    "concrete": ("concrete_floor_worn_001", 3.0),
    "plaster": ("painted_plaster_wall", 3.0),
    "brick": ("red_brick_03", 2.5),
    "grass": ("aerial_grass_rock", 12.0),
    "sand": ("aerial_beach_01", 12.0),
    "rock": ("rock_face", 6.0),
    "forest": ("forrest_ground_01", 5.0),
    "roof_tiles": ("clay_roof_tiles_02", 3.0),
    "gravel": ("gravel_road", 4.0),
    "metal": ("metal_plate", 2.0),            # lamp poles, signal poles, railings, bridge steel
    "wood": ("wood_planks_grey", 2.0),        # pier decks, benches
}
HERO_4K = {"asphalt", "concrete", "brick", "plaster", "metal", "wood"}  # also fetched at 4K (hero renders)
MAPS = {"diff": "Diffuse", "rough": "Rough", "nor": "nor_gl"}
METAL_MAP = {"metal": ("metal", "Metal")}  # role -> (short, Poly Haven key): extra metalness map
HDRIS = {  # lighting preset -> Poly Haven sky-only HDRI (CC0), used for camera + reflection rays
    "golden_hour": "belfast_sunset_puresky",
    "midday": "kloofendal_48d_partly_cloudy_puresky",
    "blue_hour": "qwantani_dusk_2_puresky",
    "night": "satara_night_no_lamps",
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    man = {"license": "CC0 1.0, Poly Haven (https://polyhaven.com/license)", "sets": {}}
    for role, (pid, size) in SETS.items():
        files = requests.get(f"https://api.polyhaven.com/files/{pid}", timeout=30).json()
        rec = {"id": pid, "size_m": size, "maps": {}}
        for res, field, roles in (("2k", "maps", None), ("4k", "maps4k", HERO_4K), ("8k", "maps8k", HERO_4K)):
            if roles is not None and role not in roles:
                continue
            rec[field] = {}
            items = dict(MAPS)
            if role in METAL_MAP:
                items["metal"] = METAL_MAP[role][1]
            for short, key in items.items():
                url = files[key][res]["jpg"]["url"]
                p = OUT / pid / f"{pid}_{short}_{res}.jpg"
                if not p.exists():
                    download(url, p)
                rec[field][short] = str(p.relative_to(crs.ROOT))
        man["sets"][role] = rec
        log(f"  texture {role}: {pid}")
    man["hdri"] = {}
    for preset, pid in HDRIS.items():
        files = requests.get(f"https://api.polyhaven.com/files/{pid}", timeout=30).json()
        p = OUT / "hdri" / f"{pid}_4k.hdr"
        if not p.exists():
            download(files["hdri"]["4k"]["hdr"]["url"], p)
        man["hdri"][preset] = {"id": pid, "path": str(p.relative_to(crs.ROOT))}
        log(f"  hdri {preset}: {pid}")
    (OUT / "textures_manifest.json").write_text(json.dumps(man, indent=1))


if __name__ == "__main__":
    main()
