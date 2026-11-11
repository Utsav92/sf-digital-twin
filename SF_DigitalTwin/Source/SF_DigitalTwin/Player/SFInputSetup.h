#pragma once
#include "CoreMinimal.h"
class UInputAction; class UInputMappingContext; class APlayerController;

/** Builds Enhanced Input assets at runtime (no editor assets needed): WASD/mouse/gamepad for walking and flying. */
struct FSFInput {
	UInputAction *Move=nullptr, *Look=nullptr, *Jump=nullptr, *Sprint=nullptr, *Up=nullptr, *Down=nullptr, *Boost=nullptr;
	UInputMappingContext* Context=nullptr;
	static FSFInput& Get(UObject* Outer);
	void Apply(APlayerController* PC) const;
};
