#include "Misc/AutomationTest.h"
#include "SFGeoCoords.h"

#if WITH_DEV_AUTOMATION_TESTS
// Reference UTM values computed independently with pyproj (EPSG:4269 -> EPSG:26910).
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FSFGeoCoordsTest, "SF.Geo.UTM10AgainstPyproj", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FSFGeoCoordsTest::RunTest(const FString&) {
	struct FP { const TCHAR* N; double Lon, Lat, E, Nn; };
	const FP P[] = {
		{TEXT("Ferry"), -122.3934, 37.79554, 553405.6346, 4183303.4126},
		{TEXT("GoldenGateBridgeSouth"), -122.4783, 37.8105, 545921.6387, 4184918.1114},
		{TEXT("TwinPeaks"), -122.4477, 37.7544, 548651.9252, 4178709.3345},
		{TEXT("OracleParkish"), -122.3893, 37.7786, 553778.8811, 4181426.2758},
		{TEXT("OceanBeach"), -122.5107, 37.7593, 543099.3968, 4179222.0951},
	};
	for (const FP& p : P) {
		double E, N, Lo, La; USFGeoCoords::LonLatToUTM10(p.Lon, p.Lat, E, N);
		TestTrue(FString::Printf(TEXT("%s forward within 1 cm (dE %.4f dN %.4f)"), p.N, E - p.E, N - p.Nn), FMath::Abs(E - p.E) < 0.01 && FMath::Abs(N - p.Nn) < 0.01);
		USFGeoCoords::UTM10ToLonLat(E, N, Lo, La);
		TestTrue(FString::Printf(TEXT("%s round trip within 1e-9 deg"), p.N), FMath::Abs(Lo - p.Lon) < 1e-9 && FMath::Abs(La - p.Lat) < 1e-9);
	}
	const FVector Ferry = USFGeoCoords::LonLatHeightToUnreal(-122.3934, 37.79554, 0.0);
	TestTrue(TEXT("Ferry Building maps to Unreal origin within 2 cm"), Ferry.Size() < 2.0);
	// Salesforce Tower manifest location (cm): north of Ferry = negative Unreal Y
	double Lo, La, H; USFGeoCoords::UnrealToLonLatHeight(FVector(-30670.9, 64160.4, 467.0), Lo, La, H);
	AddInfo(FString::Printf(TEXT("Salesforce pivot from manifest -> lon %.6f lat %.6f"), Lo, La));
	return true;
}
#endif
