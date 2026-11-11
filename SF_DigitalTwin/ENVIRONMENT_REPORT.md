# Environment report (inspected 2026-11-10)

| Item | Finding |
|---|---|
| macOS | 27.0 (build 26A425), arm64 |
| CPU/GPU | Apple M5 Pro, 16 GPU cores, Metal 4 |
| RAM | 24 GB unified |
| Disk | 460 GB volume; 10 GB free at start (98% full), 33 GB after the user freed space |
| Xcode | 27.2 (27B52), at /Applications/Xcode.app |
| Unreal Engine | UE 5.8.4 (CL 58902052) at ~/unreal/UE_5.8. /Users/Shared/Epic Games/UE_5.7 and UE_5.8 are empty Launcher shells |
| Blender | 5.2.3 LTS at /Applications/Blender.app (no `blender` on PATH) |
| System Python | 3.9.6, no GIS libs. ~/sf_twin/.venv is Python 3.12.16 |
| Existing work | ~/sf_twin: city-wide pipeline, built on rather than replaced |

## Engine plugins present in UE 5.8.4
PCG, PCGInterops, MeshTerrainMode (Experimental), MassAI, MassCrowd, MetaHuman (several), ChaosVehiclesPlugin (Experimental),
PythonScriptPlugin, EditorScriptingUtilities, FastGeoStreaming, AIAssistant (Experimental).

## Not installed
- Cesium for Unreal and a Cesium ion token (needs the user's account).
- Unreal MCP: no MCP plugin found. AIAssistant is not assumed to be an MCP server.
- Gaussian-splat plugin: none found.

## Verified so far
- sf_twin phase checks 1,2,3,4,5,6,7,9,11 each exited 0 when re-run on 2026-11-10.
- Nothing in Unreal has been built or run yet.
