# SF Digital Twin: status (2026-11-10)

Built on the existing `~/sf_twin` pipeline. Data, terrain, roads, buildings and landmarks come from there; this folder is the UE 5.8.4 project.

## Verified (executed, not assumed)
| Item | Evidence |
|---|---|
| sf_twin phase checks 1-7, 9, 11 re-run | each exited 0 on 2026-11-10 |
| Full-city USD export for Unreal: 618 of 618 tiles | `check_phase11.py`: 0 failures (units, triangulated, UVs, material names, bounds to 1 cm, Salesforce anchor) |
| Exporter fixes | Blender 5.2 linked-material rename crash; props layer excluded (cars/lamps are instance data); one shared `out/unreal/textures` folder instead of 53 MB per tile (8.3 GB total instead of ~40 GB) |
| UE C++ module compiles with Xcode toolchain | `Build.sh SF_DigitalTwinEditor Mac Development` succeeded |
| Geo transform (WGS84/NAD83 to UTM 10N to city m to Unreal cm) | UE automation test `SF.Geo.UTM10AgainstPyproj` passed: 5 landmarks within 1 cm of pyproj, round trip within 1e-9 deg |
| USD import into UE | 16 pilot tiles + 12 landmarks imported (28 import tasks) |
| Map `/Game/Maps/SF_Pilot` | 16 tiles + 12 landmarks placed at manifest locations; sky, sun, fog |
| Real Metal render | `screenshots/unreal_pilot_downtown_aerial.png` (UE game mode, 1920x1080) |

## Written but NOT yet run or tested
Third-person character (`ASFPlayerCharacter`), fly camera (`ASFFlyPawn`), game mode and console commands (SFFly, SFWalk, SFTeleport, SFWhere). They compile; I have not driven them interactively. Keyboard/PlayStation bindings are untested.

## Not done
- Drivable Chaos vehicle (needs a skeletal car asset; none licensed/created yet).
- Imports for the other 602 tiles (disk and time cost not measured; see issues).
- Cesium for Unreal, Unreal MCP, Gaussian splat plugin, Mesh Terrain, PCG graphs, traffic, pedestrians, missions, UI, cinematics, macOS packaging.
- Performance numbers: none recorded. No FPS, memory or frame-time claims are made.

## Reproduce
```
make unreal                                  # build editor target
SF_IDS=... SF_LANDMARKS=... UnrealEditor SF_DigitalTwin.uproject -ExecutePythonScript=Tools/import_usd.py -unattended
UnrealEditor SF_DigitalTwin.uproject -ExecutePythonScript=Tools/build_map.py -unattended
UnrealEditor SF_DigitalTwin.uproject /Game/Maps/SF_Pilot -game -ExecCmds="SFShotAt <lon> <lat> <h_m> <yaw> <pitch> <delay_s> <name>"
```
Camera yaw: Unreal Y is flipped (north = -Y), so yaw = atan2(-dNorth, dEast).

## 2026-11-11 update
Done and verified by screenshot: full 618-tile import with detail layers, Nanite on all 630 meshes, per-mesh materials, World Partition conversion (SF_City converted in place; 640 external actors), 30 km loading range set in ASFGameMode::StartPlay (without it nothing but the always-loaded landmarks streams), 208,666 trees from out/unreal/instances placed by ASFTreeField (instanced meshes, C++; not a PCG graph), original props + SK_Vehicle imported.
Fixed: M_SF_Master/M_SF_Facade lacked "used with instanced static meshes" and "used with Nanite", so instanced meshes rendered with the default material; roof/trim detail now renders.
Measured (Apple M5 Pro, 1920x1080 windowed, Development build, full city + trees): ~31 fps average, worst frame ~61 ms, ~9.8 GB physical memory.
Spawned but not visually verified: 4 Niagara FountainLightweight (engine template) systems at plazas.
NOT working / NOT done: Chaos vehicle (builds, simulates, launches upward instead of settling; tile meshes have no collision so ground trace hits only the ocean plane), PCG graph (no CSV loader node in PCG 5.8), Mass crowds/traffic, final video.
Known visual flaws: hard ocean-plane/sky horizon line, dark fuzzy rectangle in bay foreground, window moire at distance.
