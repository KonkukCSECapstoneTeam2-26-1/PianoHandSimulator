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
#include <atomic>
#include "Async/ParallelFor.h"
#include "ChaosFlesh/ChaosDeformableTetrahedralComponent.h"
#include "ChaosFlesh/FleshCollectionEngineUtility.h"
#include "GeometryCollection/Facades/CollectionTetrahedralBindingsFacade.h"

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

		// Render-thread status, logged every 300 calls: shows whether the pass really runs and why it is skipped.
		static std::atomic<uint32> CallCount{0}, RunCount{0}, NoFrameCount{0}, ZeroBlendCount{0}, MismatchCount{0};
		const uint32 Call = ++CallCount;
		const bool bNoFrame = !Frame.IsValid();
		const bool bZeroBlend = !bNoFrame && Frame->Blend <= 0.0f;
		const bool bMismatch = !bNoFrame && (uint32)Frame->Positions.Num() != NumLodVertices;
		if (bNoFrame) { ++NoFrameCount; } else if (bZeroBlend) { ++ZeroBlendCount; } else if (bMismatch) { ++MismatchCount; } else { ++RunCount; }
		if (Call % 300 == 1)
		{
			UE_LOG(LogPianoHand, Display, TEXT("[FleshInput] render pass: %u calls | ran %u | no data %u | blend 0 %u | count mismatch %u (frame %d vs LOD %u)"),
				Call, RunCount.load(), NoFrameCount.load(), ZeroBlendCount.load(), MismatchCount.load(), Frame.IsValid() ? Frame->Positions.Num() : -1, NumLodVertices);
		}
		if (bNoFrame || bZeroBlend || bMismatch)
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
// Fast read of the bound surface (same maths as ChaosFlesh::BoundSurfacePositions, but the bindings and evaluator are
// built once and the per-vertex evaluation runs on all cores)
// ---------------------------------------------------------------------------

struct FPianoHandFleshFastPath
{
	TUniquePtr<GeometryCollection::Facades::FTetrahedralBindings> Bindings;
	TUniquePtr<GeometryCollection::Facades::FTetrahedralBindings::Evaluator> Evaluator;
	TArray<Chaos::TVector<Chaos::FRealSingle, 3>> Current;
	int32 NumTetVertices = 0; // the simulated positions must have exactly this many entries before the bindings are evaluated
	bool bBuilt = false;
	bool bFailed = false;
};

namespace
{
	bool BuildFastPath(FPianoHandFleshFastPath& Path, const UDeformableTetrahedralComponent* Tet, const USkeletalMesh* Mesh)
	{
		const UFleshAsset* Rest = Tet->GetRestCollection();
		const FFleshCollection* FleshCollection = Rest ? Rest->GetCollection() : nullptr;
		const TManagedArray<FVector3f>* RestVertices = Rest ? Rest->FindPositions() : nullptr;
		if (FleshCollection == nullptr || RestVertices == nullptr)
		{
			return false;
		}
		const FName MeshId(ChaosFlesh::GetMeshId(Mesh, false));
		Path.Bindings = MakeUnique<GeometryCollection::Facades::FTetrahedralBindings>(static_cast<const FManagedArrayCollection&>(*FleshCollection));
		const int32 TetIndex = Path.Bindings->GetTetMeshIndex(MeshId, 0);
		if (TetIndex == INDEX_NONE || !Path.Bindings->ReadBindingsGroup(TetIndex, MeshId, 0))
		{
			return false;
		}
		Path.NumTetVertices = RestVertices->Num();
		Path.Evaluator = Path.Bindings->InitEvaluator(RestVertices);
		return Path.Evaluator.IsValid() && Path.Evaluator->IsValid();
	}

	bool FastRead(FPianoHandFleshFastPath& Path, const UDeformableTetrahedralComponent* Tet, TArray<FVector3f>& OutPositions)
	{
		const UFleshDynamicAsset* Dynamic = Tet->GetDynamicCollection();
		const TManagedArray<FVector3f>* Simulated = Dynamic ? Dynamic->FindPositions() : nullptr;
		if (Simulated == nullptr || !Path.Evaluator.IsValid())
		{
			return false;
		}
		if (Simulated->Num() != Path.NumTetVertices)
		{
			// The solver has not filled the positions yet (first frames after Play): nothing to read, and indexing would run off the array.
			OutPositions.Reset();
			return true;
		}
		Path.Current.SetNumUninitialized(Simulated->Num());
		for (int32 Index = 0; Index < Path.Current.Num(); ++Index)
		{
			Path.Current[Index] = Chaos::FVec3f((*Simulated)[Index]);
		}

		const int32 NumVertices = Path.Evaluator->NumVertices();
		OutPositions.SetNumUninitialized(NumVertices);
		constexpr int32 BatchSize = 2048;
		const int32 NumBatches = (NumVertices + BatchSize - 1) / BatchSize;
		ParallelFor(NumBatches, [&](int32 Batch)
		{
			const int32 End = FMath::Min((Batch + 1) * BatchSize, NumVertices);
			for (int32 Index = Batch * BatchSize; Index < End; ++Index)
			{
				OutPositions[Index] = Path.Evaluator->GetEmbeddedPosition(Index, Path.Current);
			}
		});
		return true;
	}
}

// ---------------------------------------------------------------------------
// Fingertip error probe (editor only): Flesh surface vs the skeletal mesh's own linear-blend skin
// ---------------------------------------------------------------------------

struct FPianoHandTipProbe
{
	using FInfluences = TArray<TPair<int32, float>, TInlineAllocator<4>>;
	struct FFinger
	{
		const TCHAR* Name = TEXT("");
		int32 TipBone = INDEX_NONE;
		TArray<int32> Verts;      // render vertices whose strongest bone is <finger>_03
		TArray<FVector3f> Rest;   // their rest positions
		TArray<FInfluences> Infl; // their skin weights
		int32 TipIdx = INDEX_NONE; // index into Verts of the vertex farthest from the _03 bone origin
		FVector PrevSkinTip = FVector::ZeroVector;
		bool bHasPrev = false;
		double SumTip = 0.0, MaxTip = 0.0, MinTip = 1e30, SumGroup = 0.0, SumAlong = 0.0, SumSpeed = 0.0;
		int32 Samples = 0;
		double MaxSpeed = 0.0, SpeedAtMaxTip = 0.0;               // peak tip speed; tip speed on the tick with the largest error
		double MoveSumTip = 0.0, MoveSumAlong = 0.0; int32 MoveSamples = 0; // only ticks with speed >= MoveSpeedCmPerSec
	};
	static constexpr double MoveSpeedCmPerSec = 10.0;
	FFinger Fingers[5];
	bool bBuilt = false;
	int32 Ticks = 0;
};

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
	const double TickStart = FPlatformTime::Seconds();
	TArray<FVector3f> Positions;
	bool bReadFast = false;
	if (bFastRead)
	{
		if (!FastPath.IsValid())
		{
			FastPath = MakeShared<FPianoHandFleshFastPath>();
		}
		const UDeformableTetrahedralComponent* Tet = Cast<UDeformableTetrahedralComponent>(FleshComponent);
		if (!FastPath->bBuilt && !FastPath->bFailed && Tet != nullptr)
		{
			FastPath->bBuilt = BuildFastPath(*FastPath, Tet, Mesh);
			FastPath->bFailed = !FastPath->bBuilt;
			UE_LOG(LogPianoHand, Display, TEXT("[FleshInput] fast read %s"), FastPath->bBuilt ? TEXT("ready (cached bindings, parallel)") : TEXT("unavailable, using Flesh's own call"));
		}
		if (FastPath->bBuilt)
		{
			bReadFast = FastRead(*FastPath, Tet, Positions);
		}
	}
	if (!bReadFast)
	{
		Positions = Cachable->GetGeometryCachePositions(Mesh);
	}
	const double ReadSeconds = FPlatformTime::Seconds() - TickStart;
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

	if (bLogTipError)
	{
		MeasureTipError(Positions, DeltaTime);
	}

	// Visibility test: shift the Flesh result up (skinned component +Z) so Blend > 0 is obvious on screen.
	if (!FMath::IsNearlyZero(DebugLiftCm))
	{
		for (FVector3f& P : Positions)
		{
			P.Z += DebugLiftCm;
		}
	}

	const FSkeletalMeshObject* Key = SkinnedComponent->GetMeshObject();
	if (Key != PublishedKey && PublishedKey != nullptr)
	{
		PianoHandFlesh::Clear(PublishedKey); // render object was recreated
	}
	PublishedKey = Key;
	PianoHandFlesh::Publish(Key, MoveTemp(Positions), Blend);

	// Cost of this adapter on the game thread, logged every 300 ticks next to the frame time (so FPS is visible too).
	TimingTicks++;
	TimingReadSeconds += ReadSeconds;
	TimingTotalSeconds += FPlatformTime::Seconds() - TickStart;
	TimingFrameSeconds += DeltaTime;
	if (TimingTicks >= 300)
	{
		UE_LOG(LogPianoHand, Display, TEXT("[FleshInput] game thread, avg over %d ticks: read Flesh %.2f ms | whole tick %.2f ms | frame %.1f ms (%.1f FPS)"),
			TimingTicks, 1000.0 * TimingReadSeconds / TimingTicks, 1000.0 * TimingTotalSeconds / TimingTicks,
			1000.0 * TimingFrameSeconds / TimingTicks, TimingFrameSeconds > 0.0 ? TimingTicks / TimingFrameSeconds : 0.0);
		TimingTicks = 0;
		TimingReadSeconds = TimingTotalSeconds = TimingFrameSeconds = 0.0;
	}
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

void UPianoHandFleshInputComponent::MeasureTipError(const TArray<FVector3f>& FleshPositions, float DeltaTime)
{
#if WITH_EDITOR
	USkeletalMeshComponent* SkinnedComponent = Skinned.Get();
	const USkeletalMesh* Mesh = SkinnedComponent ? SkinnedComponent->GetSkeletalMeshAsset() : nullptr;
	const FSkeletalMeshModel* Model = Mesh ? Mesh->GetImportedModel() : nullptr;
	if (Model == nullptr || !Model->LODModels.IsValidIndex(0) || DeltaTime <= 0.0f)
	{
		return;
	}
	const TArray<FTransform>& CompSpace = SkinnedComponent->GetComponentSpaceTransforms();
	const TArray<FMatrix44f>& RefInv = Mesh->GetRefBasesInvMatrix();
	if (CompSpace.Num() == 0 || CompSpace.Num() != RefInv.Num())
	{
		return;
	}

	if (!TipProbe.IsValid())
	{
		TipProbe = MakeShared<FPianoHandTipProbe>();
	}
	FPianoHandTipProbe& Probe = *TipProbe;

	if (!Probe.bBuilt)
	{
		Probe.bBuilt = true;
		static const TCHAR* FingerNames[5] = { TEXT("thumb"), TEXT("index"), TEXT("middle"), TEXT("ring"), TEXT("pinky") };
		for (int32 F = 0; F < 5; ++F)
		{
			Probe.Fingers[F].Name = FingerNames[F];
			Probe.Fingers[F].TipBone = Mesh->GetRefSkeleton().FindBoneIndex(FName(*FString::Printf(TEXT("%s_03_r"), FingerNames[F])));
		}

		// Group render vertices by the fingertip bone that influences them most.
		int32 Count = 0;
		for (const FSkelMeshSection& Section : Model->LODModels[0].Sections)
		{
			for (const FSoftSkinVertex& V : Section.SoftVertices)
			{
				int32 BestBone = INDEX_NONE;
				uint16 BestWeight = 0;
				for (int32 I = 0; I < MAX_TOTAL_INFLUENCES; ++I)
				{
					if (V.InfluenceWeights[I] > BestWeight && Section.BoneMap.IsValidIndex(V.InfluenceBones[I]))
					{
						BestWeight = V.InfluenceWeights[I];
						BestBone = Section.BoneMap[V.InfluenceBones[I]];
					}
				}
				for (FPianoHandTipProbe::FFinger& Finger : Probe.Fingers)
				{
					if (BestBone != INDEX_NONE && BestBone == Finger.TipBone)
					{
						Finger.Verts.Add(Count);
						Finger.Rest.Add(V.Position);
						FPianoHandTipProbe::FInfluences List;
						for (int32 I = 0; I < MAX_TOTAL_INFLUENCES; ++I)
						{
							if (V.InfluenceWeights[I] > 0 && Section.BoneMap.IsValidIndex(V.InfluenceBones[I]))
							{
								List.Emplace(Section.BoneMap[V.InfluenceBones[I]], V.InfluenceWeights[I] / 65535.0f);
							}
						}
						Finger.Infl.Add(MoveTemp(List));
						break;
					}
				}
				++Count;
			}
		}
		for (FPianoHandTipProbe::FFinger& Finger : Probe.Fingers)
		{
			if (Finger.TipBone == INDEX_NONE || Finger.Verts.IsEmpty()) { continue; }
			const FVector Origin = FVector(RefInv[Finger.TipBone].Inverse().GetOrigin());
			double Far = -1.0;
			for (int32 I = 0; I < Finger.Verts.Num(); ++I)
			{
				const double D = FVector::DistSquared(FVector(Finger.Rest[I]), Origin);
				if (D > Far) { Far = D; Finger.TipIdx = I; }
			}
		}
		UE_LOG(LogPianoHand, Display, TEXT("[FleshTip] probe ready. Vertices per fingertip bone: thumb %d index %d middle %d ring %d pinky %d. Distance = Flesh surface to the skeletal mesh's linear-blend skin (cm); 'along' = part of the offset along the tip's motion (negative = Flesh behind)."),
			Probe.Fingers[0].Verts.Num(), Probe.Fingers[1].Verts.Num(), Probe.Fingers[2].Verts.Num(), Probe.Fingers[3].Verts.Num(), Probe.Fingers[4].Verts.Num());
	}

	// skin matrix per bone: ref pose -> current component space
	TArray<FMatrix44f> SkinMatrices;
	SkinMatrices.SetNumUninitialized(CompSpace.Num());
	for (int32 B = 0; B < CompSpace.Num(); ++B)
	{
		SkinMatrices[B] = RefInv[B] * FMatrix44f(CompSpace[B].ToMatrixWithScale());
	}

	for (FPianoHandTipProbe::FFinger& Finger : Probe.Fingers)
	{
		if (Finger.TipIdx == INDEX_NONE) { continue; }

		double GroupSum = 0.0;
		for (int32 I = 0; I < Finger.Verts.Num(); ++I)
		{
			FVector Skin = FVector::ZeroVector;
			for (const TPair<int32, float>& Influence : Finger.Infl[I])
			{
				Skin += FVector(SkinMatrices[Influence.Key].TransformPosition(Finger.Rest[I]) * Influence.Value);
			}
			GroupSum += FVector::Dist(Skin, FVector(FleshPositions[Finger.Verts[I]]));
		}
		Finger.SumGroup += GroupSum / Finger.Verts.Num();

		FVector SkinTip = FVector::ZeroVector;
		for (const TPair<int32, float>& Influence : Finger.Infl[Finger.TipIdx])
		{
			SkinTip += FVector(SkinMatrices[Influence.Key].TransformPosition(Finger.Rest[Finger.TipIdx]) * Influence.Value);
		}
		const FVector Offset = FVector(FleshPositions[Finger.Verts[Finger.TipIdx]]) - SkinTip;
		const double Dist = Offset.Size();
		Finger.SumTip += Dist;
		Finger.MinTip = FMath::Min(Finger.MinTip, Dist);
		double Speed = 0.0;
		if (Finger.bHasPrev)
		{
			const FVector Velocity = (SkinTip - Finger.PrevSkinTip) / DeltaTime;
			Speed = Velocity.Size();
			Finger.SumSpeed += Speed;
			Finger.MaxSpeed = FMath::Max(Finger.MaxSpeed, Speed);
			if (Speed > 1.0) // cm/s; below this the direction is noise
			{
				const double Along = FVector::DotProduct(Offset, Velocity / Speed);
				Finger.SumAlong += Along;
				if (Speed >= FPianoHandTipProbe::MoveSpeedCmPerSec)
				{
					Finger.MoveSumTip += Dist;
					Finger.MoveSumAlong += Along;
					++Finger.MoveSamples;
				}
			}
		}
		if (Dist > Finger.MaxTip)
		{
			Finger.MaxTip = Dist;
			Finger.SpeedAtMaxTip = Speed;
		}
		Finger.PrevSkinTip = SkinTip;
		Finger.bHasPrev = true;
		++Finger.Samples;
	}

	if (++Probe.Ticks >= TipLogInterval)
	{
		FString Line;
		for (FPianoHandTipProbe::FFinger& Finger : Probe.Fingers)
		{
			if (Finger.Samples > 0)
			{
				Line += FString::Printf(TEXT(" | %s tip %.2f (min %.2f max %.2f @%.0fcm/s) group %.2f speed avg %.1f max %.1f | moving(%d) tip %.2f along %+.2f"), Finger.Name,
					Finger.SumTip / Finger.Samples, Finger.MinTip, Finger.MaxTip, Finger.SpeedAtMaxTip, Finger.SumGroup / Finger.Samples,
					Finger.SumSpeed / Finger.Samples, Finger.MaxSpeed,
					Finger.MoveSamples, Finger.MoveSamples ? Finger.MoveSumTip / Finger.MoveSamples : 0.0, Finger.MoveSamples ? Finger.MoveSumAlong / Finger.MoveSamples : 0.0);
			}
			Finger.SumTip = Finger.MaxTip = Finger.SumGroup = Finger.SumAlong = Finger.SumSpeed = 0.0;
			Finger.MaxSpeed = Finger.SpeedAtMaxTip = Finger.MoveSumTip = Finger.MoveSumAlong = 0.0;
			Finger.MinTip = 1e30;
			Finger.Samples = Finger.MoveSamples = 0;
		}
		UE_LOG(LogPianoHand, Display, TEXT("[FleshTip] avg over %d ticks, cm (tip = farthest vertex, @ = tip speed on its worst tick, group = mean of all vertices on the tip bone, speed in cm/s, moving = ticks with speed >= 10 cm/s)%s"), Probe.Ticks, *Line);
		Probe.Ticks = 0;
	}
#endif
}
