# Issue log
| # | Status | Issue |
|---|---|---|
| 1 | open | Imported USD materials are default `MI_MAT_*` instances with no authored colour; buildings render near-black. Need master materials per `config/unreal_materials.json`. |
| 2 | open | Every tile imports as one merged static mesh (about 3 MB asset for a 125k-tri tile). World Partition streaming and Nanite settings not configured; import of all 618 tiles untested. |
| 3 | open | Chaos vehicle not started: no licensed/created skeletal car. |
| 4 | open | Cesium for Unreal, Cesium ion token, Unreal MCP, splat plugin are not installed. MCP tool names unverified; none are used. |
| 5 | open | Pilot tile USD files are from the older pilot export (backed up at /tmp/claude-501/unreal_pilot_backup); re-exporting them gives 88 MB per tile because detail layers are now built there. |
| 6 | open | Character/fly pawn/input untested interactively. |
| 7 | open | `SFShotAt` ignores the `filename=` quoting; it saves under `Saved/Screenshots/MacEditor/<name>.png`. |
| 8 | fixed | export_unreal.py: linked material rename crash (Blender 5.2). |
| 9 | fixed | export_unreal.py: props layer leaked into tile USD (UVs, bounds, material names failed on 102-413 tiles). |
| 10 | fixed | run_all.sh: empty-array crash on macOS bash 3.2 (`SEL[@]`). |
| 11 | fixed | Makefile `unreal` target pointed at an empty Launcher folder. |
| 12 | note | UE editor reports `Android`, `Win64`, `Linux` SDKs invalid; irrelevant for a Mac build. |
