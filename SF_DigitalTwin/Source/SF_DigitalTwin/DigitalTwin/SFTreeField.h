#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SFTreeField.generated.h"

/** Loads the per-tile tree CSVs (out/unreal/instances) into one instanced-mesh component per species. */
UCLASS()
class SF_DIGITALTWIN_API ASFTreeField : public AActor {
	GENERATED_BODY()
public:
	ASFTreeField();
	virtual void BeginPlay() override;
	UPROPERTY(EditAnywhere) FString InstancesDir;
	UPROPERTY(VisibleAnywhere) int32 TreeCount = 0;
};
