#include "SFInputSetup.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/PlayerController.h"
#include "Engine/LocalPlayer.h"

static UInputAction* MakeAction(UObject* O, const TCHAR* Name, EInputActionValueType T) {
	UInputAction* A = NewObject<UInputAction>(O, Name); A->ValueType = T; return A;
}

FSFInput& FSFInput::Get(UObject* Outer) {
	static FSFInput S; static TWeakObjectPtr<UInputMappingContext> Alive;
	if (S.Context && Alive.IsValid()) return S;
	UObject* O = GetTransientPackage();
	S.Move = MakeAction(O, TEXT("IA_Move"), EInputActionValueType::Axis2D);
	S.Look = MakeAction(O, TEXT("IA_Look"), EInputActionValueType::Axis2D);
	S.Jump = MakeAction(O, TEXT("IA_Jump"), EInputActionValueType::Boolean);
	S.Sprint = MakeAction(O, TEXT("IA_Sprint"), EInputActionValueType::Boolean);
	S.Up = MakeAction(O, TEXT("IA_Up"), EInputActionValueType::Boolean);
	S.Down = MakeAction(O, TEXT("IA_Down"), EInputActionValueType::Boolean);
	S.Boost = MakeAction(O, TEXT("IA_Boost"), EInputActionValueType::Boolean);
	for (UInputAction* A : {S.Move, S.Look, S.Jump, S.Sprint, S.Up, S.Down, S.Boost}) A->AddToRoot();
	UInputMappingContext* C = NewObject<UInputMappingContext>(O, TEXT("IMC_SF")); C->AddToRoot(); S.Context = C; Alive = C;

	auto Key = [&](UInputAction* A, FKey K, bool bNeg, bool bSwizzle) {
		FEnhancedActionKeyMapping& M = C->MapKey(A, K);
		if (bSwizzle) { auto* Sw = NewObject<UInputModifierSwizzleAxis>(C); Sw->Order = EInputAxisSwizzle::YXZ; M.Modifiers.Add(Sw); }
		if (bNeg) M.Modifiers.Add(NewObject<UInputModifierNegate>(C));
	};
	// Move: X = right, Y = forward
	Key(S.Move, EKeys::D, false, false); Key(S.Move, EKeys::A, true, false);
	Key(S.Move, EKeys::W, false, true);  Key(S.Move, EKeys::S, true, true);
	C->MapKey(S.Move, EKeys::Gamepad_Left2D);
	// Look: mouse, right stick (mouse Y is inverted for pitch-up-is-positive handled in pawn)
	C->MapKey(S.Look, EKeys::Mouse2D); C->MapKey(S.Look, EKeys::Gamepad_Right2D);
	C->MapKey(S.Jump, EKeys::SpaceBar); C->MapKey(S.Jump, EKeys::Gamepad_FaceButton_Bottom);   // PlayStation Cross
	C->MapKey(S.Sprint, EKeys::LeftShift); C->MapKey(S.Sprint, EKeys::Gamepad_LeftThumbstick);   // L3
	C->MapKey(S.Boost, EKeys::LeftShift); C->MapKey(S.Boost, EKeys::Gamepad_RightShoulder);
	C->MapKey(S.Up, EKeys::E); C->MapKey(S.Up, EKeys::Gamepad_RightTriggerAxis);
	C->MapKey(S.Down, EKeys::Q); C->MapKey(S.Down, EKeys::Gamepad_LeftTriggerAxis);
	return S;
}

void FSFInput::Apply(APlayerController* PC) const {
	if (!PC || !PC->GetLocalPlayer()) return;
	if (auto* Sub = ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PC->GetLocalPlayer())) {
		Sub->ClearAllMappings(); Sub->AddMappingContext(Context, 0);
	}
}
