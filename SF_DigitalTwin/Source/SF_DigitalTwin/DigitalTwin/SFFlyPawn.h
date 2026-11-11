#pragma once
#include "CoreMinimal.h"
#include "GameFramework/SpectatorPawn.h"
#include "SFFlyPawn.generated.h"
struct FInputActionValue;

/** City-scale fly-through camera. Speed scales with altitude so the whole 12 km city and street level are both usable. */
UCLASS()
class SF_DIGITALTWIN_API ASFFlyPawn : public ASpectatorPawn {
	GENERATED_BODY()
public:
	ASFFlyPawn();
	virtual void SetupPlayerInputComponent(UInputComponent* C) override;
	virtual void PossessedBy(AController* C) override;
	virtual void Tick(float Dt) override;
	UPROPERTY(EditAnywhere, Category="SF") float MinSpeedCmS = 1500.f;       // 15 m/s
	UPROPERTY(EditAnywhere, Category="SF") float AltitudeSpeedFactor = 1.5f; // speed = factor * altitude per second
	UPROPERTY(EditAnywhere, Category="SF") float BoostMul = 4.f;
	/** Last computed WGS84/NAD83 position of the camera, for the HUD. */
	UPROPERTY(BlueprintReadOnly, Category="SF") double Lon=0, Lat=0, HeightM=0;
private:
	FVector2D MoveIn=FVector2D::ZeroVector; float UpIn=0, DownIn=0; bool bBoost=false;
	void OnMove(const FInputActionValue& V); void OnLook(const FInputActionValue& V);
};
