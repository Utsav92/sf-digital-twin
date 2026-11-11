#include "SFPlayerCharacter.h"
#include "SFInputSetup.h"
#include "GameFramework/SpringArmComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "EnhancedInputComponent.h"
#include "InputActionValue.h"
#include "UObject/ConstructorHelpers.h"

ASFPlayerCharacter::ASFPlayerCharacter() {
	GetCapsuleComponent()->InitCapsuleSize(35.f, 90.f);
	bUseControllerRotationYaw = false;
	GetCharacterMovement()->bOrientRotationToMovement = true;
	GetCharacterMovement()->RotationRate = FRotator(0, 540, 0);
	GetCharacterMovement()->MaxWalkSpeed = WalkSpeed;
	GetCharacterMovement()->JumpZVelocity = 420.f;
	GetCharacterMovement()->MaxStepHeight = 30.f;
	GetCharacterMovement()->SetWalkableFloorAngle(50.f);   // SF sidewalks and hills
	Arm = CreateDefaultSubobject<USpringArmComponent>(TEXT("Arm")); Arm->SetupAttachment(RootComponent);
	Arm->TargetArmLength = 350.f; Arm->bUsePawnControlRotation = true; Arm->SocketOffset = FVector(0, 0, 60);
	Cam = CreateDefaultSubobject<UCameraComponent>(TEXT("Cam")); Cam->SetupAttachment(Arm);
	// Placeholder body: engine primitive capsule (no licensed character model is bundled yet).
	UStaticMeshComponent* Body = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Body")); Body->SetupAttachment(RootComponent);
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cyl(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	if (Cyl.Succeeded()) { Body->SetStaticMesh(Cyl.Object); Body->SetRelativeScale3D(FVector(0.6f, 0.6f, 1.7f)); Body->SetRelativeLocation(FVector(0, 0, -5)); Body->SetCollisionEnabled(ECollisionEnabled::NoCollision); }
}

void ASFPlayerCharacter::PossessedBy(AController* C) { Super::PossessedBy(C); FSFInput::Get(this).Apply(Cast<APlayerController>(C)); }
void ASFPlayerCharacter::OnRep_Controller() { Super::OnRep_Controller(); FSFInput::Get(this).Apply(Cast<APlayerController>(Controller)); }

void ASFPlayerCharacter::SetupPlayerInputComponent(UInputComponent* C) {
	Super::SetupPlayerInputComponent(C);
	FSFInput& I = FSFInput::Get(this);
	if (auto* E = Cast<UEnhancedInputComponent>(C)) {
		E->BindAction(I.Move, ETriggerEvent::Triggered, this, &ASFPlayerCharacter::OnMove);
		E->BindAction(I.Look, ETriggerEvent::Triggered, this, &ASFPlayerCharacter::OnLook);
		E->BindAction(I.Jump, ETriggerEvent::Started, this, &ACharacter::Jump);
		E->BindAction(I.Jump, ETriggerEvent::Completed, this, &ACharacter::StopJumping);
		E->BindAction(I.Sprint, ETriggerEvent::Started, this, &ASFPlayerCharacter::SprintOn);
		E->BindAction(I.Sprint, ETriggerEvent::Completed, this, &ASFPlayerCharacter::SprintOff);
	}
}
void ASFPlayerCharacter::OnMove(const FInputActionValue& V) {
	const FVector2D M = V.Get<FVector2D>(); const FRotator Y(0, Controller->GetControlRotation().Yaw, 0);
	AddMovementInput(FRotationMatrix(Y).GetUnitAxis(EAxis::X), M.Y);
	AddMovementInput(FRotationMatrix(Y).GetUnitAxis(EAxis::Y), M.X);
}
void ASFPlayerCharacter::OnLook(const FInputActionValue& V) { const FVector2D L = V.Get<FVector2D>(); AddControllerYawInput(L.X); AddControllerPitchInput(-L.Y); }
void ASFPlayerCharacter::SprintOn() { GetCharacterMovement()->MaxWalkSpeed = SprintSpeed; }
void ASFPlayerCharacter::SprintOff() { GetCharacterMovement()->MaxWalkSpeed = WalkSpeed; }
