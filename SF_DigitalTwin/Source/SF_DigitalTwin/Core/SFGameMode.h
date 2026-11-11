#pragma once
#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "SFGameMode.generated.h"

/** Default mode: spawns the third-person walker. Console: SFFly / SFWalk switch to the digital-twin fly camera / character. */
UCLASS()
class SF_DIGITALTWIN_API ASFGameMode : public AGameModeBase {
	GENERATED_BODY()
public:
	ASFGameMode();
	virtual void StartPlay() override;
};
UCLASS()
class SF_DIGITALTWIN_API ASFPlayerController : public APlayerController {
	GENERATED_BODY()
public:
	UFUNCTION(Exec) void SFFly(); UFUNCTION(Exec) void SFWalk(); UFUNCTION(Exec) void SFTeleport(double Lon, double Lat, double HeightM);
	UFUNCTION(Exec) void SFWhere();
	/** Time of day 7-17.5 h: moves sun, recaptures sky, balances exposure; daylight only (07:00-17:30). */
	UFUNCTION(Exec) void SFTime(float Hour);
	/** Photo mode on the current CineCamera view target (or a new one at the view): f-stop, focal length mm, focus distance m, exposure bias EV. */
	UFUNCTION(Exec) void SFPhoto(float FStop, float FocalMm, float FocusM, float EVBias);
	/** Post-process look: cinematic | noir | teal | neutral. */
	UFUNCTION(Exec) void SFFilter(const FString& Name);
	/** Spawn the Chaos vehicle at lon/lat (dropped onto the ground) and possess it. */
	UFUNCTION(Exec) void SFDrive(double Lon, double Lat);
	/** Automated check: spawn, apply full throttle for Seconds, log distance travelled and speed, then quit. */
	UFUNCTION(Exec) void SFDriveTest(double Lon, double Lat, float Seconds);
	/** Fly to lon/lat/height, wait DelaySec for shaders/streaming, save a screenshot, quit. For automated captures. */
	UFUNCTION(Exec) void SFShotAt(double Lon, double Lat, double HeightM, float YawDeg, float PitchDeg, float DelaySec, const FString& Name);
private:
	UPROPERTY() APawn* Walker=nullptr; UPROPERTY() APawn* Flyer=nullptr;
};
