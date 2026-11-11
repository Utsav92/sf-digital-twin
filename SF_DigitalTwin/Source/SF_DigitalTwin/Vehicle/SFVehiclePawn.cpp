#include "SFVehiclePawn.h"
#include "ChaosWheeledVehicleMovementComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "Camera/CameraComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "EnhancedInputComponent.h"
#include "InputActionValue.h"
#include "../Player/SFInputSetup.h"
#include "GameFramework/PlayerController.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "PhysicsEngine/SkeletalBodySetup.h"
#include "PhysicsEngine/BoxElem.h"

USFWheelFront::USFWheelFront() {
	WheelRadius = 34.f; WheelWidth = 24.f; AxleType = EAxleType::Front; bAffectedBySteering = true; MaxSteerAngle = 38.f;
	bAffectedByHandbrake = false; bAffectedByEngine = false; FrictionForceMultiplier = 3.f;
	SuspensionMaxRaise = 8.f; SuspensionMaxDrop = 12.f; SpringRate = 250.f; SuspensionDampingRatio = 0.7f;
}
USFWheelRear::USFWheelRear() {
	WheelRadius = 34.f; WheelWidth = 24.f; AxleType = EAxleType::Rear; bAffectedBySteering = false;
	bAffectedByHandbrake = true; bAffectedByEngine = true; FrictionForceMultiplier = 3.f;
	SuspensionMaxRaise = 8.f; SuspensionMaxDrop = 12.f; SpringRate = 250.f; SuspensionDampingRatio = 0.7f;
}

ASFVehiclePawn::ASFVehiclePawn(const FObjectInitializer& OI) : Super(OI) {
	if (USkeletalMesh* SK = LoadObject<USkeletalMesh>(nullptr, TEXT("/Game/Vehicle/SK_Vehicle.SK_Vehicle"))) GetMesh()->SetSkeletalMesh(SK);
	// The FBX carries no physics asset, so the chassis would never simulate: build a one-box chassis body on the root bone.
	UPhysicsAsset* PA = CreateDefaultSubobject<UPhysicsAsset>(TEXT("ChassisPhysics"));
	USkeletalBodySetup* BS = NewObject<USkeletalBodySetup>(PA, TEXT("Chassis"), RF_Transactional);
	BS->BoneName = TEXT("Root"); BS->PhysicsType = PhysType_Default; BS->CollisionTraceFlag = CTF_UseSimpleAsComplex;
	FKBoxElem Box(180.f, 440.f, 110.f); Box.Center = FVector(0, 0, 90.f); BS->AggGeom.BoxElems.Add(Box);
	PA->SkeletalBodySetups.Add(BS); PA->UpdateBodySetupIndexMap(); PA->UpdateBoundsBodiesArray();
	GetMesh()->SetPhysicsAsset(PA, true);
	GetMesh()->SetSimulatePhysics(true); GetMesh()->BodyInstance.bSimulatePhysics = true; GetMesh()->SetCollisionProfileName(TEXT("Vehicle")); GetMesh()->SetEnableGravity(true); GetMesh()->SetLinearDamping(0.05f); GetMesh()->SetAngularDamping(0.5f);
	UChaosWheeledVehicleMovementComponent* M = CastChecked<UChaosWheeledVehicleMovementComponent>(GetVehicleMovement());
	M->WheelSetups.SetNum(4);
	const FName Bones[4] = { "Wheel_FL", "Wheel_FR", "Wheel_RL", "Wheel_RR" };
	for (int32 i = 0; i < 4; ++i) { M->WheelSetups[i].WheelClass = i < 2 ? TSubclassOf<UChaosVehicleWheel>(USFWheelFront::StaticClass()) : TSubclassOf<UChaosVehicleWheel>(USFWheelRear::StaticClass()); M->WheelSetups[i].BoneName = Bones[i]; }
	M->Mass = 1400.f; M->DragCoefficient = 0.32f; M->ChassisHeight = 145.f; M->ChassisWidth = 180.f;
	{ FRichCurve* TC = M->EngineSetup.TorqueCurve.GetRichCurve(); TC->Reset(); TC->AddKey(0.f, 0.45f); TC->AddKey(1500.f, 0.85f); TC->AddKey(3500.f, 1.f); TC->AddKey(5500.f, 0.8f); TC->AddKey(6500.f, 0.5f); }
	// Wheel bones can coincide at the origin after FBX import, which makes Chaos reject the springs: place wheels explicitly (cm, component space).
	const FVector WheelPos[4] = { FVector(135, -85, 34), FVector(135, 85, 34), FVector(-135, -85, 34), FVector(-135, 85, 34) };
	for (int32 i = 0; i < 4; ++i) M->WheelSetups[i].AdditionalOffset = WheelPos[i];
	M->EngineSetup.MaxTorque = 560.f; M->EngineSetup.MaxRPM = 6500.f;
	M->TransmissionSetup.bUseAutomaticGears = true;
	Arm = CreateDefaultSubobject<USpringArmComponent>(TEXT("Arm")); Arm->SetupAttachment(GetMesh()); Arm->TargetArmLength = 750.f; Arm->SocketOffset = FVector(0, 0, 220.f);
	Arm->bUsePawnControlRotation = false; Arm->bInheritPitch = false; Arm->bInheritRoll = false; Arm->bEnableCameraLag = true; Arm->CameraLagSpeed = 6.f;
	Cam = CreateDefaultSubobject<UCameraComponent>(TEXT("Cam")); Cam->SetupAttachment(Arm);
}
void ASFVehiclePawn::PossessedBy(AController* C) { Super::PossessedBy(C); FSFInput::Get(this).Apply(Cast<APlayerController>(C)); }
void ASFVehiclePawn::SetupPlayerInputComponent(UInputComponent* C) {
	Super::SetupPlayerInputComponent(C);
	if (auto* E = Cast<UEnhancedInputComponent>(C)) {
		FSFInput& I = FSFInput::Get(this);
		E->BindAction(I.Move, ETriggerEvent::Triggered, this, &ASFVehiclePawn::OnMove);
		E->BindAction(I.Move, ETriggerEvent::Completed, this, &ASFVehiclePawn::OnMove);
		E->BindActionValueLambda(I.Boost, ETriggerEvent::Triggered, [this](const FInputActionValue&){ GetVehicleMovementComponent()->SetHandbrakeInput(true); });
		E->BindActionValueLambda(I.Boost, ETriggerEvent::Completed, [this](const FInputActionValue&){ GetVehicleMovementComponent()->SetHandbrakeInput(false); });
	}
}
void ASFVehiclePawn::OnMove(const FInputActionValue& V) {
	const FVector2D M = V.Get<FVector2D>(); UChaosVehicleMovementComponent* VM = GetVehicleMovementComponent();
	VM->SetThrottleInput(FMath::Max(M.Y, 0.f)); VM->SetBrakeInput(FMath::Max(-M.Y, 0.f)); VM->SetSteeringInput(M.X);
}
