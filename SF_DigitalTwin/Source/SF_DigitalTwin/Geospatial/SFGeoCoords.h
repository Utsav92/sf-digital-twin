#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "SFGeoCoords.generated.h"

/**
 * Single shared transform for all SF data: WGS84 <-> UTM 10N (EPSG:26910, NAD83) <-> city metres <-> Unreal cm.
 * Conventions match sf_twin/out/city/manifest.json:
 *   city m  = UTM - origin(Ferry Building 553405.6345588617, 4183303.412602094), x east, y north, z up
 *   Unreal  = X east*100, Y -north*100, Z up*100
 * NAD83 and WGS84 differ by about 1 m; the sf_twin data is NAD83, and this treats WGS84 input as NAD83 (GRS80 ellipsoid).
 */
UCLASS()
class SF_DIGITALTWIN_API USFGeoCoords : public UBlueprintFunctionLibrary {
	GENERATED_BODY()
public:
	static constexpr double OriginE = 553405.6345588617;
	static constexpr double OriginN = 4183303.412602094;

	UFUNCTION(BlueprintPure, Category="SF|Geo") static void LonLatToUTM10(double LonDeg, double LatDeg, double& Easting, double& Northing);
	UFUNCTION(BlueprintPure, Category="SF|Geo") static void UTM10ToLonLat(double Easting, double Northing, double& LonDeg, double& LatDeg);
	UFUNCTION(BlueprintPure, Category="SF|Geo") static FVector LonLatHeightToUnreal(double LonDeg, double LatDeg, double HeightM);
	UFUNCTION(BlueprintPure, Category="SF|Geo") static void UnrealToLonLatHeight(const FVector& Location, double& LonDeg, double& LatDeg, double& HeightM);
	UFUNCTION(BlueprintPure, Category="SF|Geo") static FVector CityMetersToUnreal(double X, double Y, double Z);
};
