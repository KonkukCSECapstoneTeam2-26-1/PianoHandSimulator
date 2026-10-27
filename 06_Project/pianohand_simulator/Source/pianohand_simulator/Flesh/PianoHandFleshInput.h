// Chaos Flesh -> PianoHand skinning adapter (04_Flesh).
//
// Game thread:  UPianoHandFleshInputComponent reads the Flesh surface positions every tick and publishes them.
// Render thread: PianoHandFlesh::AddFleshBlendPass mixes them into the skinned position buffer.
//
// The skinning deformer (03_Skinning) only needs one call, right after the skinning pass:
//     PianoHandFlesh::AddFleshBlendPass(GraphBuilder, MeshObject, PositionBuffer, Lod.GetNumVertices());

#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "RenderGraphFwd.h"
#include "PianoHandFleshInput.generated.h"

class FSkeletalMeshObject;
class USkeletalMeshComponent;
class UPrimitiveComponent;

namespace PianoHandFlesh
{
	/** Game thread. Hand the latest Flesh positions (render-vertex order, skinned component space) to the render thread. */
	PIANOHAND_SIMULATOR_API void Publish(const FSkeletalMeshObject* Key, TArray<FVector3f>&& Positions, float Blend);

	/** Game thread. Stop mixing for this mesh object. */
	PIANOHAND_SIMULATOR_API void Clear(const FSkeletalMeshObject* Key);

	/**
	 * Render thread. Adds a compute pass that does Position = lerp(Position, Flesh, Blend) in place.
	 * Returns false (and adds nothing) when no Flesh data is published for Key, the blend is 0,
	 * or the vertex count does not match.
	 */
	PIANOHAND_SIMULATOR_API bool AddFleshBlendPass(FRDGBuilder& GraphBuilder, const FSkeletalMeshObject* Key, FRDGBufferRef PositionBuffer, uint32 NumLodVertices);
}

/**
 * Put this on the actor that has both the Flesh component and the skinned (Dense) hand component.
 * It pulls the deformed surface from the Flesh component for the Dense mesh and feeds the skinning deformer.
 */
UCLASS(ClassGroup = (PianoHand), meta = (BlueprintSpawnableComponent))
class PIANOHAND_SIMULATOR_API UPianoHandFleshInputComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UPianoHandFleshInputComponent();

	/** Mix Flesh into the skinned result. Off = skinning only. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Flesh")
	bool bEnabled = true;

	/** 0 = skinning only, 1 = Flesh only. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Flesh", meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float Blend = 1.0f;

	/** The render mesh the Flesh asset was bound to with GenerateSurfaceBindings. The skinned component is found by this mesh name. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Flesh")
	FName TargetMeshName = TEXT("SKM_MH_Hand_R_Dense");

	/** Actor that holds the skinned hand (the component with the PianoHand skin deformer). Empty = this component's own actor. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Flesh")
	TObjectPtr<AActor> SkinnedActor;

	/** Log vertex count, space and rest-pose deviation once, when the first frame arrives. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Flesh")
	bool bLogDiagnostics = true;

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

private:
	bool FindComponents();
	void LogDiagnostics(const TArray<FVector3f>& FleshPositions) const;

	TWeakObjectPtr<USkeletalMeshComponent> Skinned;
	TWeakObjectPtr<UPrimitiveComponent> Flesh;
	const FSkeletalMeshObject* PublishedKey = nullptr;
	bool bDiagnosticsLogged = false;
	bool bWarnedMissing = false;
	bool bWarnedCount = false;
};
