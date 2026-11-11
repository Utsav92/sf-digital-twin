using UnrealBuildTool;
public class SF_DigitalTwinTarget : TargetRules {
	public SF_DigitalTwinTarget(TargetInfo Target) : base(Target) {
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("SF_DigitalTwin");
	}
}
