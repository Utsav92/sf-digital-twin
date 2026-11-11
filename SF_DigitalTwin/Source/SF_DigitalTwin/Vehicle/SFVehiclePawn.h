#pragma once
#include "CoreMinimal.h"
#include "WheeledVehiclePawn.h"
#include "ChaosVehicleWheel.h"
#include "SFVehiclePawn.generated.h"
struct FInputActionValue;

UCLASS() class SF_DIGITALTWIN_API USFWheelFront : public UChaosVehicleWheel { GENERATED_BODY() public: USFWheelFront(); };
UCLASS() class SF_DIGITALTWIN_API USFWheelRear : public UChaosVehicleWheel { GENERATED_BODY() public: USFWheelRear(); };

/** Chaos wheeled vehicle on our own rigged car (SK_Vehicle: Root + Wheel_FL/FR/RL/RR). Third-person chase camera. */
UCLASS()
class SF_DIGITALTWIN_API ASFVehiclePawn : public AWheeledVehiclePawn {
	GENERATED_BODY()
public:
	ASFVehiclePawn(const FObjectInitializer& OI);
	virtual void SetupPlayerInputComponent(UInputComponent* C) override;
	virtual void PossessedBy(AController* C) override;
	UPROPERTY(VisibleAnywhere) class USpringArmComponent* Arm; UPROPERTY(VisibleAnywhere) class UCameraComponent* Cam;
private:
	void OnMove(const FInputActionValue& V);
};
