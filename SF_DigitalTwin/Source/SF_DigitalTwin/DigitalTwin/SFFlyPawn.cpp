#include "SFFlyPawn.h"
#include "../Player/SFInputSetup.h"
#include "../Geospatial/SFGeoCoords.h"
#include "EnhancedInputComponent.h"
#include "InputActionValue.h"
#include "GameFramework/PlayerController.h"

ASFFlyPawn::ASFFlyPawn() { PrimaryActorTick.bCanEverTick = true; }
void ASFFlyPawn::PossessedBy(AController* C) { Super::PossessedBy(C); FSFInput::Get(this).Apply(Cast<APlayerController>(C)); }
void ASFFlyPawn::SetupPlayerInputComponent(UInputComponent* C) {
	if (auto* E = Cast<UEnhancedInputComponent>(C)) {
		FSFInput& I = FSFInput::Get(this);
		E->BindAction(I.Move, ETriggerEvent::Triggered, this, &ASFFlyPawn::OnMove);
		E->BindAction(I.Move, ETriggerEvent::Completed, this, &ASFFlyPawn::OnMove);
		E->BindAction(I.Look, ETriggerEvent::Triggered, this, &ASFFlyPawn::OnLook);
		E->BindActionValueLambda(I.Up, ETriggerEvent::Triggered, [this](const FInputActionValue& V){ UpIn = V.Get<float>(); });
		E->BindActionValueLambda(I.Up, ETriggerEvent::Completed, [this](const FInputActionValue&){ UpIn = 0; });
		E->BindActionValueLambda(I.Down, ETriggerEvent::Triggered, [this](const FInputActionValue& V){ DownIn = V.Get<float>(); });
		E->BindActionValueLambda(I.Down, ETriggerEvent::Completed, [this](const FInputActionValue&){ DownIn = 0; });
		E->BindActionValueLambda(I.Boost, ETriggerEvent::Triggered, [this](const FInputActionValue&){ bBoost = true; });
		E->BindActionValueLambda(I.Boost, ETriggerEvent::Completed, [this](const FInputActionValue&){ bBoost = false; });
	}
}
void ASFFlyPawn::OnMove(const FInputActionValue& V) { MoveIn = V.Get<FVector2D>(); }
void ASFFlyPawn::OnLook(const FInputActionValue& V) { const FVector2D L = V.Get<FVector2D>(); AddControllerYawInput(L.X); AddControllerPitchInput(-L.Y); }
void ASFFlyPawn::Tick(float Dt) {
	Super::Tick(Dt);
	const FVector P = GetActorLocation();
	const float Alt = FMath::Max(P.Z, 0.f);
	const float Speed = FMath::Max(MinSpeedCmS, AltitudeSpeedFactor * Alt) * (bBoost ? BoostMul : 1.f);
	const FRotator R = GetControlRotation();
	FVector D = R.Vector() * MoveIn.Y + FRotationMatrix(R).GetUnitAxis(EAxis::Y) * MoveIn.X + FVector::UpVector * (UpIn - DownIn);
	SetActorLocation(P + D.GetClampedToMaxSize(1.f) * Speed * Dt, false);
	USFGeoCoords::UnrealToLonLatHeight(GetActorLocation(), Lon, Lat, HeightM);
}
