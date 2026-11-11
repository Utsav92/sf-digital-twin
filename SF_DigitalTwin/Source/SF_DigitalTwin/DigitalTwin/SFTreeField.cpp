#include "SFTreeField.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInterface.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

ASFTreeField::ASFTreeField() {
	USceneComponent* R = CreateDefaultSubobject<USceneComponent>(TEXT("Root")); SetRootComponent(R);
	InstancesDir = FPaths::ConvertRelativePathToFull(FPaths::ProjectDir() / TEXT("../out/unreal/instances"));
}

void ASFTreeField::BeginPlay() {
	Super::BeginPlay();
	struct FSpecies { const TCHAR* Name; const TCHAR* Mesh; UHierarchicalInstancedStaticMeshComponent* C = nullptr; float NativeH = 1.f; };
	FSpecies Sp[3] = {
		{ TEXT("broadleaf"), TEXT("/Game/Props/SM_Tree_Broadleaf/SM_Tree_Broadleaf/StaticMeshes/SM_Tree_Broadleaf.SM_Tree_Broadleaf") },
		{ TEXT("conifer"),   TEXT("/Game/Props/SM_Tree_Conifer/SM_Tree_Conifer/StaticMeshes/SM_Tree_Conifer.SM_Tree_Conifer") },
		{ TEXT("palm"),      TEXT("/Game/Props/SM_Tree_Palm/SM_Tree_Palm/StaticMeshes/SM_Tree_Palm.SM_Tree_Palm") } };
	for (FSpecies& S : Sp) {
		UStaticMesh* M = LoadObject<UStaticMesh>(nullptr, S.Mesh);
		if (!M) { UE_LOG(LogTemp, Error, TEXT("SFTREES missing mesh %s"), S.Mesh); continue; }
		S.NativeH = FMath::Max(1.f, M->GetBounds().BoxExtent.Z * 2.f);
		S.C = NewObject<UHierarchicalInstancedStaticMeshComponent>(this, FName(*FString::Printf(TEXT("Trees_%s"), S.Name)));
		S.C->SetStaticMesh(M); S.C->SetMobility(EComponentMobility::Movable); S.C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		S.C->SetCastShadow(true); S.C->bAffectDistanceFieldLighting = true; S.C->bAffectDynamicIndirectLighting = true; S.C->SetCullDistances(0, 400000);
		for (int32 k = 0; k < S.C->GetNumMaterials(); ++k) { UMaterialInterface* MI = S.C->GetMaterial(k); FLinearColor LC(0,0,0,0); if (MI) MI->GetVectorParameterValue(FName("Color"), LC); UE_LOG(LogTemp, Display, TEXT("SFTREES %s slot %d mat %s color %.2f %.2f %.2f"), S.Name, k, MI ? *MI->GetName() : TEXT("none"), LC.R, LC.G, LC.B); }
		S.C->AttachToComponent(GetRootComponent(), FAttachmentTransformRules::KeepRelativeTransform); S.C->RegisterComponent();
	}
	TArray<FString> Files; IFileManager::Get().FindFiles(Files, *(InstancesDir / TEXT("*_trees.csv")), true, false);
	TMap<UHierarchicalInstancedStaticMeshComponent*, TArray<FTransform>> Batches;
	for (const FString& F : Files) {
		TArray<FString> Lines; if (!FFileHelper::LoadFileToStringArray(Lines, *(InstancesDir / F))) continue;
		for (int32 i = 1; i < Lines.Num(); ++i) {
			TArray<FString> C; Lines[i].ParseIntoArray(C, TEXT(","), false); if (C.Num() < 8) continue;
			for (FSpecies& S : Sp) if (S.C && C[7] == S.Name) {
				const float H = FCString::Atof(*C[6]) * 100.f, Rad = FCString::Atof(*C[4]) * 100.f;
				const float Sz = H / S.NativeH; // uniform fit to the surveyed height; crown radius only nudges width
				const float W = FMath::Clamp(Rad / FMath::Max(1.f, H * 0.35f), 0.7f, 1.5f) * Sz;
				Batches.FindOrAdd(S.C).Add(FTransform(FRotator(0, FCString::Atof(*C[3]), 0), FVector(FCString::Atof(*C[0]), FCString::Atof(*C[1]), FCString::Atof(*C[2])), FVector(W, W, Sz)));
				++TreeCount; break;
			}
		}
	}
	for (auto& B : Batches) B.Key->AddInstances(B.Value, false, true);
	UE_LOG(LogTemp, Display, TEXT("SFTREES placed %d trees from %d tile files"), TreeCount, Files.Num());
}
