using UnrealBuildTool;
public class SF_DigitalTwinEditorTarget : TargetRules {
	public SF_DigitalTwinEditorTarget(TargetInfo Target) : base(Target) {
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("SF_DigitalTwin");
	}
}
