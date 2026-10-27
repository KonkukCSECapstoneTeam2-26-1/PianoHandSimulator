#include "PianoHandFleshInput.h"
#include "../pianohand_simulator.h"

#include "Components/PrimitiveComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "GameFramework/Actor.h"
#include "Rendering/SkeletalMeshRenderData.h"
#include "Rendering/SkeletalMeshLODRenderData.h"
#include "Dataflow/Interfaces/DataflowInterfaceGeometryCachable.h"

#if WITH_EDITOR
#include "Rendering/SkeletalMeshModel.h"
#endif

#include "GlobalShader.h"
#include "ShaderParameterStruct.h"
#include "DataDrivenShaderPlatformInfo.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"

// ---------------------------------------------------------------------------
// Compute shader: Position = lerp(Position, Flesh, Blend), in place
// ---------------------------------------------------------------------------

class FPianoHandFleshBlendCS : public FGlobalShader
{
public:
	DECLARE_GLOBAL_SHADER(FPianoHandFleshBlendCS);
	SHADER_USE_PARAMETER_STRUCT(FPianoHandFleshBlendCS, FGlobalShader);

	static constexpr uint32 ThreadGroupSize = 64;

	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER(uint32, NumVertices)
		SHADER_PARAMETER(float, BlendWeight)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float3>, FleshPositions)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<float>, PositionBufferUAV)
	END_SHADER_PARAMETER_STRUCT()

	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters)
	{
		return IsFeatureLevelSupported(Parameters.Platform, ERHIFeatureLevel::SM5);
	}

	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment)
	{
		FGlobalShader::ModifyCompilationEnvironment(Parameters, OutEnvironment);
		OutEnvironment.SetDefine(TEXT("THREADGROUP_SIZE"), ThreadGroupSize);
	}
};

IMPLEMENT_GLOBAL_SHADER(FPianoHandFleshBlendCS, "/PianoHand/Private/PianoHandFleshBlend.usf", "BlendCS", SF_Compute);

// ---------------------------------------------------------------------------
// Game thread -> render thread hand-off, keyed by the skeletal mesh render object
// ---------------------------------------------------------------------------

namespace
{
	struct FFleshFrame
	{
		TArray<FVector3f> Positions;
		float Blend = 0.0f;
	};

	FCriticalSection GFleshMutex;
	TMap<const FSkeletalMeshObject*, TSharedPtr<FFleshFrame, ESPMode::ThreadSafe>> GFleshFrames;
}

namespace PianoHandFlesh
{
	void Publish(const FSkeletalMeshObject* Key, TArray<FVector3f>&& Positions, float Blend)
	{
		if (Key == nullptr)
		{
			return;
		}
		TSharedPtr<FFleshFrame, ESPMode::ThreadSafe> Frame = MakeShared<FFleshFrame, ESPMode::ThreadSafe>();
		Frame->Positions = MoveTemp(Positions);
		Frame->Blend = FMath::Clamp(Blend, 0.0f, 1.0f);

		FScopeLock Lock(&GFleshMutex);
		GFleshFrames.Add(Key, Frame);
	}

	void Clear(const FSkeletalMeshObject* Key)
	{
		FScopeLock Lock(&GFleshMutex);
		GFleshFrames.Remove(Key);
	}

	bool AddFleshBlendPass(FRDGBuilder& GraphBuilder, const FSkeletalMeshObject* Key, FRDGBufferRef PositionBuffer, uint32 NumLodVertices)
	{
		if (Key == nullptr || PositionBuffer == nullptr || NumLodVertices == 0)
		{
			return false;
		}

		TSharedPtr<FFleshFrame, ESPMode::ThreadSafe> Frame;
		{
			FScopeLock Lock(&GFleshMutex);
			if (const TSharedPtr<FFleshFrame, ESPMode::ThreadSafe>* Found = GFleshFrames.Find(Key))
			{
				Frame = *Found;
			}
		}
		if (!Frame.IsValid() || Frame->Blend <= 0.0f || (uint32)Frame->Positions.Num() != NumLodVertices)
		{
			return false;
		}

		FRDGBufferRef FleshBuffer = CreateStructuredBuffer(GraphBuilder, TEXT("PianoHandFleshPositions"), Frame->Positions);

		FPianoHandFleshBlendCS::FParameters* Params = GraphBuilder.AllocParameters<FPianoHandFleshBlendCS::FParameters>();
		Params->NumVertices = NumLodVertices;
		Params->BlendWeight = Frame->Blend;
		Params->FleshPositions = GraphBuilder.CreateSRV(FleshBuffer);
		Params->PositionBufferUAV = GraphBuilder.CreateUAV(PositionBuffer, PF_R32_FLOAT);

		TShaderMapRef<FPianoHandFleshBlendCS> ComputeShader(GetGlobalShaderMap(GMaxRHIFeatureLevel));
		FComputeShaderUtils::AddPass(
			GraphBuilder,
			RDG_EVENT_NAME("PianoHand.FleshBlend(%u verts)", NumLodVertices),
			ComputeShader,
			Params,
			FComputeShaderUtils::GetGroupCount(NumLodVertices, FPianoHandFleshBlendCS::ThreadGroupSize));
		return true;
	}
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

UPianoHandFleshInputComponent::UPianoHandFleshInputComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	// Flesh ticks late in the frame; read it after the skeletal mesh and Flesh are done.
	PrimaryComponentTick.TickGroup = TG_PostUpdateWork;
}

bool UPianoHandFleshInputComponent::FindComponents()
{
	AActor* Owner = GetOwner();
	if (Owner == nullptr)
	{
		return false;
	}

	Skinned.Reset();
	Flesh.Reset();

	TArray<USkeletalMeshComponent*> SkeletalComponents;
	(SkinnedActor != nullptr ? SkinnedActor.Get() : Owner)->GetComponents<USkeletalMeshComponent>(SkeletalComponents);
	for (USkeletalMeshComponent* Component : SkeletalComponents)
	{
		const USkeletalMesh* Mesh = Component->GetSkeletalMeshAsset();
		if (Mesh != nullptr && Mesh->GetFName() == TargetMeshName)
		{
			Skinned = Component;
			break;
		}
	}

	TArray<UPrimitiveComponent*> Primitives;
	Owner->GetComponents<UPrimitiveComponent>(Primitives);
	for (UPrimitiveComponent* Component : Primitives)
	{
		if (Cast<IDataflowGeometryCachable>(Component) != nullptr)
		{
			Flesh = Component;
			break;
		}
	}

	if (!Skinned.IsValid() || !Flesh.IsValid())
	{
		if (!bWarnedMissing)
		{
			bWarnedMissing = true;
			UE_LOG(LogPianoHand, Warning, TEXT("[FleshInput] %s: need both a skeletal mesh component with mesh '%s' (found: %s) and a Flesh component (found: %s) on the same actor."),
				*GetNameSafe(Owner), *TargetMeshName.ToString(), Skinned.IsValid() ? TEXT("yes") : TEXT("no"), Flesh.IsValid() ? TEXT("yes") : TEXT("no"));
		}
		return false;
	}

	// Read Flesh after it has been updated this frame.
	AddTickPrerequisiteComponent(Flesh.Get());
	bWarnedMissing = false;
	return true;
}

void UPianoHandFleshInputComponent::BeginPlay()
{
	Super::BeginPlay();
	bDiagnosticsLogged = false;
	bWarnedCount = false;
	FindComponents();
}

void UPianoHandFleshInputComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (PublishedKey != nullptr)
	{
		PianoHandFlesh::Clear(PublishedKey);
		PublishedKey = nullptr;
	}
	Super::EndPlay(EndPlayReason);
}

void UPianoHandFleshInputComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	if (!bEnabled)
	{
		if (PublishedKey != nullptr)
		{
			PianoHandFlesh::Clear(PublishedKey);
			PublishedKey = nullptr;
		}
		return;
	}

	if (!Skinned.IsValid() || !Flesh.IsValid())
	{
		if (!FindComponents())
		{
			return;
		}
	}

	USkeletalMeshComponent* SkinnedComponent = Skinned.Get();
	UPrimitiveComponent* FleshComponent = Flesh.Get();
	const USkeletalMesh* Mesh = SkinnedComponent->GetSkeletalMeshAsset();
	IDataflowGeometryCachable* Cachable = Cast<IDataflowGeometryCachable>(FleshComponent);
	if (Mesh == nullptr || Cachable == nullptr)
	{
		return;
	}

	// One position per render vertex of 'Mesh', in the order GenerateSurfaceBindings stored them (Flesh component space).
	TArray<FVector3f> Positions = Cachable->GetGeometryCachePositions(Mesh);
	if (Positions.IsEmpty())
	{
		return; // not simulated yet, or the Flesh asset has no bindings for this mesh
	}

	const FSkeletalMeshRenderData* RenderData = Mesh->GetResourceForRendering();
	const int32 NumRenderVertices = (RenderData != nullptr && RenderData->LODRenderData.Num() > 0) ? (int32)RenderData->LODRenderData[0].GetNumVertices() : 0;
	if (Positions.Num() != NumRenderVertices)
	{
		if (!bWarnedCount)
		{
			bWarnedCount = true;
			UE_LOG(LogPianoHand, Warning, TEXT("[FleshInput] '%s': Flesh returned %d positions but LOD0 has %d render vertices. Re-run GenerateSurfaceBindings with this mesh, or the mesh changed."),
				*Mesh->GetName(), Positions.Num(), NumRenderVertices);
		}
		return;
	}

	if (bLogDiagnostics && !bDiagnosticsLogged)
	{
		bDiagnosticsLogged = true;
		LogDiagnostics(Positions);
	}

	// Flesh component space -> skinned component space
	const FTransform FleshToSkinned = FleshComponent->GetComponentTransform().GetRelativeTransform(SkinnedComponent->GetComponentTransform());
	if (!FleshToSkinned.Equals(FTransform::Identity, 1e-4f))
	{
		for (FVector3f& P : Positions)
		{
			P = FVector3f(FleshToSkinned.TransformPosition(FVector(P)));
		}
	}

	const FSkeletalMeshObject* Key = SkinnedComponent->GetMeshObject();
	if (Key != PublishedKey && PublishedKey != nullptr)
	{
		PianoHandFlesh::Clear(PublishedKey); // render object was recreated
	}
	PublishedKey = Key;
	PianoHandFlesh::Publish(Key, MoveTemp(Positions), Blend);
}

void UPianoHandFleshInputComponent::LogDiagnostics(const TArray<FVector3f>& FleshPositions) const
{
	UE_LOG(LogPianoHand, Display, TEXT("[FleshInput] first frame: %d Flesh positions for '%s'"), FleshPositions.Num(), *TargetMeshName.ToString());

#if WITH_EDITOR
	const USkeletalMesh* Mesh = Skinned.IsValid() ? Skinned->GetSkeletalMeshAsset() : nullptr;
	const FSkeletalMeshModel* Model = Mesh ? Mesh->GetImportedModel() : nullptr;
	if (Model == nullptr || !Model->LODModels.IsValidIndex(0))
	{
		return;
	}

	// Compare against the mesh's own rest positions (same vertex order the Flesh bindings were built from).
	// Right after Play the animation is at its first frame (near rest), so a correct order and space gives small numbers.
	const FTransform FleshToSkinned = Flesh->GetComponentTransform().GetRelativeTransform(Skinned->GetComponentTransform());
	double SumRaw = 0.0, SumConv = 0.0;
	double MaxRaw = 0.0, MaxConv = 0.0;
	int32 Count = 0;
	for (const FSkelMeshSection& Section : Model->LODModels[0].Sections)
	{
		for (const FSoftSkinVertex& V : Section.SoftVertices)
		{
			if (Count >= FleshPositions.Num())
			{
				break;
			}
			const FVector Rest(V.Position);
			const FVector Raw(FleshPositions[Count]);
			const double DRaw = FVector::Dist(Rest, Raw);
			const double DConv = FVector::Dist(Rest, FleshToSkinned.TransformPosition(Raw));
			SumRaw += DRaw; SumConv += DConv;
			MaxRaw = FMath::Max(MaxRaw, DRaw); MaxConv = FMath::Max(MaxConv, DConv);
			++Count;
		}
	}
	if (Count > 0)
	{
		UE_LOG(LogPianoHand, Display, TEXT("[FleshInput] deviation from rest over %d verts: as-is mean %.3f max %.3f | converted mean %.3f max %.3f (cm)"),
			Count, SumRaw / Count, MaxRaw, SumConv / Count, MaxConv);
	}
#endif
}
