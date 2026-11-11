#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "SFPlayerCharacter.generated.h"
class USpringArmComponent; class UCameraComponent; struct FInputActionValue;

UCLASS()
class SF_DIGITALTWIN_API ASFPlayerCharacter : public ACharacter {
	GENERATED_BODY()
public:
	ASFPlayerCharacter();
	virtual void SetupPlayerInputComponent(UInputComponent* C) override;
	virtual void PossessedBy(AController* NewController) override;
	virtual void OnRep_Controller() override;
	UPROPERTY(EditAnywhere, Category="SF") float WalkSpeed = 220.f;   // cm/s
	UPROPERTY(EditAnywhere, Category="SF") float SprintSpeed = 600.f;
private:
	UPROPERTY(VisibleAnywhere) USpringArmComponent* Arm; UPROPERTY(VisibleAnywhere) UCameraComponent* Cam;
	void OnMove(const FInputActionValue& V); void OnLook(const FInputActionValue& V);
	void SprintOn(); void SprintOff();
};
