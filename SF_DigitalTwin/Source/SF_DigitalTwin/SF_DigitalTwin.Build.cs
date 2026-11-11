using UnrealBuildTool;
public class SF_DigitalTwin : ModuleRules {
	public SF_DigitalTwin(ReadOnlyTargetRules Target) : base(Target) {
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "EnhancedInput", "ChaosVehicles", "UMG", "CinematicCamera", "Niagara" });
	}
}
