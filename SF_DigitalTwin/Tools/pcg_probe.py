import unreal
names = sorted(n for n in dir(unreal) if n.startswith("PCG"))
print("SFPCG classes", len(names), [n for n in names if n.endswith("Settings")][:200])
for cls in ("PCGStaticMeshSpawnerSettings", "PCGSurfaceSamplerSettings", "PCGPointFromMeshSettings", "PCGGetPrimitiveDataSettings", "PCGSelfPruningSettings", "PCGDensityFilterSettings", "PCGTransformPointsSettings", "PCGCreatePointsGridSettings", "PCGNormalToDensitySettings", "PCGDensityNoiseSettings", "PCGMeshSelectorWeighted", "PCGGetSplineDataSettings", "PCGSplineSamplerSettings"):
    c = getattr(unreal, cls, None)
    if c is None: print("SFPCG missing", cls); continue
    d = c.get_default_object() if hasattr(c, "get_default_object") else None
    print("SFPCG", cls, [p for p in dir(d) if not p.startswith("_") and not callable(getattr(d, p, None))][:60] if d else "no CDO")
ms = sorted(n for n in dir(unreal) if any(n.startswith(p) for p in ("Mass", "ZoneGraph", "ZoneShape", "ChaosWheeled", "ChaosVehicle", "Niagara", "WorldPartition", "StateTree")))
print("SFMASS classes", len(ms), [n for n in ms if any(k in n for k in ("Trait", "Spawner", "EntityConfig", "Representation", "ZoneShape", "ZoneGraph", "Crowd", "Movement", "Wheeled", "NiagaraActor", "NiagaraComponent", "NiagaraSystem", "WorldPartition"))][:300])
print("SFPCG_DONE")
