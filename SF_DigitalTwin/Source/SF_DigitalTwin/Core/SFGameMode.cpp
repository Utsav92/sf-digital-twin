#include "SFGameMode.h"
#include "Containers/Ticker.h"
#include "HAL/PlatformMemory.h"
#include "NiagaraFunctionLibrary.h"
#include "NiagaraSystem.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "Components/SkeletalMeshComponent.h"
#include "../DigitalTwin/SFTreeField.h"
#include "../Player/SFPlayerCharacter.h"
#include "../DigitalTwin/SFFlyPawn.h"
#include "../Geospatial/SFGeoCoords.h"
#include "Engine/Engine.h"
#include "CineCameraActor.h"
#include "CineCameraComponent.h"
#include "Kismet/GameplayStatics.h"
#include "EngineUtils.h"
#include "Engine/DirectionalLight.h"
#include "Engine/SkyLight.h"
#include "Engine/PostProcessVolume.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/SkyLightComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "../Vehicle/SFVehiclePawn.h"
#include "ChaosVehicleMovementComponent.h"

ASFGameMode::ASFGameMode() { DefaultPawnClass = ASFPlayerCharacter::StaticClass(); PlayerControllerClass = ASFPlayerController::StaticClass(); }
void ASFGameMode::StartPlay() {
	Super::StartPlay();
	// The whole 618-tile city must stay resident for skyline shots: widen the World Partition loading range to 30 km (dev builds).
	GetWorld()->SpawnActor<ASFTreeField>(ASFTreeField::StaticClass());
	{ // frame-time log for the performance report: average fps / worst frame / physical memory every 10 s
		struct FPerf { double T = 0; int32 N = 0; float Worst = 0; };
		TSharedPtr<FPerf> PF = MakeShared<FPerf>();
		FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateLambda([PF](float Dt) {
			PF->T += Dt; ++PF->N; PF->Worst = FMath::Max(PF->Worst, Dt);
			if (PF->T >= 10.0) { UE_LOG(LogTemp, Display, TEXT("SFPERF avg %.1f fps (%.1f ms) worst frame %.0f ms physmem %.1f GB"), PF->N / PF->T, 1000.0 * PF->T / PF->N, PF->Worst * 1000.f, FPlatformMemory::GetStats().UsedPhysical / 1073741824.0); PF->T = 0; PF->N = 0; PF->Worst = 0; }
			return true; }));
	}
	// Niagara: engine template fountains at real SF plazas (Embarcadero Plaza, Union Square, Civic Center Plaza, Yerba Buena Gardens).
	if (UNiagaraSystem* Fountain = LoadObject<UNiagaraSystem>(nullptr, TEXT("/Niagara/DefaultAssets/Templates/Systems/FountainLightweight.FountainLightweight"))) {
		const double Plazas[4][2] = { {-122.3965, 37.7939}, {-122.4075, 37.7880}, {-122.4177, 37.7793}, {-122.4022, 37.7845} };
		for (const auto& L : Plazas) UNiagaraFunctionLibrary::SpawnSystemAtLocation(GetWorld(), Fountain, USFGeoCoords::LonLatHeightToUnreal(L[0], L[1], 10.0), FRotator::ZeroRotator, FVector(3.f), true, true);
		UE_LOG(LogTemp, Display, TEXT("SFFX spawned 4 plaza fountains"));
	} else UE_LOG(LogTemp, Warning, TEXT("SFFX fountain system missing"));
	if (GEngine) GEngine->Exec(GetWorld(), TEXT("wp.Runtime.OverrideRuntimeLoadingRange -grid=MainPartition -range=3000000"));
}

void ASFPlayerController::SFFly() {
	APawn* Cur = GetPawn(); if (Cur == Flyer) return;
	if (Cur && !Walker) Walker = Cur;
	if (!Flyer) { FActorSpawnParameters P; P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn; Flyer = GetWorld()->SpawnActor<ASFFlyPawn>(ASFFlyPawn::StaticClass(), (Cur?Cur->GetActorLocation():FVector::ZeroVector) + FVector(0,0,30000), GetControlRotation(), P); }
	Possess(Flyer);
}
void ASFPlayerController::SFWalk() { if (Walker) { Walker->SetActorLocation(Flyer ? Flyer->GetActorLocation() : Walker->GetActorLocation()); Possess(Walker); } }
void ASFPlayerController::SFTeleport(double Lon, double Lat, double H) {
	if (APawn* P = GetPawn()) P->SetActorLocation(USFGeoCoords::LonLatHeightToUnreal(Lon, Lat, H), false, nullptr, ETeleportType::TeleportPhysics);
}
void ASFPlayerController::SFWhere() {
	if (APawn* P = GetPawn()) { double Lo, La, H; USFGeoCoords::UnrealToLonLatHeight(P->GetActorLocation(), Lo, La, H);
		UE_LOG(LogTemp, Display, TEXT("SF position lon %.6f lat %.6f height %.1f m"), Lo, La, H); }
}

void ASFPlayerController::SFShotAt(double Lon, double Lat, double H, float Yaw, float Pitch, float Delay, const FString& Name) {
	// Cinematic, deterministic capture: a CineCamera (35 mm super-35, f/2.8) is the view target, so no pawn/controller state can move it.
	const FVector Loc = USFGeoCoords::LonLatHeightToUnreal(Lon, Lat, H);
	FActorSpawnParameters P; P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ACineCameraActor* Cam = GetWorld()->SpawnActor<ACineCameraActor>(ACineCameraActor::StaticClass(), Loc, FRotator(Pitch, Yaw, 0), P);
	if (UCineCameraComponent* C = Cam ? Cam->GetCineCameraComponent() : nullptr) {
		C->CurrentFocalLength = 35.f; C->CurrentAperture = 2.8f;
		C->FocusSettings.FocusMethod = ECameraFocusMethod::Disable;
		C->Filmback.SensorWidth = 24.89f; C->Filmback.SensorHeight = 14.0f; /* Super 35, 16:9 */
		C->bConstrainAspectRatio = false; C->SetFieldOfView(C->GetHorizontalFieldOfView());
	}
	// World Partition streams around the pawn (the streaming source), so park it under the camera or the tiles never load.
	if (APawn* SP = GetPawn()) SP->SetActorLocation(Loc, false, nullptr, ETeleportType::TeleportPhysics);
	if (Cam) SetViewTargetWithBlend(Cam, 0.f);
	UE_LOG(LogTemp, Display, TEXT("SFSHOT camera at %s rot P%.1f Y%.1f view target %s"), *Loc.ToString(), Pitch, Yaw, Cam ? *Cam->GetName() : TEXT("none"));
	FTimerHandle T1, T2;
	GetWorldTimerManager().SetTimer(T1, [this, Name]() {
		ConsoleCommand(FString::Printf(TEXT("HighResShot 1920x1080 filename=\"%s\""), *Name));
	}, Delay, false);
	GetWorldTimerManager().SetTimer(T2, [this]() { ConsoleCommand(TEXT("quit")); }, Delay + 8.f, false);
}

static APostProcessVolume* SFGetPPV(UWorld* W) { for (TActorIterator<APostProcessVolume> It(W); It; ++It) if (It->bUnbound) return *It; return nullptr; }

void ASFPlayerController::SFTime(float Hour) {
	Hour = FMath::Clamp(Hour, 7.f, 17.5f);   // daylight only; night mode removed
	const float AltDeg = 62.f * FMath::Cos(FMath::DegreesToRadians((Hour - 12.f) * 15.f)) + 2.f;  // noon ~56 deg, midnight ~-68
	const float AzDeg = 90.f + (Hour - 6.f) * 15.f;                                            // compass bearing, east at 06, west at 18
	for (TActorIterator<ADirectionalLight> It(GetWorld()); It; ++It) {
		UDirectionalLightComponent* L = Cast<UDirectionalLightComponent>(It->GetLightComponent());
		It->SetActorRotation(FRotator(-AltDeg, AzDeg - 90.f, 0.f));
		const float Day = FMath::Clamp((AltDeg + 2.f) / 10.f, 0.f, 1.f);                       // fade out through twilight
		const float Warm = 1.f - FMath::Clamp(AltDeg / 30.f, 0.f, 1.f);
		L->SetIntensity(14.f * Day);
		L->SetLightColor(FLinearColor::LerpUsingHSV(FLinearColor(1.f, 0.97, 0.93), FLinearColor(1.f, 0.62f, 0.35f), Warm));
		L->MarkRenderStateDirty();
	}
	for (TActorIterator<ASkyLight> It(GetWorld()); It; ++It) It->GetLightComponent()->RecaptureSky();
	UE_LOG(LogTemp, Display, TEXT("SFTIME hour %.1f sun altitude %.1f azimuth %.1f"), Hour, AltDeg, AzDeg);
}

void ASFPlayerController::SFPhoto(float FStop, float FocalMm, float FocusM, float EVBias) {
	ACineCameraActor* Cam = Cast<ACineCameraActor>(GetViewTarget());
	if (!Cam) {
		FActorSpawnParameters P; P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		FVector L; FRotator R; GetPlayerViewPoint(L, R);
		Cam = GetWorld()->SpawnActor<ACineCameraActor>(ACineCameraActor::StaticClass(), L, R, P);
		if (Cam) { Cam->GetCineCameraComponent()->Filmback.SensorWidth = 24.89f; Cam->GetCineCameraComponent()->Filmback.SensorHeight = 14.f; Cam->GetCineCameraComponent()->bConstrainAspectRatio = false; SetViewTargetWithBlend(Cam, 0.f); }
	}
	if (!Cam) return;
	UCineCameraComponent* C = Cam->GetCineCameraComponent();
	C->CurrentAperture = FStop; C->CurrentFocalLength = FocalMm;
	C->FocusSettings.FocusMethod = ECameraFocusMethod::Manual; C->FocusSettings.ManualFocusDistance = FocusM * 100.f;
	C->PostProcessSettings.bOverride_AutoExposureBias = true; C->PostProcessSettings.AutoExposureBias = EVBias;
	UE_LOG(LogTemp, Display, TEXT("SFPHOTO f/%.1f %.0f mm focus %.1f m EV %.1f"), FStop, FocalMm, FocusM, EVBias);
}

void ASFPlayerController::SFFilter(const FString& Name) {
	APostProcessVolume* V = SFGetPPV(GetWorld()); if (!V) return;
	FPostProcessSettings& S = V->Settings;
	float Sat = 0.9f, Con = 1.12f, Vig = 0.35f, Grain = 0.05f; FLinearColor Tint(1.f, 0.97f, 0.93f); float Chroma = 0.f;
	if (Name == TEXT("noir")) { Sat = 0.f; Con = 1.3f; Vig = 0.6f; Grain = 0.25f; Tint = FLinearColor(1.f, 1.f, 1.f); }
	else if (Name == TEXT("teal")) { Sat = 1.05f; Con = 1.18f; Vig = 0.45f; Grain = 0.08f; Tint = FLinearColor(0.88f, 0.98f, 1.05f); Chroma = 0.3f; }
	else if (Name == TEXT("neutral")) { Sat = 1.f; Con = 1.f; Vig = 0.f; Grain = 0.f; Tint = FLinearColor::White; }
	S.bOverride_ColorSaturation = true; S.ColorSaturation = FVector4(Sat, Sat, Sat, 1.f);
	S.bOverride_ColorContrast = true; S.ColorContrast = FVector4(Con, Con, Con, 1.f);
	S.bOverride_VignetteIntensity = true; S.VignetteIntensity = Vig;
	S.bOverride_FilmGrainIntensity = true; S.FilmGrainIntensity = Grain;
	S.bOverride_SceneColorTint = true; S.SceneColorTint = Tint;
	S.bOverride_SceneFringeIntensity = true; S.SceneFringeIntensity = Chroma;
	UE_LOG(LogTemp, Display, TEXT("SFFILTER %s"), *Name);
}

void ASFPlayerController::SFDrive(double Lon, double Lat) {
	FVector P = USFGeoCoords::LonLatHeightToUnreal(Lon, Lat, 800.0); FHitResult Hit;
	FCollisionQueryParams Q; Q.bTraceComplex = true;
	if (GetWorld()->LineTraceSingleByChannel(Hit, P, P - FVector(0, 0, 200000.f), ECC_Visibility, Q)) { P = Hit.ImpactPoint + FVector(0, 0, 120.f); UE_LOG(LogTemp, Display, TEXT("SFDRIVE ground hit %s z %.0f"), Hit.GetComponent() ? *Hit.GetComponent()->GetName() : TEXT("?"), Hit.ImpactPoint.Z); }
	else UE_LOG(LogTemp, Warning, TEXT("SFDRIVE no ground hit under lon %.5f lat %.5f"), Lon, Lat);
	FActorSpawnParameters SP; SP.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
	if (ASFVehiclePawn* V = GetWorld()->SpawnActor<ASFVehiclePawn>(ASFVehiclePawn::StaticClass(), P, FRotator::ZeroRotator, SP)) { Possess(V); UE_LOG(LogTemp, Display, TEXT("SFDRIVE spawned vehicle at %s"), *P.ToString()); }
}
void ASFPlayerController::SFDriveTest(double Lon, double Lat, float Seconds) {
	// Wait for World Partition to stream the ground in, then spawn, floor it, and log distance/speed once a second.
	FTimerHandle W; int32* N = new int32(0);
	GetWorldTimerManager().SetTimer(W, [this, Lon, Lat, N]() {
		SFDrive(Lon, Lat);
		ASFVehiclePawn* V = Cast<ASFVehiclePawn>(GetPawn()); if (!V) { UE_LOG(LogTemp, Error, TEXT("SFDRIVETEST no vehicle")); return; }
		const FVector Start = V->GetActorLocation(); V->GetVehicleMovementComponent()->SetThrottleInput(1.f);
		USkeletalMeshComponent* SM = V->GetMesh(); UE_LOG(LogTemp, Display, TEXT("SFDRIVETEST sim=%d pa=%s bones=%d bone0=%s bodies=%d collision=%d"), SM->IsSimulatingPhysics(), SM->GetPhysicsAsset() ? *SM->GetPhysicsAsset()->GetName() : TEXT("none"), SM->GetNumBones(), SM->GetNumBones() ? *SM->GetBoneName(0).ToString() : TEXT("-"), SM->Bodies.Num(), (int32)SM->GetCollisionEnabled()); UE_LOG(LogTemp, Display, TEXT("SFDRIVETEST gravity=%d mass=%.0f gz=%.0f"), SM->IsGravityEnabled(), SM->GetMass(), GetWorld()->GetGravityZ());
		FTimerHandle T; GetWorldTimerManager().SetTimer(T, [V, Start, N]() { ++*N;
			UE_LOG(LogTemp, Display, TEXT("SFDRIVETEST t=%ds moved %.1f m speed %.1f km/h z %.0f"), *N, FVector::Dist2D(V->GetActorLocation(), Start) / 100.f, V->GetVehicleMovementComponent()->GetForwardSpeedMPH() * 1.609f, V->GetActorLocation().Z); }, 1.f, true);
	}, 60.f, false);
	FTimerHandle Q; GetWorldTimerManager().SetTimer(Q, [this]() { ConsoleCommand(TEXT("quit")); }, 60.f + Seconds, false);
}
