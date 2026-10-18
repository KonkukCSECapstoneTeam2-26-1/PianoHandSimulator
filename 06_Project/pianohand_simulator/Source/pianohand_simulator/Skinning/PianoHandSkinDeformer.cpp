#include "PianoHandSkinDeformer.h"
#include "../pianohand_simulator.h"

#include "Components/SkinnedMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "SkeletalRenderPublic.h"
#include "SkeletalMeshDeformerHelpers.h"
#include "Rendering/SkeletalMeshRenderData.h"
#include "Rendering/SkeletalMeshLODRenderData.h"
#include "Rendering/SkinWeightVertexBuffer.h"
#include "Rendering/MultiSizeIndexContainer.h"
#include "RawIndexBuffer.h"
#include "GPUSkinPublicDefs.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "RenderingThread.h"
#include "DataDrivenShaderPlatformInfo.h"
#include "RHIStaticStates.h"
#include "TextureResource.h"
#include "ReferenceSkeleton.h"
#include "Engine/SkinnedAsset.h"
#include "Rendering/PositionVertexBuffer.h"
#include "Rendering/SkinWeightVertexBuffer.h"

namespace PianoHandImplicit
{
	void Build(const USkinnedMeshComponent* Component, const FPianoHandImplicitBuildSettings& Settings, FPianoHandImplicitData& Out);
	bool BuildWeldMap(const FSkeletalMeshLODRenderData& Lod, TArray<uint32>& OutCanon, TArray<uint32>& OutWeldedIndices, int32& OutNumTwins);
}

namespace PianoHandProportions
{
	void BuildBoneScales(const USkinnedMeshComponent* Component, const FPianoHandProportions& P, TArray<FVector3f>& OutScale);
	void BuildCapsules(const USkinnedMeshComponent* Component, TArray<FPianoHandBoneCapsule>& Out);
	static void RefPoseComponentSpace(const USkinnedAsset* Asset, TArray<FTransform>& Out);
}

// ---------------------------------------------------------------------------
// Compute shader
// ---------------------------------------------------------------------------

IMPLEMENT_GLOBAL_SHADER(FPianoHandSkinDeformerCS, "/PianoHand/Private/CustomSkinningDeformer.usf", "DeformCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FPianoHandTensionAccumulateCS, "/PianoHand/Private/CustomSkinningTension.usf", "AccumulateCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FPianoHandTensionResolveCS, "/PianoHand/Private/CustomSkinningTension.usf", "ResolveCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FPianoHandTensorSmoothScatterCS, "/PianoHand/Private/CustomSkinningTension.usf", "SmoothScatterCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FPianoHandTensorSmoothResolveCS, "/PianoHand/Private/CustomSkinningTension.usf", "SmoothResolveCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FPianoHandDetailDisplaceCS, "/PianoHand/Private/CustomSkinningDetail.usf", "DisplaceCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FPianoHandNormalAccumulateCS, "/PianoHand/Private/CustomSkinningDetail.usf", "NormalAccumulateCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FPianoHandNormalResolveCS, "/PianoHand/Private/CustomSkinningDetail.usf", "NormalResolveCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FPianoHandImplicitProjectCS, "/PianoHand/Private/ImplicitSkinning.usf", "ImplicitProjectCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FPianoHandImplicitRelaxCS, "/PianoHand/Private/ImplicitSkinning.usf", "ImplicitRelaxCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FPianoHandImplicitBetaCS, "/PianoHand/Private/ImplicitSkinning.usf", "ImplicitBetaCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FPianoHandImplicitSmoothCS, "/PianoHand/Private/ImplicitSkinning.usf", "ImplicitSmoothCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FPianoHandImplicitAdvectCS, "/PianoHand/Private/ImplicitSkinning.usf", "ImplicitAdvectCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FPianoHandImplicitDebugCS, "/PianoHand/Private/ImplicitSkinning.usf", "ImplicitDebugCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FPianoHandImplicitFinalizeCS, "/PianoHand/Private/ImplicitSkinning.usf", "ImplicitFinalizeCS", SF_Compute);

#define PH_IMPLICIT_SHADER_BOILERPLATE(ClassName) \
bool ClassName::ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters) \
{ \
	return IsFeatureLevelSupported(Parameters.Platform, ERHIFeatureLevel::SM5); \
} \
void ClassName::ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment) \
{ \
	FGlobalShader::ModifyCompilationEnvironment(Parameters, OutEnvironment); \
	OutEnvironment.SetDefine(TEXT("THREADGROUP_SIZE"), ThreadGroupSize); \
}
PH_IMPLICIT_SHADER_BOILERPLATE(FPianoHandImplicitProjectCS)
PH_IMPLICIT_SHADER_BOILERPLATE(FPianoHandImplicitRelaxCS)
PH_IMPLICIT_SHADER_BOILERPLATE(FPianoHandImplicitBetaCS)
PH_IMPLICIT_SHADER_BOILERPLATE(FPianoHandImplicitSmoothCS)
PH_IMPLICIT_SHADER_BOILERPLATE(FPianoHandImplicitAdvectCS)
PH_IMPLICIT_SHADER_BOILERPLATE(FPianoHandImplicitDebugCS)
PH_IMPLICIT_SHADER_BOILERPLATE(FPianoHandImplicitFinalizeCS)
#undef PH_IMPLICIT_SHADER_BOILERPLATE

bool FPianoHandSkinDeformerCS::ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters)
{
	return IsFeatureLevelSupported(Parameters.Platform, ERHIFeatureLevel::SM5);
}

void FPianoHandSkinDeformerCS::ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment)
{
	FGlobalShader::ModifyCompilationEnvironment(Parameters, OutEnvironment);
	OutEnvironment.SetDefine(TEXT("THREADGROUP_SIZE"), ThreadGroupSize);
	OutEnvironment.SetDefine(TEXT("GPUSKIN_UNLIMITED_BONE_INFLUENCE"), 0);
}

bool FPianoHandTensionAccumulateCS::ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters)
{
	return IsFeatureLevelSupported(Parameters.Platform, ERHIFeatureLevel::SM5);
}

void FPianoHandTensionAccumulateCS::ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment)
{
	FGlobalShader::ModifyCompilationEnvironment(Parameters, OutEnvironment);
	OutEnvironment.SetDefine(TEXT("THREADGROUP_SIZE"), ThreadGroupSize);
}

bool FPianoHandTensionResolveCS::ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters)
{
	return IsFeatureLevelSupported(Parameters.Platform, ERHIFeatureLevel::SM5);
}

void FPianoHandTensionResolveCS::ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment)
{
	FGlobalShader::ModifyCompilationEnvironment(Parameters, OutEnvironment);
	OutEnvironment.SetDefine(TEXT("THREADGROUP_SIZE"), ThreadGroupSize);
}

bool FPianoHandTensorSmoothScatterCS::ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters)
{
	return IsFeatureLevelSupported(Parameters.Platform, ERHIFeatureLevel::SM5);
}
void FPianoHandTensorSmoothScatterCS::ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment)
{
	FGlobalShader::ModifyCompilationEnvironment(Parameters, OutEnvironment);
	OutEnvironment.SetDefine(TEXT("THREADGROUP_SIZE"), ThreadGroupSize);
}
bool FPianoHandTensorSmoothResolveCS::ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters)
{
	return IsFeatureLevelSupported(Parameters.Platform, ERHIFeatureLevel::SM5);
}
void FPianoHandTensorSmoothResolveCS::ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment)
{
	FGlobalShader::ModifyCompilationEnvironment(Parameters, OutEnvironment);
	OutEnvironment.SetDefine(TEXT("THREADGROUP_SIZE"), ThreadGroupSize);
}

bool FPianoHandDetailDisplaceCS::ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters)
{
	return IsFeatureLevelSupported(Parameters.Platform, ERHIFeatureLevel::SM5);
}

void FPianoHandDetailDisplaceCS::ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment)
{
	FGlobalShader::ModifyCompilationEnvironment(Parameters, OutEnvironment);
	OutEnvironment.SetDefine(TEXT("THREADGROUP_SIZE"), ThreadGroupSize);
	OutEnvironment.SetDefine(TEXT("GPUSKIN_UNLIMITED_BONE_INFLUENCE"), 0);
}

bool FPianoHandNormalAccumulateCS::ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters)
{
	return IsFeatureLevelSupported(Parameters.Platform, ERHIFeatureLevel::SM5);
}

void FPianoHandNormalAccumulateCS::ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment)
{
	FGlobalShader::ModifyCompilationEnvironment(Parameters, OutEnvironment);
	OutEnvironment.SetDefine(TEXT("THREADGROUP_SIZE"), ThreadGroupSize);
}

bool FPianoHandNormalResolveCS::ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters)
{
	return IsFeatureLevelSupported(Parameters.Platform, ERHIFeatureLevel::SM5);
}

void FPianoHandNormalResolveCS::ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment)
{
	FGlobalShader::ModifyCompilationEnvironment(Parameters, OutEnvironment);
	OutEnvironment.SetDefine(TEXT("THREADGROUP_SIZE"), ThreadGroupSize);
}

// ---------------------------------------------------------------------------
// Render thread execution
// ---------------------------------------------------------------------------

namespace PianoHandSkinDeformer
{
	/** Runs the skinning kernel for every enabled section of the current LOD. Returns false if the deformer could not run (caller triggers the fallback). */
	/** Section-local copy of a per-bone table, in Section.BoneMap order (weight-stream bone indices are section-local). */
	static TArray<FSkinBoneTransform> SectionTable(const FSkelMeshRenderSection& Section, const TArray<FSkinBoneTransform>& All)
	{
		TArray<FSkinBoneTransform> Out;
		Out.SetNumUninitialized(FMath::Max(Section.BoneMap.Num(), 1));
		for (int32 i = 0; i < Section.BoneMap.Num(); ++i)
		{
			const int32 BoneIndex = Section.BoneMap[i];
			Out[i] = All.IsValidIndex(BoneIndex) ? All[BoneIndex] : FSkinBoneTransform::FromMatrix(FMatrix44f::Identity);
		}
		if (Section.BoneMap.Num() == 0)
		{
			Out[0] = FSkinBoneTransform::FromMatrix(FMatrix44f::Identity);
		}
		return Out;
	}

	static bool Execute_RenderThread(
		FRHICommandListImmediate& RHICmdList,
		FSkeletalMeshObject* MeshObject,
		const TArray<FSkinBoneTransform>& AllBones,
		const TArray<FSkinBoneTransform>& AllBoneNormals,
		const TArray<FSkinBoneTransform>& AllRefInverses,
		const TArray<FSkinBoneTransform>& AllRestBones,
		const TArray<FSkinBoneTransform>& AllRestBoneNormals,
		const TArray<FPianoHandBoneCapsule>& AllCapsules,
		const TArray<FSkinBoneTransform>& PrimInverses,
		const TArray<FSkinBoneTransform>& PrimForward,
		const TArray<float>& PairBend,
		TSharedPtr<const FPianoHandImplicitData, ESPMode::ThreadSafe> Implicit,
		const FPianoHandDeformerFrameParams& Params,
		FPianoHandDeformerRenderState& State,
		FName OwnerName)
	{
		check(IsInRenderingThread());

		// FSkeletalMeshDeformerHelpers casts to FSkeletalMeshObjectGPUSkin, so only take the GPU skin path.
		if (MeshObject == nullptr || MeshObject->IsCPUSkinned() || !MeshObject->IsGPUSkinMesh())
		{
			return false;
		}

		// No dynamic data yet -> the render state is still being (re)created this frame.
		if (!MeshObject->HaveValidDynamicData())
		{
			return false;
		}

		const int32 LodIndex = MeshObject->GetLOD();
		const FSkeletalMeshRenderData& RenderData = MeshObject->GetSkeletalMeshRenderData();
		if (!RenderData.IsInitialized() || !RenderData.LODRenderData.IsValidIndex(LodIndex))
		{
			return false;
		}

		// LOD streaming guard. Per-LOD render resources (the GPU skin vertex factories) only exist for
		// LODs at or above CurrentFirstLODIdx; PendingFirstLODIdx is where streaming is heading. Dispatching
		// on a LOD outside that range makes FSkeletalMeshDeformerHelpers index an empty vertex-factory array
		// and assert. Skipping the frame just falls back to engine skinning, which is the correct behaviour
		// while the mesh streams in.
		const int32 FirstReadyLod = FMath::Max<int32>(RenderData.CurrentFirstLODIdx, RenderData.GetPendingFirstLODIdx(0));
		if (FirstReadyLod == INDEX_NONE || LodIndex < FirstReadyLod)
		{
			return false;
		}

		const FSkeletalMeshLODRenderData& Lod = RenderData.LODRenderData[LodIndex];
		if (Lod.GetNumVertices() == 0 || Lod.RenderSections.Num() == 0)
		{
			return false;
		}

		if (FSkeletalMeshDeformerHelpers::GetIndexOfFirstAvailableSection(MeshObject, LodIndex) == INDEX_NONE)
		{
			return false;
		}

		const FSkinWeightVertexBuffer* WeightBuffer = Lod.GetSkinWeightVertexBuffer();
		if (WeightBuffer == nullptr)
		{
			return false;
		}
		if (WeightBuffer->GetBoneInfluenceType() == GPUSkinBoneInfluenceType::UnlimitedBoneInfluence)
		{
			if (!State.bLoggedUnsupported)
			{
				State.bLoggedUnsupported = true;
				UE_LOG(LogPianoHand, Warning, TEXT("[SkinDeformer] %s: unlimited bone influences are not supported yet, falling back to engine skinning."), *OwnerName.ToString());
			}
			return false;
		}

		FRHIShaderResourceView* PositionSRV = Lod.StaticVertexBuffers.PositionVertexBuffer.GetSRV();
		FRHIShaderResourceView* TangentSRV = Lod.StaticVertexBuffers.StaticMeshVertexBuffer.GetTangentsSRV();
		FRHIShaderResourceView* WeightSRV = WeightBuffer->GetDataVertexBuffer() ? WeightBuffer->GetDataVertexBuffer()->GetSRV() : nullptr;
		if (PositionSRV == nullptr || TangentSRV == nullptr || WeightSRV == nullptr)
		{
			return false;
		}

		const uint32 NumBoneInfluences = WeightBuffer->GetMaxBoneInfluences();
		const uint32 InputWeightStride = WeightBuffer->GetConstantInfluencesVertexStride();
		const bool bIndex16 = WeightBuffer->Use16BitBoneIndex();
		const bool bWeight16 = WeightBuffer->Use16BitBoneWeight();

		const EPianoHandSkinMode Mode = Params.Mode;

		if (!State.bLoggedLayout)
		{
			State.bLoggedLayout = true;
			UE_LOG(LogPianoHand, Display, TEXT("[SkinDeformer] %s: LOD%d verts=%u sections=%d influences=%u stride=%u index16=%d weight16=%d bones=%d mode=%s"),
				*OwnerName.ToString(), LodIndex, Lod.GetNumVertices(), Lod.RenderSections.Num(), NumBoneInfluences, InputWeightStride,
				bIndex16 ? 1 : 0, bWeight16 ? 1 : 0, AllBones.Num(), Mode == EPianoHandSkinMode::LinearBlend ? TEXT("LBS") : TEXT("DQS"));
		}

		FRDGBuilder GraphBuilder(RHICmdList, RDG_EVENT_NAME("PianoHandSkinDeformer(%s)", *OwnerName.ToString()));
		FRDGExternalAccessQueue ExternalAccessQueue;

		// Avoid using the previous position buffer from another LOD for motion vectors.
		const bool bInvalidatePreviousPosition = (LodIndex != State.LastLodIndex);
		State.LastLodIndex = LodIndex;

		FRDGBufferRef PositionBuffer = FSkeletalMeshDeformerHelpers::AllocateVertexFactoryPositionBuffer(GraphBuilder, ExternalAccessQueue, MeshObject, LodIndex, TEXT("PianoHandSkinDeformerPosition"));
		FRDGBufferRef TangentBuffer = FSkeletalMeshDeformerHelpers::AllocateVertexFactoryTangentBuffer(GraphBuilder, ExternalAccessQueue, MeshObject, LodIndex, TEXT("PianoHandSkinDeformerTangent"));
		if (PositionBuffer == nullptr || TangentBuffer == nullptr)
		{
			ExternalAccessQueue.Submit(GraphBuilder);
			GraphBuilder.Execute();
			return false;
		}

		// Phase 2: tension needs the LOD index buffer as an SRV (created by the engine on SM5+ / passthrough platforms).
		FRHIShaderResourceView* IndexSRV = nullptr;
		FRDGBufferRef ColorBuffer = nullptr;
		bool bComputeTension = Params.bComputeTension;
		{
			const FRawStaticIndexBuffer16or32Interface* IndexBuffer = Lod.MultiSizeIndexContainer.IsIndexBufferValid() ? Lod.MultiSizeIndexContainer.GetIndexBuffer() : nullptr;
			IndexSRV = IndexBuffer ? IndexBuffer->GetSRV() : nullptr;
		}
		// 10-18: every triangle-gather pass runs on the WELDED index buffer (UV-seam twins -> canonical vertex) and
		// every per-vertex resolve reads the canonical vertex's accumulation, so the two copies of a seam vertex
		// get the same strain, normal and displacement. Without this the seams along the finger sides opened
		// into hairline cracks (detail pass) and see-through slivers (implicit relaxation + smoothing).
		FRDGBufferSRVRef WeldIndexSRV = nullptr;
		FRDGBufferSRVRef WeldCanonSRV = nullptr;
		{
			const uint32 NumLodVertsForWeld = Lod.GetNumVertices();
			if (!State.WeldCanon.IsValid() || !State.WeldIndices.IsValid() || State.WeldNumVerts != NumLodVertsForWeld)
			{
				TArray<uint32> Canon, Welded;
				int32 NumTwins = 0;
				if (PianoHandImplicit::BuildWeldMap(Lod, Canon, Welded, NumTwins) && Canon.Num() == (int32)NumLodVertsForWeld && Welded.Num() >= 3)
				{
					FRDGBufferRef CanonBuf = CreateStructuredBuffer(GraphBuilder, TEXT("PianoHandWeldCanon"), Canon);
					FRDGBufferRef IdxBuf = CreateVertexBuffer(GraphBuilder, TEXT("PianoHandWeldIndices"), FRDGBufferDesc::CreateBufferDesc(sizeof(uint32), Welded.Num()), Welded.GetData(), Welded.Num() * sizeof(uint32));
					GraphBuilder.QueueBufferExtraction(CanonBuf, &State.WeldCanon);
					GraphBuilder.QueueBufferExtraction(IdxBuf, &State.WeldIndices);
					State.WeldNumVerts = NumLodVertsForWeld;
					State.WeldNumIndices = (uint32)Welded.Num();
					WeldCanonSRV = GraphBuilder.CreateSRV(CanonBuf);
					WeldIndexSRV = GraphBuilder.CreateSRV(IdxBuf, PF_R32_UINT);
					if (!State.bLoggedWeld)
					{
						State.bLoggedWeld = true;
						UE_LOG(LogPianoHand, Display, TEXT("[SkinDeformer] %s: UV-seam weld map built - %d of %u vertices are seam twins (%d indices rewritten)"),
							*OwnerName.ToString(), NumTwins, NumLodVertsForWeld, Welded.Num());
					}
				}
				else
				{
					State.WeldCanon.SafeRelease();
					State.WeldIndices.SafeRelease();
					State.WeldNumVerts = 0;
					if (!State.bLoggedWeld)
					{
						State.bLoggedWeld = true;
						UE_LOG(LogPianoHand, Warning, TEXT("[SkinDeformer] %s: no CPU access to positions / indices - seam weld unavailable, tension and normals skipped"), *OwnerName.ToString());
					}
				}
			}
			else
			{
				WeldCanonSRV = GraphBuilder.CreateSRV(GraphBuilder.RegisterExternalBuffer(State.WeldCanon, TEXT("PianoHandWeldCanon")));
				WeldIndexSRV = GraphBuilder.CreateSRV(GraphBuilder.RegisterExternalBuffer(State.WeldIndices, TEXT("PianoHandWeldIndices")), PF_R32_UINT);
			}
		}
		if (WeldIndexSRV == nullptr) { IndexSRV = nullptr; }
		if (bComputeTension)
		{
			if (IndexSRV != nullptr)
			{
				ColorBuffer = FSkeletalMeshDeformerHelpers::AllocateVertexFactoryColorBuffer(GraphBuilder, ExternalAccessQueue, MeshObject, LodIndex, TEXT("PianoHandSkinDeformerColor"));
			}
			if (IndexSRV == nullptr || ColorBuffer == nullptr)
			{
				bComputeTension = false;
				if (!State.bLoggedTensionUnavailable)
				{
					State.bLoggedTensionUnavailable = true;
					UE_LOG(LogPianoHand, Warning, TEXT("[SkinDeformer] %s: tension output unavailable (index SRV=%d, colour buffer=%d); skinning only."),
						*OwnerName.ToString(), IndexSRV != nullptr ? 1 : 0, ColorBuffer != nullptr ? 1 : 0);
				}
			}
		}

		const EPixelFormat TangentsFormat = IsOpenGLPlatform(GMaxRHIShaderPlatform) ? PF_R16G16B16A16_SINT : PF_R16G16B16A16_SNORM;
		FRDGBufferUAVRef PositionUAV = GraphBuilder.CreateUAV(PositionBuffer, PF_R32_FLOAT);
		FRDGBufferUAVRef TangentUAV = GraphBuilder.CreateUAV(TangentBuffer, TangentsFormat);
		// 10-16: per-vertex skinning rotation for the elastic (ARAP) tangential relaxation of the implicit stage
		FRDGBufferRef VertexRotBuffer = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(sizeof(FVector4f), FMath::Max(Lod.GetNumVertices(), 1u)), TEXT("PianoHandVertexRot"));
		FRDGBufferUAVRef VertexRotUAV = GraphBuilder.CreateUAV(VertexRotBuffer);

		FPianoHandSkinDeformerCS::FPermutationDomain PermutationVector;
		PermutationVector.Set<FPianoHandSkinDeformerCS::FSkinModeDim>(Mode == EPianoHandSkinMode::LinearBlend ? 0 : 1);
		PermutationVector.Set<FPianoHandSkinDeformerCS::FBoneIndex16Dim>(bIndex16);
		PermutationVector.Set<FPianoHandSkinDeformerCS::FBoneWeight16Dim>(bWeight16);
		TShaderMapRef<FPianoHandSkinDeformerCS> ComputeShader(GetGlobalShaderMap(GMaxRHIFeatureLevel), PermutationVector);

		// One skinning dispatch per section with the given bone tables, into the given UAVs.
		auto AddSkinPasses = [&](const TCHAR* EventName, const TArray<FSkinBoneTransform>& Bones, const TArray<FSkinBoneTransform>& Normals,
		                         FRDGBufferUAVRef PosUAV, FRDGBufferUAVRef TanUAV)
		{
			for (int32 SectionIndex = 0; SectionIndex < Lod.RenderSections.Num(); ++SectionIndex)
			{
				const FSkelMeshRenderSection& Section = Lod.RenderSections[SectionIndex];
				if (Section.bDisabled || Section.NumVertices == 0)
				{
					continue;
				}

				TArray<FSkinBoneTransform> SectionBones = SectionTable(Section, Bones);
				TArray<FSkinBoneTransform> SectionNormals = SectionTable(Section, Normals);
				FRDGBufferRef BoneBuffer = CreateStructuredBuffer(GraphBuilder, TEXT("PianoHandSkinDeformerBones"), SectionBones);
				FRDGBufferRef NormalBuffer = CreateStructuredBuffer(GraphBuilder, TEXT("PianoHandSkinDeformerBoneNormals"), SectionNormals);

				FPianoHandSkinDeformerCS::FParameters* SkinParams = GraphBuilder.AllocParameters<FPianoHandSkinDeformerCS::FParameters>();
				SkinParams->NumVertices = Section.NumVertices;
				SkinParams->BaseVertexIndex = Section.BaseVertexIndex;
				SkinParams->NumBoneInfluences = NumBoneInfluences;
				SkinParams->InputWeightStride = InputWeightStride;
				SkinParams->NumSectionBones = SectionBones.Num();
				SkinParams->PositionInputBuffer = PositionSRV;
				SkinParams->TangentInputBuffer = TangentSRV;
				SkinParams->InputWeightStream = WeightSRV;
				SkinParams->BoneTransforms = GraphBuilder.CreateSRV(BoneBuffer);
				SkinParams->BoneNormalTransforms = GraphBuilder.CreateSRV(NormalBuffer);
				SkinParams->PositionBufferUAV = PosUAV;
				SkinParams->TangentBufferUAV = TanUAV;
				SkinParams->VertexRotUAV = VertexRotUAV;

				FComputeShaderUtils::AddPass(
					GraphBuilder,
					RDG_EVENT_NAME("PianoHand.%s(section %d, %u verts)", EventName, SectionIndex, Section.NumVertices),
					ComputeShader,
					SkinParams,
					FComputeShaderUtils::GetGroupCount(Section.NumVertices, FPianoHandSkinDeformerCS::ThreadGroupSize));
			}
		};

		AddSkinPasses(TEXT("SkinDeformer"), AllBones, AllBoneNormals, PositionUAV, TangentUAV);

		// -------------------------------------------------------------------
		// Phase 8: implicit skinning. The LBS / DQS pose above is the initial solution; every vertex
		// now marches along the gradient of the composed HRBF field back to its rest iso-value,
		// with tangential relaxation between pairs of Newton steps and a localised Laplacian pass
		// over the contact regions afterwards (Vaillant et al. 2013, sections 5-6).
		// -------------------------------------------------------------------
		const uint32 NumLodVerticesEarly = Lod.GetNumVertices();
		FPianoHandImplicitCommonParameters ImplicitDebugCommon;
		FRDGBufferRef ImplicitPrePos = nullptr;
		FRDGBufferRef ImplicitGradBuffer = nullptr;
		FRDGBufferRef ImplicitStateBuffer = nullptr;
		const bool bImplicit = Params.bImplicitSkinning && Implicit.IsValid() && Implicit->bValid
			&& Implicit->NumVertices == NumLodVerticesEarly && PrimInverses.Num() == Implicit->PrimInfo.Num() && Params.ImplicitIterations > 0;
		if (bImplicit)
		{
			// Static tables live in pooled buffers across frames; re-uploaded when the build changes.
			const bool bUpload = State.ImplicitBuildId != Implicit->BuildId || !State.ImplicitSamples.IsValid() || !State.ImplicitAdjWeights.IsValid();
			auto Static = [&](const TCHAR* Name, const auto& Array, TRefCountPtr<FRDGPooledBuffer>& Pooled) -> FRDGBufferRef
			{
				if (bUpload)
				{
					FRDGBufferRef Buf = CreateStructuredBuffer(GraphBuilder, Name, Array);
					GraphBuilder.QueueBufferExtraction(Buf, &Pooled);
					return Buf;
				}
				return GraphBuilder.RegisterExternalBuffer(Pooled, Name);
			};
			FPianoHandImplicitCommonParameters Common;
			Common.NumVertices = NumLodVerticesEarly;
			Common.NumPrims = (uint32)Implicit->PrimInfo.Num();
			Common.HrbfSamples = GraphBuilder.CreateSRV(Static(TEXT("PianoHandImplicitSamples"), Implicit->Samples, State.ImplicitSamples));
			Common.PrimInfo = GraphBuilder.CreateSRV(Static(TEXT("PianoHandImplicitPrimInfo"), Implicit->PrimInfo, State.ImplicitPrimInfo));
			Common.PrimAxis = GraphBuilder.CreateSRV(Static(TEXT("PianoHandImplicitPrimAxis"), Implicit->PrimAxis, State.ImplicitPrimAxis));
			Common.PrimMeta = GraphBuilder.CreateSRV(Static(TEXT("PianoHandImplicitPrimMeta"), Implicit->PrimMeta, State.ImplicitPrimMeta));
			Common.PrimNeighbours = GraphBuilder.CreateSRV(Static(TEXT("PianoHandImplicitPrimNeighbours"), Implicit->PrimNeighbours, State.ImplicitPrimNeighbours));
			Common.VertexPrim = GraphBuilder.CreateSRV(Static(TEXT("PianoHandImplicitVertexPrim"), Implicit->VertexPrim, State.ImplicitVertexPrim));
			Common.VertexIso = GraphBuilder.CreateSRV(Static(TEXT("PianoHandImplicitVertexIso"), Implicit->VertexIso, State.ImplicitVertexIso));
			Common.VertexOverlap = GraphBuilder.CreateSRV(Static(TEXT("PianoHandImplicitVertexOverlap"), Implicit->VertexOverlap, State.ImplicitVertexOverlap));
			Common.VertexOwn = GraphBuilder.CreateSRV(Static(TEXT("PianoHandImplicitVertexOwn"), Implicit->VertexOwn, State.ImplicitVertexOwn));
			Common.VertexBlend = GraphBuilder.CreateSRV(Static(TEXT("PianoHandImplicitVertexBlend"), Implicit->VertexBlend, State.ImplicitVertexBlend));
			Common.AdjOffsets = GraphBuilder.CreateSRV(Static(TEXT("PianoHandImplicitAdjOffsets"), Implicit->AdjOffsets, State.ImplicitAdjOffsets));
			Common.AdjIndices = GraphBuilder.CreateSRV(Static(TEXT("PianoHandImplicitAdjIndices"), Implicit->AdjIndices, State.ImplicitAdjIndices));
			Common.AdjWeights = GraphBuilder.CreateSRV(Static(TEXT("PianoHandImplicitAdjWeights"), Implicit->AdjWeights, State.ImplicitAdjWeights));
			if (bUpload)
			{
				State.ImplicitBuildId = Implicit->BuildId;
				if (!State.bLoggedImplicit)
				{
					State.bLoggedImplicit = true;
					UE_LOG(LogPianoHand, Display, TEXT("[SkinDeformer] %s: implicit skinning on - %s"), *OwnerName.ToString(), *Implicit->Summary);
				}
			}
			// per frame: the animated -> rest transform of every primitive
			FRDGBufferRef PrimInvBuffer = CreateStructuredBuffer(GraphBuilder, TEXT("PianoHandImplicitPrimInverse"), PrimInverses);
			Common.PrimInverse = GraphBuilder.CreateSRV(PrimInvBuffer);
			TArray<float> PairBendSafe = PairBend;
			if (PairBendSafe.Num() == 0) { PairBendSafe.Add(0.0f); }
			FRDGBufferSRVRef PairBendSRV = GraphBuilder.CreateSRV(CreateStructuredBuffer(GraphBuilder, TEXT("PianoHandImplicitPairBend"), PairBendSafe));

			ImplicitDebugCommon = Common;
			ImplicitPrePos = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateBufferDesc(sizeof(float), FMath::Max(NumLodVerticesEarly * 3u, 1u)), TEXT("PianoHandImplicitPrePos"));
			AddCopyBufferPass(GraphBuilder, ImplicitPrePos, 0, PositionBuffer, 0, FMath::Min<uint64>((uint64)NumLodVerticesEarly * 3u * sizeof(float), PositionBuffer->Desc.GetSize()));
			FRDGBufferRef GradBuffer = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(sizeof(FVector4f), FMath::Max(NumLodVerticesEarly, 1u)), TEXT("PianoHandImplicitGrad"));
			ImplicitGradBuffer = GradBuffer;
			FRDGBufferRef StateBuffer = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(sizeof(uint32), FMath::Max(NumLodVerticesEarly, 1u)), TEXT("PianoHandImplicitState"));
			ImplicitStateBuffer = StateBuffer;
			FRDGBufferRef PushBuffer = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(sizeof(float), FMath::Max(NumLodVerticesEarly, 1u)), TEXT("PianoHandImplicitPush"));
			FRDGBufferUAVRef PushUAV = GraphBuilder.CreateUAV(PushBuffer);
			FRDGBufferRef Snapshot = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateBufferDesc(sizeof(float), FMath::Max(NumLodVerticesEarly * 3u, 1u)), TEXT("PianoHandImplicitSnapshot"));
			FRDGBufferUAVRef GradUAV = GraphBuilder.CreateUAV(GradBuffer);
			FRDGBufferUAVRef StateUAV = GraphBuilder.CreateUAV(StateBuffer);
			FRDGBufferSRVRef SnapshotSRV = GraphBuilder.CreateSRV(Snapshot, PF_R32_FLOAT);
			const uint64 PosBytes = (uint64)NumLodVerticesEarly * 3u * sizeof(float);
			auto TakeSnapshot = [&]()
			{
				AddCopyBufferPass(GraphBuilder, Snapshot, 0, PositionBuffer, 0, FMath::Min<uint64>(PosBytes, PositionBuffer->Desc.GetSize()));
			};

			// ---- Phase 11: incremental tracking (Vaillant 2014 step 1) --------------------------------------
			// Start from last frame's tracked skin carried by each primitive's transform difference, unless the pose
			// jumped (scrub, first frame, rebuilt data) - then the geometric skinning above is the initial guess.
			bool bTracked = false;
			if (Params.bImplicitTracking && State.ImplicitTracked.IsValid() && State.ImplicitTrackedNumVerts == NumLodVerticesEarly
				&& State.ImplicitTrackedBuildId == Implicit->BuildId && State.ImplicitPrevPrimForward.Num() == PrimForward.Num()
				&& State.ImplicitPrevPrimInverse.Num() == PrimInverses.Num() && PrimForward.Num() > 0)
			{
				float MaxAngle = 0.0f, MaxShift = 0.0f;
				for (int32 Pi = 0; Pi < PrimForward.Num(); ++Pi)
				{
					const FMatrix44f Delta = State.ImplicitPrevPrimInverse[Pi].ToMatrix() * PrimForward[Pi].ToMatrix();   // prev^-1 then now (row-vector convention)
					const float Trace = Delta.M[0][0] + Delta.M[1][1] + Delta.M[2][2];
					MaxAngle = FMath::Max(MaxAngle, FMath::Acos(FMath::Clamp((Trace - 1.0f) * 0.5f, -1.0f, 1.0f)));
					MaxShift = FMath::Max(MaxShift, FVector3f(Delta.M[3][0], Delta.M[3][1], Delta.M[3][2]).Size());
				}
				bTracked = MaxAngle <= FMath::DegreesToRadians(FMath::Max(Params.ImplicitTrackMaxStepDeg, 1.0f)) && MaxShift <= 5.0f;
			}
			if (bTracked)
			{
				FRDGBufferRef TrackedBuffer = GraphBuilder.RegisterExternalBuffer(State.ImplicitTracked, TEXT("PianoHandImplicitTracked"));
				FRDGBufferRef PrevInvBuffer = CreateStructuredBuffer(GraphBuilder, TEXT("PianoHandImplicitPrimPrevInverse"), State.ImplicitPrevPrimInverse);
				FRDGBufferRef PrimNowBuffer = CreateStructuredBuffer(GraphBuilder, TEXT("PianoHandImplicitPrimNow"), PrimForward);
				TShaderMapRef<FPianoHandImplicitAdvectCS> AdvectShader(GetGlobalShaderMap(GMaxRHIFeatureLevel));
				FPianoHandImplicitAdvectCS::FParameters* AP = GraphBuilder.AllocParameters<FPianoHandImplicitAdvectCS::FParameters>();
				AP->Common = Common;
				AP->TrackedIn = GraphBuilder.CreateSRV(TrackedBuffer, PF_R32_FLOAT);
				AP->PrimPrevInverse = GraphBuilder.CreateSRV(PrevInvBuffer);
				AP->PrimNow = GraphBuilder.CreateSRV(PrimNowBuffer);
				AP->PositionUAV = PositionUAV;
				FComputeShaderUtils::AddPass(GraphBuilder, RDG_EVENT_NAME("PianoHand.ImplicitAdvect"), AdvectShader, AP,
					FComputeShaderUtils::GetGroupCount(NumLodVerticesEarly, FPianoHandImplicitAdvectCS::ThreadGroupSize));
				if (!State.bLoggedTracking)
				{
					State.bLoggedTracking = true;
					UE_LOG(LogPianoHand, Display, TEXT("[SkinDeformer] %s: implicit tracking on (incremental iso-surface tracking, max step %.0f deg)"), *OwnerName.ToString(), Params.ImplicitTrackMaxStepDeg);
				}
			}

			const FIntPoint Groups(FComputeShaderUtils::GetGroupCount(NumLodVerticesEarly, 64).X, 1);
			TShaderMapRef<FPianoHandImplicitProjectCS> ProjectShader(GetGlobalShaderMap(GMaxRHIFeatureLevel));
			TShaderMapRef<FPianoHandImplicitRelaxCS> RelaxShader(GetGlobalShaderMap(GMaxRHIFeatureLevel));
			TShaderMapRef<FPianoHandImplicitBetaCS> BetaShader(GetGlobalShaderMap(GMaxRHIFeatureLevel));
			TShaderMapRef<FPianoHandImplicitSmoothCS> SmoothShader(GetGlobalShaderMap(GMaxRHIFeatureLevel));

			const int32 Iterations = FMath::Clamp(Params.ImplicitIterations, 1, 32);
			const int32 Rounds = (Iterations + 1) / 2;
			for (int32 Round = 0; Round < Rounds; ++Round)
			{
				FPianoHandImplicitProjectCS::FParameters* PP = GraphBuilder.AllocParameters<FPianoHandImplicitProjectCS::FParameters>();
				PP->Common = Common;
				PP->NumSteps = (uint32)FMath::Min(2, Iterations - Round * 2);
				PP->bFirstPass = (Round == 0) ? 1u : 0u;
				PP->Sigma = Params.ImplicitSigma;
				PP->IsoTolerance = Params.ImplicitTolerance;
				PP->StopCosAngle = FMath::Cos(FMath::DegreesToRadians(Params.ImplicitStopAngle));
				PP->MaxStepCm = Params.ImplicitMaxStep;
				PP->BulgeAmount = Params.ImplicitBulge;
				PP->BulgeStart = FMath::DegreesToRadians(Params.ImplicitBulgeStart);
				PP->BulgeFull = FMath::DegreesToRadians(FMath::Max(Params.ImplicitBulgeFull, Params.ImplicitBulgeStart + 1.0f));
				PP->BendGateStart = FMath::DegreesToRadians(Params.ImplicitBendStart);
				PP->BendGateFull = FMath::DegreesToRadians(FMath::Max(Params.ImplicitBendFull, Params.ImplicitBendStart + 1.0f));
				PP->PairBend = PairBendSRV;
				PP->ContactDepth = FMath::Max(Params.ImplicitContactDepth, 0.0f);
				PP->VertexPush = PushUAV;
				PP->PositionUAV = PositionUAV;
				PP->VertexGrad = GradUAV;
				PP->VertexState = StateUAV;
				FComputeShaderUtils::AddPass(GraphBuilder, RDG_EVENT_NAME("PianoHand.ImplicitProject(%d)", Round), ProjectShader, PP,
					FComputeShaderUtils::GetGroupCount(NumLodVerticesEarly, FPianoHandImplicitProjectCS::ThreadGroupSize));

				if (Params.ImplicitRelax > 0.0f && Round + 1 < Rounds)
				{
					TakeSnapshot();
					FPianoHandImplicitRelaxCS::FParameters* RP = GraphBuilder.AllocParameters<FPianoHandImplicitRelaxCS::FParameters>();
					RP->Common = Common;
					RP->RelaxScale = Params.ImplicitRelax;
					RP->PositionIn = SnapshotSRV;
					RP->RestPositionIn = PositionSRV;
					RP->VertexRot = GraphBuilder.CreateSRV(VertexRotBuffer);
					RP->PositionUAV = PositionUAV;
					RP->VertexGrad = GradUAV;
					RP->VertexState = StateUAV;
					FComputeShaderUtils::AddPass(GraphBuilder, RDG_EVENT_NAME("PianoHand.ImplicitRelax(%d)", Round), RelaxShader, RP,
						FComputeShaderUtils::GetGroupCount(NumLodVerticesEarly, FPianoHandImplicitRelaxCS::ThreadGroupSize));
				}
			}

			const int32 SmoothIt = FMath::Clamp(Params.ImplicitSmoothIterations, 0, 48);
			if (SmoothIt > 0 && Params.ImplicitSmoothBeta > 0.0f)
			{
				FRDGBufferRef BetaA = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(sizeof(float), FMath::Max(NumLodVerticesEarly, 1u)), TEXT("PianoHandImplicitBetaA"));
				FRDGBufferRef BetaB = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(sizeof(float), FMath::Max(NumLodVerticesEarly, 1u)), TEXT("PianoHandImplicitBetaB"));
				const int32 Diffusion = FMath::Clamp(Params.ImplicitBetaDiffusion, 0, 48);
				FRDGBufferRef Cur = BetaA, Nxt = BetaB;
				// the seed pass only writes, but it still binds BetaIn: give RDG a produced buffer to validate against
				AddClearUAVPass(GraphBuilder, GraphBuilder.CreateUAV(BetaB), 0u);
				for (int32 It = 0; It <= Diffusion; ++It)
				{
					FPianoHandImplicitBetaCS::FParameters* BP = GraphBuilder.AllocParameters<FPianoHandImplicitBetaCS::FParameters>();
					BP->Common = Common;
					BP->bFirstPass = (It == 0) ? 1u : 0u;
					BP->BetaIn = GraphBuilder.CreateSRV(It == 0 ? Nxt : Cur);
					BP->BetaOut = GraphBuilder.CreateUAV(It == 0 ? Cur : Nxt);
					BP->VertexState = StateUAV;
					BP->VertexPush = PushUAV;
					FComputeShaderUtils::AddPass(GraphBuilder, RDG_EVENT_NAME("PianoHand.ImplicitBeta(%d)", It), BetaShader, BP,
						FComputeShaderUtils::GetGroupCount(NumLodVerticesEarly, FPianoHandImplicitBetaCS::ThreadGroupSize));
					if (It > 0) { Swap(Cur, Nxt); }
				}
				FRDGBufferSRVRef BetaSRV = GraphBuilder.CreateSRV(Cur);
				for (int32 It = 0; It < SmoothIt; ++It)
				{
					TakeSnapshot();
					FPianoHandImplicitSmoothCS::FParameters* SP = GraphBuilder.AllocParameters<FPianoHandImplicitSmoothCS::FParameters>();
					SP->Common = Common;
					SP->SmoothBeta = Params.ImplicitSmoothBeta;
					SP->PositionIn = SnapshotSRV;
					SP->PrePosition = GraphBuilder.CreateSRV(ImplicitPrePos, PF_R32_FLOAT);
					SP->BetaIn = BetaSRV;
					SP->PositionUAV = PositionUAV;
					FComputeShaderUtils::AddPass(GraphBuilder, RDG_EVENT_NAME("PianoHand.ImplicitSmooth(%d)", It), SmoothShader, SP,
						FComputeShaderUtils::GetGroupCount(NumLodVerticesEarly, FPianoHandImplicitSmoothCS::ThreadGroupSize));
				}
			}

			// fade the correction out towards the palm (per-vertex blend from the finger weights)
			{
				TShaderMapRef<FPianoHandImplicitFinalizeCS> FinalizeShader(GetGlobalShaderMap(GMaxRHIFeatureLevel));
				FPianoHandImplicitFinalizeCS::FParameters* FP = GraphBuilder.AllocParameters<FPianoHandImplicitFinalizeCS::FParameters>();
				FP->Common = Common;
				FP->StretchKeep = FMath::Clamp(Params.ImplicitStretchKeep, 0.0f, 1.0f);
				FP->BendGateStart = FMath::DegreesToRadians(Params.ImplicitBendStart);
				FP->BendGateFull = FMath::DegreesToRadians(FMath::Max(Params.ImplicitBendFull, Params.ImplicitBendStart + 1.0f));
				FP->PairBend = PairBendSRV;
				FP->PrePosition = GraphBuilder.CreateSRV(ImplicitPrePos, PF_R32_FLOAT);
				FP->PositionUAV = PositionUAV;
				FComputeShaderUtils::AddPass(GraphBuilder, RDG_EVENT_NAME("PianoHand.ImplicitFinalize"), FinalizeShader, FP,
					FComputeShaderUtils::GetGroupCount(NumLodVerticesEarly, FPianoHandImplicitFinalizeCS::ThreadGroupSize));
			}
			// Phase 11: keep this frame's result (and the primitive transforms it was tracked under) for the next frame
			if (Params.bImplicitTracking)
			{
				FRDGBufferRef TrackedOut = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateBufferDesc(sizeof(float), FMath::Max(NumLodVerticesEarly * 3u, 1u)), TEXT("PianoHandImplicitTrackedOut"));
				AddCopyBufferPass(GraphBuilder, TrackedOut, 0, PositionBuffer, 0, FMath::Min<uint64>(PosBytes, PositionBuffer->Desc.GetSize()));
				GraphBuilder.QueueBufferExtraction(TrackedOut, &State.ImplicitTracked);
				State.ImplicitTrackedNumVerts = NumLodVerticesEarly;
				State.ImplicitTrackedBuildId = Implicit->BuildId;
				State.ImplicitPrevPrimForward = PrimForward;
				State.ImplicitPrevPrimInverse = PrimInverses;
			}
			else
			{
				State.ImplicitTracked.SafeRelease();
				State.ImplicitTrackedNumVerts = 0;
			}
		}

		// -------------------------------------------------------------------
		// Phase 5: proportions. The strain reference has to be the SCALED rest pose, or a finger made
		// 10% longer reads as 10% stretched everywhere and sprouts veins. Skin the rest pose once more
		// with the proportion-only transforms (RefPoseInverse * Scale * RefPose) into scratch buffers
		// and hand those to the tension / detail passes as "rest".
		// -------------------------------------------------------------------
		const bool bUseProportionedRest = Params.bProportioned && Params.bComputeTension;
		if (Params.bProportioned && Mode != EPianoHandSkinMode::LinearBlend && !State.bLoggedProportionsDQS)
		{
			State.bLoggedProportionsDQS = true;
			UE_LOG(LogPianoHand, Warning, TEXT("[SkinDeformer] %s: hand proportions are applied as bone scales, which dual quaternions cannot carry; the DQS result ignores them."), *OwnerName.ToString());
		}
		// Always allocated (a few bytes when unused) so the typed RDG SRV parameters below are never null.
		const uint32 PropVerts = bUseProportionedRest ? Lod.GetNumVertices() : 1u;
		FRDGBufferRef PropRestPosition = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateBufferDesc(sizeof(float), PropVerts * 3u), TEXT("PianoHandProportionedRestPosition"));
		FRDGBufferRef PropRestTangent = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateBufferDesc(sizeof(uint16) * 4, PropVerts * 2u), TEXT("PianoHandProportionedRestTangent"));
		if (bUseProportionedRest)
		{
			AddSkinPasses(TEXT("ProportionedRest"), AllRestBones, AllRestBoneNormals,
				GraphBuilder.CreateUAV(PropRestPosition, PF_R32_FLOAT), GraphBuilder.CreateUAV(PropRestTangent, TangentsFormat));
		}
		else
		{
			AddClearUAVPass(GraphBuilder, GraphBuilder.CreateUAV(PropRestPosition, PF_R32_FLOAT), 0u);
			AddClearUAVPass(GraphBuilder, GraphBuilder.CreateUAV(PropRestTangent, TangentsFormat), 0u);
		}
		FRDGBufferSRVRef PropRestPositionSRV = GraphBuilder.CreateSRV(PropRestPosition, PF_R32_FLOAT);
		FRDGBufferSRVRef PropRestTangentSRV = GraphBuilder.CreateSRV(PropRestTangent, TangentsFormat);

		// -------------------------------------------------------------------
		// Phase 2: per-vertex strain tensor (stretch tensor vs rest pose) -> vertex colour
		// -------------------------------------------------------------------
		FRDGBufferRef VertexTensorBuffer = nullptr;
		FRDGBufferRef RelaxStateBuffer = nullptr;
		FRDGBufferSRVRef SkinnedPositionSRV = nullptr;
		const uint32 NumLodVertices = Lod.GetNumVertices();

		if (bComputeTension)
		{
			check(NumLodVertices > 0);

			// 6 unique components of the symmetric 3x3 tensor per vertex, fixed point.
			constexpr uint32 TensorStride = 6u;
			FRDGBufferRef TensorAccum = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(sizeof(int32), FMath::Max(NumLodVertices * TensorStride, 1u)), TEXT("PianoHandTensionTensorAccum"));
			FRDGBufferRef TensorCount = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(sizeof(uint32), FMath::Max(NumLodVertices, 1u)), TEXT("PianoHandTensionTensorCount"));
			FRDGBufferUAVRef TensorAccumUAV = GraphBuilder.CreateUAV(TensorAccum);
			FRDGBufferUAVRef TensorCountUAV = GraphBuilder.CreateUAV(TensorCount);
			AddClearUAVPass(GraphBuilder, TensorAccumUAV, 0u);
			AddClearUAVPass(GraphBuilder, TensorCountUAV, 0u);
			FRDGBufferRef NormalOuter = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(sizeof(int32), FMath::Max(NumLodVertices * TensorStride, 1u)), TEXT("PianoHandTensionNormalOuter"));
			FRDGBufferUAVRef NormalOuterUAV = GraphBuilder.CreateUAV(NormalOuter);
			AddClearUAVPass(GraphBuilder, NormalOuterUAV, 0u);

			SkinnedPositionSRV = GraphBuilder.CreateSRV(PositionBuffer, PF_R32_FLOAT);
			TShaderMapRef<FPianoHandTensionAccumulateCS> AccumulateShader(GetGlobalShaderMap(GMaxRHIFeatureLevel));

			for (int32 SectionIndex = 0; SectionIndex < Lod.RenderSections.Num(); ++SectionIndex)
			{
				const FSkelMeshRenderSection& Section = Lod.RenderSections[SectionIndex];
				if (Section.bDisabled || Section.NumTriangles == 0)
				{
					continue;
				}

				FPianoHandTensionAccumulateCS::FParameters* AccParams = GraphBuilder.AllocParameters<FPianoHandTensionAccumulateCS::FParameters>();
				AccParams->NumTriangles = Section.NumTriangles;
				AccParams->BaseIndex = Section.BaseIndex;
				AccParams->IndexBuffer = WeldIndexSRV;
				AccParams->RestPositionBuffer = PositionSRV;
				AccParams->ProportionedRestPositionBuffer = PropRestPositionSRV;
				AccParams->bUseProportionedRest = bUseProportionedRest ? 1u : 0u;
				AccParams->SkinnedPositionBuffer = SkinnedPositionSRV;
				AccParams->TensorAccum = TensorAccumUAV;
				AccParams->TensorCount = TensorCountUAV;
				AccParams->NormalOuterAccum = NormalOuterUAV;

				FComputeShaderUtils::AddPass(
					GraphBuilder,
					RDG_EVENT_NAME("PianoHand.TensionAccumulate(section %d, %u tris)", SectionIndex, Section.NumTriangles),
					AccumulateShader,
					AccParams,
					FComputeShaderUtils::GetGroupCount(Section.NumTriangles, FPianoHandTensionAccumulateCS::ThreadGroupSize));
			}

			// Averaged tensor, kept for the Phase 3 detail pass.
			VertexTensorBuffer = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(sizeof(float), FMath::Max(NumLodVertices * TensorStride, 1u)), TEXT("PianoHandVertexTensor"));

			// ---- relax state: the one thing here that has to survive the frame -------------
			// Skin that has been pulled taut does not come back flat. Detecting that needs last
			// frame's strain, so this buffer is extracted out of the graph and registered back in
			// next frame. A LOD change or a first frame resets it - stale slack from a different
			// vertex count would otherwise bleed folds onto the wrong places.
			const bool bRelaxReset =
				!State.RelaxStateBuffer.IsValid() ||
				State.RelaxStateNumVertices != NumLodVertices ||
				bInvalidatePreviousPosition;

			if (bRelaxReset)
			{
				RelaxStateBuffer = GraphBuilder.CreateBuffer(
					FRDGBufferDesc::CreateStructuredDesc(sizeof(float) * 2, FMath::Max(NumLodVertices, 1u)),
					TEXT("PianoHandRelaxState"));
				AddClearUAVPass(GraphBuilder, GraphBuilder.CreateUAV(RelaxStateBuffer), 0u);
				State.RelaxStateNumVertices = NumLodVertices;
			}
			else
			{
				RelaxStateBuffer = GraphBuilder.RegisterExternalBuffer(State.RelaxStateBuffer, TEXT("PianoHandRelaxState"));
			}

			// Wall-clock delta, clamped: a hitch or a paused editor must not dump the whole decay
			// in one step, and a zero delta would freeze the slack instead of letting it settle.
			const double NowSeconds = FPlatformTime::Seconds();
			const float RelaxDeltaTime = (State.RelaxLastTimeSeconds > 0.0)
				? FMath::Clamp((float)(NowSeconds - State.RelaxLastTimeSeconds), 0.0f, 0.1f)
				: 0.0f;
			State.RelaxLastTimeSeconds = NowSeconds;

			FRDGBufferUAVRef ColorUAV = GraphBuilder.CreateUAV(ColorBuffer, PF_R8G8B8A8);
			TShaderMapRef<FPianoHandTensionResolveCS> ResolveShader(GetGlobalShaderMap(GMaxRHIFeatureLevel));
			FPianoHandTensionResolveCS::FParameters* ResParams = GraphBuilder.AllocParameters<FPianoHandTensionResolveCS::FParameters>();
			ResParams->NumVertices = NumLodVertices;
			ResParams->TensionScale = Params.TensionScale;
			ResParams->RestTangentBuffer = TangentSRV;
			ResParams->ProportionedRestTangentBuffer = PropRestTangentSRV;
			ResParams->bUseProportionedRest = bUseProportionedRest ? 1u : 0u;
			ResParams->TensorAccumIn = GraphBuilder.CreateSRV(TensorAccum);
			ResParams->TensorCountIn = GraphBuilder.CreateSRV(TensorCount);
			ResParams->NormalOuterAccumIn = GraphBuilder.CreateSRV(NormalOuter);
			ResParams->WeldCanon = WeldCanonSRV;
			ResParams->ColorBufferUAV = ColorUAV;
			ResParams->VertexTensorOut = GraphBuilder.CreateUAV(VertexTensorBuffer);
			ResParams->DeltaTime = RelaxDeltaTime;
			ResParams->RelaxGain = Params.RelaxGain;
			ResParams->RelaxTau = Params.RelaxTau;
			ResParams->bResetRelax = bRelaxReset ? 1u : 0u;
			ResParams->RelaxState = GraphBuilder.CreateUAV(RelaxStateBuffer);

			FComputeShaderUtils::AddPass(
				GraphBuilder,
				RDG_EVENT_NAME("PianoHand.TensionResolve(%u verts)", NumLodVertices),
				ResolveShader,
				ResParams,
				FComputeShaderUtils::GetGroupCount(NumLodVertices, FPianoHandTensionResolveCS::ThreadGroupSize));

			GraphBuilder.QueueBufferExtraction(RelaxStateBuffer, &State.RelaxStateBuffer);

			// Phase 7b: smooth the averaged tensor over the mesh before the detail pass reads it.
			for (int32 It = 0; It < FMath::Clamp(Params.TensorSmoothIterations, 0, 6); ++It)
			{
				AddClearUAVPass(GraphBuilder, TensorAccumUAV, 0u);
				AddClearUAVPass(GraphBuilder, TensorCountUAV, 0u);
				FRDGBufferSRVRef InSRV = GraphBuilder.CreateSRV(VertexTensorBuffer);
				TShaderMapRef<FPianoHandTensorSmoothScatterCS> ScatterShader(GetGlobalShaderMap(GMaxRHIFeatureLevel));
				for (int32 SectionIndex = 0; SectionIndex < Lod.RenderSections.Num(); ++SectionIndex)
				{
					const FSkelMeshRenderSection& Section = Lod.RenderSections[SectionIndex];
					if (Section.bDisabled || Section.NumTriangles == 0) { continue; }
					FPianoHandTensorSmoothScatterCS::FParameters* SP = GraphBuilder.AllocParameters<FPianoHandTensorSmoothScatterCS::FParameters>();
					SP->NumTriangles = Section.NumTriangles;
					SP->BaseIndex = Section.BaseIndex;
					SP->IndexBuffer = WeldIndexSRV;
					SP->SmoothTensorIn = InSRV;
					SP->TensorAccum = TensorAccumUAV;
					SP->TensorCount = TensorCountUAV;
					FComputeShaderUtils::AddPass(GraphBuilder, RDG_EVENT_NAME("PianoHand.TensorSmoothScatter(%d)", It), ScatterShader, SP,
						FComputeShaderUtils::GetGroupCount(Section.NumTriangles, FPianoHandTensorSmoothScatterCS::ThreadGroupSize));
				}
				FRDGBufferRef Smoothed = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(sizeof(float), FMath::Max(NumLodVertices * TensorStride, 1u)), TEXT("PianoHandVertexTensorSmoothed"));
				TShaderMapRef<FPianoHandTensorSmoothResolveCS> ResolveSmooth(GetGlobalShaderMap(GMaxRHIFeatureLevel));
				FPianoHandTensorSmoothResolveCS::FParameters* RP = GraphBuilder.AllocParameters<FPianoHandTensorSmoothResolveCS::FParameters>();
				RP->NumVertices = NumLodVertices;
				RP->SmoothLambda = FMath::Clamp(Params.TensorSmoothLambda, 0.0f, 1.0f);
				RP->SmoothTensorIn = InSRV;
				RP->TensorAccumIn = GraphBuilder.CreateSRV(TensorAccum);
				RP->TensorCountIn = GraphBuilder.CreateSRV(TensorCount);
				RP->WeldCanon = WeldCanonSRV;
				RP->SmoothTensorOut = GraphBuilder.CreateUAV(Smoothed);
				FComputeShaderUtils::AddPass(GraphBuilder, RDG_EVENT_NAME("PianoHand.TensorSmoothResolve(%d)", It), ResolveSmooth, RP,
					FComputeShaderUtils::GetGroupCount(NumLodVertices, FPianoHandTensorSmoothResolveCS::ThreadGroupSize));
				VertexTensorBuffer = Smoothed;
			}
		}

		// -------------------------------------------------------------------
		// Phase 3: detail displacement (volume preservation + joint creases)
		// -------------------------------------------------------------------
		if (Params.bDetailDisplacement && VertexTensorBuffer != nullptr && SkinnedPositionSRV != nullptr && ColorBuffer != nullptr)
		{
			FRDGBufferSRVRef VertexTensorSRV = GraphBuilder.CreateSRV(VertexTensorBuffer);
			FRDGBufferUAVRef DetailColorUAV = GraphBuilder.CreateUAV(ColorBuffer, PF_R8G8B8A8);
			FRDGBufferSRVRef RelaxStateSRV = GraphBuilder.CreateSRV(RelaxStateBuffer);

			FPianoHandDetailDisplaceCS::FPermutationDomain DisplacePermutation;
			DisplacePermutation.Set<FPianoHandDetailDisplaceCS::FBoneIndex16Dim>(bIndex16);
			DisplacePermutation.Set<FPianoHandDetailDisplaceCS::FBoneWeight16Dim>(bWeight16);
			TShaderMapRef<FPianoHandDetailDisplaceCS> DisplaceShader(GetGlobalShaderMap(GMaxRHIFeatureLevel), DisplacePermutation);

			for (int32 SectionIndex = 0; SectionIndex < Lod.RenderSections.Num(); ++SectionIndex)
			{
				const FSkelMeshRenderSection& Section = Lod.RenderSections[SectionIndex];
				if (Section.bDisabled || Section.NumVertices == 0)
				{
					continue;
				}

				// RefBasesInvMatrix in section BoneMap order, so the kernel can take the dominant bone
				// index straight out of the weight stream and get rest-pose bone-local coordinates.
				TArray<FSkinBoneTransform> SectionRefInverses = SectionTable(Section, AllRefInverses);

				FRDGBufferRef RefInvBuffer = CreateStructuredBuffer(GraphBuilder, TEXT("PianoHandRefPoseInverses"), SectionRefInverses);

				FPianoHandDetailDisplaceCS::FParameters* DispParams = GraphBuilder.AllocParameters<FPianoHandDetailDisplaceCS::FParameters>();
				DispParams->NumVertices = Section.NumVertices;
				DispParams->BaseVertexIndex = Section.BaseVertexIndex;
				DispParams->NumBoneInfluences = NumBoneInfluences;
				DispParams->InputWeightStride = InputWeightStride;
				DispParams->NumSectionBones = SectionRefInverses.Num();
				DispParams->VolumeBulge = Params.VolumeBulge;
				DispParams->CreaseDepth = Params.CreaseDepth;
				DispParams->CreaseSharpness = Params.CreaseSharpness;
				DispParams->CreaseCompressionGain = Params.CreaseCompressionGain;
				DispParams->WrinkleAmplitude = Params.WrinkleAmplitude;
				DispParams->WrinkleFrequency = Params.WrinkleFrequency;
				DispParams->CreaseStretchRelief = Params.CreaseStretchRelief;
				DispParams->RelaxCreaseGain = Params.RelaxCreaseGain;
				DispParams->TensionScale = Params.TensionScale;
				DispParams->RestPositionBuffer = PositionSRV;
				DispParams->RestTangentBuffer = TangentSRV;
				DispParams->ProportionedRestPositionBuffer = PropRestPositionSRV;
				DispParams->ProportionedRestTangentBuffer = PropRestTangentSRV;
				DispParams->bUseProportionedRest = bUseProportionedRest ? 1u : 0u;
				DispParams->InputWeightStream = WeightSRV;

				// Phase 5: the baked wrinkle mask, if the texture is streamed in and the mesh has UVs.
				FRHITexture* MaskRHI = (Params.WrinkleMaskResource && Params.WrinkleMaskResource->TextureRHI.IsValid())
					? Params.WrinkleMaskResource->TextureRHI.GetReference() : nullptr;
				FRHIShaderResourceView* UVSRV = Lod.StaticVertexBuffers.StaticMeshVertexBuffer.GetTexCoordsSRV();
				const bool bMask = MaskRHI != nullptr && UVSRV != nullptr;
				if (Params.WrinkleMaskResource != nullptr && !bMask && !State.bLoggedMaskUnavailable)
				{
					State.bLoggedMaskUnavailable = true;
					UE_LOG(LogPianoHand, Warning, TEXT("[SkinDeformer] %s: wrinkle mask set but unavailable (texture RHI=%d, UV SRV=%d); band-wide groove used."),
						*OwnerName.ToString(), MaskRHI != nullptr ? 1 : 0, UVSRV != nullptr ? 1 : 0);
				}
				DispParams->bHasWrinkleMask = bMask ? 1u : 0u;
				DispParams->NumUVChannels = FMath::Max<uint32>(Lod.StaticVertexBuffers.StaticMeshVertexBuffer.GetNumTexCoords(), 1u);
				DispParams->MaskCreaseDepth = Params.MaskCreaseDepth;
				DispParams->MaskCreaseWidth = Params.MaskCreaseWidth;
				DispParams->MaskCreaseRange = Params.MaskCreaseRange;
				DispParams->MaskGain = Params.MaskGain;
				DispParams->MaskSharpness = Params.MaskSharpness;
				DispParams->MaskPalmSplit = Params.MaskPalmSplit;
				DispParams->MaskPalmarBase = Params.MaskPalmarBase;
				DispParams->MaskPalmarCompress = Params.MaskPalmarCompress;
				DispParams->MaskPalmarIron = Params.MaskPalmarIron;
				DispParams->MaskDorsalBase = Params.MaskDorsalBase;
				DispParams->MaskDorsalIron = Params.MaskDorsalIron;
				DispParams->DorsalGather = Params.DorsalGather;
				DispParams->DorsalGatherSpacing = FMath::Max(Params.DorsalGatherSpacing, 0.05f);
				DispParams->DorsalGatherReach = FMath::Max(Params.DorsalGatherReach, 0.1f);
				DispParams->DorsalGatherBase = Params.DorsalGatherBase;
				DispParams->DorsalGatherIron = Params.DorsalGatherIron;
				DispParams->PalmarPadHeight = Params.PalmarPadHeight;
				DispParams->PalmarPadDist = Params.PalmarPadDist;
				DispParams->PalmarPadWidth = Params.PalmarPadWidth;
				DispParams->PalmarFold2Depth = Params.PalmarFold2Depth;
				DispParams->PalmarFold2Dist = Params.PalmarFold2Dist;
				DispParams->PalmarFold2Width = Params.PalmarFold2Width;
				DispParams->PalmarCreaseDeepen = Params.PalmarCreaseDeepen;
				DispParams->PalmarFoldBendFull = Params.PalmarFoldBendFull;
				DispParams->WrinkleMask = bMask ? MaskRHI : GBlackTexture->TextureRHI.GetReference();
				DispParams->WrinkleMaskSampler = TStaticSamplerState<SF_Bilinear, AM_Clamp, AM_Clamp, AM_Clamp>::GetRHI();
				DispParams->UVInputBuffer = UVSRV ? UVSRV : GNullColorVertexBuffer.VertexBufferSRV.GetReference();

				// Phase 7: contact bulge needs the animated bone table and the capsules, both in section order.
				TArray<FSkinBoneTransform> SectionAnimBones = SectionTable(Section, AllBones);
				TArray<FVector4f> SectionCapsules;
				SectionCapsules.SetNumZeroed(FMath::Max(Section.BoneMap.Num(), 1) * 2);
				bool bHaveCapsules = Params.bContactBulge && AllCapsules.Num() > 0;
				for (int32 i = 0; i < Section.BoneMap.Num() && bHaveCapsules; ++i)
				{
					const int32 BoneIndex = Section.BoneMap[i];
					if (!AllCapsules.IsValidIndex(BoneIndex))
					{
						continue;
					}
					const FPianoHandBoneCapsule& Cap = AllCapsules[BoneIndex];
					// the parent's SECTION index, or -1 if the parent is not in this section
					int32 ParentSection = INDEX_NONE;
					if (Cap.Parent != INDEX_NONE)
					{
						ParentSection = Section.BoneMap.IndexOfByKey((FBoneIndexType)Cap.Parent);
					}
					SectionCapsules[i * 2 + 0] = FVector4f(Cap.Origin, Cap.Radius * Params.CapsuleRadiusScale);
					SectionCapsules[i * 2 + 1] = FVector4f(Cap.End, (float)ParentSection);
				}
				FRDGBufferRef AnimBoneBuffer = CreateStructuredBuffer(GraphBuilder, TEXT("PianoHandDisplaceBones"), SectionAnimBones);
				FRDGBufferRef CapsuleBuffer = CreateStructuredBuffer(GraphBuilder, TEXT("PianoHandBoneCapsules"), SectionCapsules);
				DispParams->BoneTransforms = GraphBuilder.CreateSRV(AnimBoneBuffer);
				DispParams->BoneCapsules = GraphBuilder.CreateSRV(CapsuleBuffer);
				DispParams->bContactBulge = bHaveCapsules ? 1u : 0u;
				DispParams->ContactMargin = Params.ContactMargin;
				DispParams->BulgeGain = Params.BulgeGain;
				DispParams->BulgeReach = Params.BulgeReach;
				DispParams->BulgeSpread = Params.BulgeSpread;
				DispParams->BendStart = FMath::DegreesToRadians(Params.BendStart);
				DispParams->BendFull = FMath::DegreesToRadians(FMath::Max(Params.BendFull, Params.BendStart + 1.0f));
				DispParams->CapsuleRadiusScale = Params.CapsuleRadiusScale;
				DispParams->DorsalTighten = Params.DorsalTighten;
				DispParams->RefPoseInverses = GraphBuilder.CreateSRV(RefInvBuffer);
				DispParams->VertexTensor = VertexTensorSRV;
				DispParams->RelaxStateIn = RelaxStateSRV;
				DispParams->WeldCanon = WeldCanonSRV;
				DispParams->PositionBufferUAV = PositionUAV;
				DispParams->TangentBufferUAV = TangentUAV;
				DispParams->ColorBufferUAV = DetailColorUAV;

				FComputeShaderUtils::AddPass(
					GraphBuilder,
					RDG_EVENT_NAME("PianoHand.DetailDisplace(section %d, %u verts)", SectionIndex, Section.NumVertices),
					DisplaceShader,
					DispParams,
					FComputeShaderUtils::GetGroupCount(Section.NumVertices, FPianoHandDetailDisplaceCS::ThreadGroupSize));
			}

			// Rebuild the tangent frame from the displaced surface, otherwise the folds are invisible.
			if (Params.bRecomputeNormals && IndexSRV != nullptr)
			{
				FRDGBufferRef NormalAccum = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(sizeof(int32), FMath::Max(NumLodVertices * 3u, 1u)), TEXT("PianoHandNormalAccum"));
				FRDGBufferUAVRef NormalAccumUAV = GraphBuilder.CreateUAV(NormalAccum);
				AddClearUAVPass(GraphBuilder, NormalAccumUAV, 0u);

				TShaderMapRef<FPianoHandNormalAccumulateCS> NormalAccShader(GetGlobalShaderMap(GMaxRHIFeatureLevel));
				for (int32 SectionIndex = 0; SectionIndex < Lod.RenderSections.Num(); ++SectionIndex)
				{
					const FSkelMeshRenderSection& Section = Lod.RenderSections[SectionIndex];
					if (Section.bDisabled || Section.NumTriangles == 0)
					{
						continue;
					}

					FPianoHandNormalAccumulateCS::FParameters* NAParams = GraphBuilder.AllocParameters<FPianoHandNormalAccumulateCS::FParameters>();
					NAParams->NumTriangles = Section.NumTriangles;
					NAParams->BaseIndex = Section.BaseIndex;
					NAParams->IndexBuffer = WeldIndexSRV;
					NAParams->DisplacedPositionBuffer = SkinnedPositionSRV;
					NAParams->NormalAccum = NormalAccumUAV;

					FComputeShaderUtils::AddPass(
						GraphBuilder,
						RDG_EVENT_NAME("PianoHand.NormalAccumulate(section %d, %u tris)", SectionIndex, Section.NumTriangles),
						NormalAccShader,
						NAParams,
						FComputeShaderUtils::GetGroupCount(Section.NumTriangles, FPianoHandNormalAccumulateCS::ThreadGroupSize));
				}

				TShaderMapRef<FPianoHandNormalResolveCS> NormalResShader(GetGlobalShaderMap(GMaxRHIFeatureLevel));
				FPianoHandNormalResolveCS::FParameters* NRParams = GraphBuilder.AllocParameters<FPianoHandNormalResolveCS::FParameters>();
				NRParams->NumLodVertices = NumLodVertices;
				NRParams->NormalAccumIn = GraphBuilder.CreateSRV(NormalAccum);
				NRParams->WeldCanon = WeldCanonSRV;
				NRParams->TangentBufferUAV = TangentUAV;

				FComputeShaderUtils::AddPass(
					GraphBuilder,
					RDG_EVENT_NAME("PianoHand.NormalResolve(%u verts)", NumLodVertices),
					NormalResShader,
					NRParams,
					FComputeShaderUtils::GetGroupCount(NumLodVertices, FPianoHandNormalResolveCS::ThreadGroupSize));
			}
		}

		// Phase 8 debug: paint the implicit state into the vertex colour, after everything else wrote it.
		if (bImplicit && Params.ImplicitDebugMode != 0 && ColorBuffer != nullptr && ImplicitPrePos != nullptr)
		{
			TShaderMapRef<FPianoHandImplicitDebugCS> DebugShader(GetGlobalShaderMap(GMaxRHIFeatureLevel));
			FPianoHandImplicitDebugCS::FParameters* DP = GraphBuilder.AllocParameters<FPianoHandImplicitDebugCS::FParameters>();
			DP->Common = ImplicitDebugCommon;
			DP->DebugMode = (uint32)Params.ImplicitDebugMode;
			DP->PositionIn = GraphBuilder.CreateSRV(PositionBuffer, PF_R32_FLOAT);
			DP->PrePosition = GraphBuilder.CreateSRV(ImplicitPrePos, PF_R32_FLOAT);
			DP->VertexGrad = GraphBuilder.CreateUAV(ImplicitGradBuffer);
			DP->VertexState = GraphBuilder.CreateUAV(ImplicitStateBuffer);
			DP->ColorBufferUAV = GraphBuilder.CreateUAV(ColorBuffer, PF_R8G8B8A8);
			FComputeShaderUtils::AddPass(GraphBuilder, RDG_EVENT_NAME("PianoHand.ImplicitDebug"), DebugShader, DP,
				FComputeShaderUtils::GetGroupCount(NumLodVerticesEarly, FPianoHandImplicitDebugCS::ThreadGroupSize));
		}

		// Phase 8: the implicit projection moved vertices; without the detail pass nothing rebuilt the normals yet.
		if (bImplicit && Params.bRecomputeNormals && IndexSRV != nullptr && !(Params.bDetailDisplacement && VertexTensorBuffer != nullptr && SkinnedPositionSRV != nullptr && ColorBuffer != nullptr))
		{
			FRDGBufferSRVRef ImplicitPosSRV = GraphBuilder.CreateSRV(PositionBuffer, PF_R32_FLOAT);
			FRDGBufferRef NormalAccum = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(sizeof(int32), FMath::Max(NumLodVerticesEarly * 3u, 1u)), TEXT("PianoHandNormalAccumImplicit"));
			FRDGBufferUAVRef NormalAccumUAV = GraphBuilder.CreateUAV(NormalAccum);
			AddClearUAVPass(GraphBuilder, NormalAccumUAV, 0u);
			TShaderMapRef<FPianoHandNormalAccumulateCS> NormalAccShader(GetGlobalShaderMap(GMaxRHIFeatureLevel));
			for (int32 SectionIndex = 0; SectionIndex < Lod.RenderSections.Num(); ++SectionIndex)
			{
				const FSkelMeshRenderSection& Section = Lod.RenderSections[SectionIndex];
				if (Section.bDisabled || Section.NumTriangles == 0) { continue; }
				FPianoHandNormalAccumulateCS::FParameters* NAParams = GraphBuilder.AllocParameters<FPianoHandNormalAccumulateCS::FParameters>();
				NAParams->NumTriangles = Section.NumTriangles;
				NAParams->BaseIndex = Section.BaseIndex;
				NAParams->IndexBuffer = WeldIndexSRV;
				NAParams->DisplacedPositionBuffer = ImplicitPosSRV;
				NAParams->NormalAccum = NormalAccumUAV;
				FComputeShaderUtils::AddPass(GraphBuilder, RDG_EVENT_NAME("PianoHand.NormalAccumulateImplicit(section %d)", SectionIndex), NormalAccShader, NAParams,
					FComputeShaderUtils::GetGroupCount(Section.NumTriangles, FPianoHandNormalAccumulateCS::ThreadGroupSize));
			}
			TShaderMapRef<FPianoHandNormalResolveCS> NormalResShader(GetGlobalShaderMap(GMaxRHIFeatureLevel));
			FPianoHandNormalResolveCS::FParameters* NRParams = GraphBuilder.AllocParameters<FPianoHandNormalResolveCS::FParameters>();
			NRParams->NumLodVertices = NumLodVerticesEarly;
			NRParams->NormalAccumIn = GraphBuilder.CreateSRV(NormalAccum);
			NRParams->WeldCanon = WeldCanonSRV;
			NRParams->TangentBufferUAV = TangentUAV;
			FComputeShaderUtils::AddPass(GraphBuilder, RDG_EVENT_NAME("PianoHand.NormalResolveImplicit"), NormalResShader, NRParams,
				FComputeShaderUtils::GetGroupCount(NumLodVerticesEarly, FPianoHandNormalResolveCS::ThreadGroupSize));
		}

		FSkeletalMeshDeformerHelpers::UpdateVertexFactoryBufferOverrides(GraphBuilder, MeshObject, LodIndex, bInvalidatePreviousPosition);
		ExternalAccessQueue.Submit(GraphBuilder);
		GraphBuilder.Execute();
		return true;
	}
}

// ---------------------------------------------------------------------------
// Phase 5 - proportions: bone lookup and per-bone scales
// ---------------------------------------------------------------------------

namespace PianoHandProportions
{
	static const TCHAR* FingerNames[5] = { TEXT("thumb"), TEXT("index"), TEXT("middle"), TEXT("ring"), TEXT("pinky") };

	/** "_r" / "_l" from the hand bone that exists on this skeleton; empty if neither does. */
	static FString SideSuffix(const USkinnedMeshComponent* Component)
	{
		if (Component == nullptr) { return FString(); }
		if (Component->GetBoneIndex(TEXT("hand_r")) != INDEX_NONE) { return TEXT("_r"); }
		if (Component->GetBoneIndex(TEXT("hand_l")) != INDEX_NONE) { return TEXT("_l"); }
		return FString();
	}

	/** True if Bone is Root or one of its descendants. */
	static bool IsInSubtree(const FReferenceSkeleton& RefSkel, int32 Bone, int32 Root)
	{
		for (int32 Guard = 0; Bone != INDEX_NONE && Guard < 256; ++Guard)
		{
			if (Bone == Root) { return true; }
			Bone = RefSkel.GetParentIndex(Bone);
		}
		return false;
	}

	void BuildBoneScales(const USkinnedMeshComponent* Component, const FPianoHandProportions& P, TArray<FVector3f>& OutScale)
	{
		const int32 NumBones = Component ? Component->GetNumBones() : 0;
		OutScale.Init(FVector3f::OneVector, NumBones);
		if (NumBones == 0) { return; }

		auto Mul = [&OutScale](int32 Bone, const FVector3f& S)
		{
			if (OutScale.IsValidIndex(Bone)) { OutScale[Bone] *= S; }
		};
		// MetaHuman / UE bone frames: x runs along the bone, +y is the palmar side, z across the finger.
		const FPianoHandFingerProportions* Fingers[5] = { &P.Thumb, &P.Index, &P.Middle, &P.Ring, &P.Pinky };
		for (int32 F = 0; F < 5; ++F)
		{
			const float T = Fingers[F]->Thickness;
			Mul(UPianoHandSkinningLibrary::FindHandBone(Component, F, 0), FVector3f(Fingers[F]->Proximal, T, T));
			Mul(UPianoHandSkinningLibrary::FindHandBone(Component, F, 1), FVector3f(Fingers[F]->Middle, T, T));
			Mul(UPianoHandSkinningLibrary::FindHandBone(Component, F, 2), FVector3f(Fingers[F]->Distal, T, T));
			Mul(UPianoHandSkinningLibrary::FindHandBone(Component, F, 3), FVector3f(P.PalmLength, P.PalmThickness, P.PalmWidth));
		}
		const int32 Root = UPianoHandSkinningLibrary::FindHandRootBone(Component);
		Mul(Root, FVector3f(P.PalmLength, P.PalmThickness, P.PalmWidth));

		if (!FMath::IsNearlyEqual(P.OverallScale, 1.0f) && Root != INDEX_NONE)
		{
			if (const USkinnedAsset* Asset = Component->GetSkinnedAsset())
			{
				const FReferenceSkeleton& RefSkel = Asset->GetRefSkeleton();
				for (int32 B = 0; B < NumBones; ++B)
				{
					if (IsInSubtree(RefSkel, B, Root))
					{
						Mul(B, FVector3f(P.OverallScale));
					}
				}
			}
		}
	}

	/**
	 * Phase 7 - measure a capsule per bone from the rest mesh: origin and axis end (the first child's
	 * origin, or the bone continued by its own length) in component space, and the radius as the 65th
	 * percentile of the distance of the vertices it dominates from its axis. CPU access to positions and
	 * skin weights is needed (the editor keeps both); without it the capsules stay empty and the contact
	 * bulge is off.
	 */
	void BuildCapsules(const USkinnedMeshComponent* Component, TArray<FPianoHandBoneCapsule>& Out)
	{
		Out.Reset();
		const USkinnedAsset* Asset = Component ? Component->GetSkinnedAsset() : nullptr;
		if (Asset == nullptr) { return; }
		const FReferenceSkeleton& RefSkel = Asset->GetRefSkeleton();
		TArray<FTransform> CS;
		RefPoseComponentSpace(Asset, CS);
		const int32 NumBones = CS.Num();
		Out.SetNum(NumBones);
		TArray<TArray<float>> Dists;
		Dists.SetNum(NumBones);
		for (int32 B = 0; B < NumBones; ++B)
		{
			Out[B].Origin = FVector3f(CS[B].GetTranslation());
			Out[B].Parent = RefSkel.GetParentIndex(B);
		}
		// axis end = first child's origin; leaves continue along the bone (-X local) by the parent segment length
		for (int32 B = 0; B < NumBones; ++B)
		{
			int32 FirstChild = INDEX_NONE;
			for (int32 C = B + 1; C < NumBones; ++C)
			{
				if (RefSkel.GetParentIndex(C) == B) { FirstChild = C; break; }
			}
			if (FirstChild != INDEX_NONE)
			{
				Out[B].End = Out[FirstChild].Origin;
			}
			else
			{
				const float ParentLen = (Out[B].Parent != INDEX_NONE) ? (Out[B].Origin - Out[Out[B].Parent].Origin).Size() : 2.0f;
				const FVector3f Dir = FVector3f(CS[B].TransformVectorNoScale(FVector(-1, 0, 0))).GetSafeNormal();
				Out[B].End = Out[B].Origin + Dir * FMath::Max(ParentLen * 0.8f, 0.5f);
			}
		}
		const FSkeletalMeshRenderData* RenderData = Asset->GetResourceForRendering();
		if (RenderData == nullptr || RenderData->LODRenderData.Num() == 0) { Out.Reset(); return; }
		const FSkeletalMeshLODRenderData& Lod = RenderData->LODRenderData[0];
		const FPositionVertexBuffer& Positions = Lod.StaticVertexBuffers.PositionVertexBuffer;
		const FSkinWeightVertexBuffer* Weights = Lod.GetSkinWeightVertexBuffer();
		if (!Positions.GetAllowCPUAccess() || Weights == nullptr || !Weights->GetNeedsCPUAccess() || Positions.GetNumVertices() == 0)
		{
			UE_LOG(LogPianoHand, Warning, TEXT("[SkinDeformer] capsules: no CPU access to positions / weights, contact bulge disabled."));
			Out.Reset();
			return;
		}
		for (const FSkelMeshRenderSection& Section : Lod.RenderSections)
		{
			for (uint32 V = Section.BaseVertexIndex; V < Section.BaseVertexIndex + Section.NumVertices && V < Positions.GetNumVertices(); ++V)
			{
				const FSkinWeightInfo W = Weights->GetVertexSkinWeights(V);
				int32 Best = INDEX_NONE; uint16 BestW = 0;
				for (int32 I = 0; I < MAX_TOTAL_INFLUENCES; ++I)
				{
					if (W.InfluenceWeights[I] > BestW)
					{
						BestW = W.InfluenceWeights[I];
						Best = Section.BoneMap.IsValidIndex(W.InfluenceBones[I]) ? (int32)Section.BoneMap[W.InfluenceBones[I]] : INDEX_NONE;
					}
				}
				if (Best == INDEX_NONE || !Out.IsValidIndex(Best)) { continue; }
				const FVector3f P = Positions.VertexPosition(V);
				const FVector3f A = Out[Best].Origin, E = Out[Best].End;
				const FVector3f AB = E - A;
				const float L2 = FMath::Max(AB.SizeSquared(), 1e-6f);
				const float T = FMath::Clamp(FVector3f::DotProduct(P - A, AB) / L2, 0.0f, 1.0f);
				Dists[Best].Add((P - (A + AB * T)).Size());
			}
		}
		int32 Measured = 0;
		for (int32 B = 0; B < NumBones; ++B)
		{
			// Only the finger joints get a contact field: the phalanges, and the thumb's two distal
			// bones. The thumb CMC (thumb_01 against the hand) and the metacarpals are not hinge joints
			// and their "capsules" are a poor fit - the diff images showed the thumb base bulging.
			const FString Name = RefSkel.GetBoneName(B).ToString().ToLower();
			const bool bFingerJoint = (Name.Contains(TEXT("_01_")) || Name.Contains(TEXT("_02_")) || Name.Contains(TEXT("_03_")))
				&& !Name.Contains(TEXT("thumb_01")) && !Name.Contains(TEXT("metacarpal"));
			if (!bFingerJoint)
			{
				continue;
			}
			if (Dists[B].Num() >= 8)
			{
				Dists[B].Sort();
				Out[B].Radius = Dists[B][FMath::Clamp((int32)(Dists[B].Num() * 0.65f), 0, Dists[B].Num() - 1)];
				++Measured;
			}
		}
		UE_LOG(LogPianoHand, Display, TEXT("[SkinDeformer] capsules: %d of %d bones measured from %u vertices."), Measured, NumBones, Positions.GetNumVertices());
	}

	/** Reference pose in component space, composed from the local ref pose. */
	static void RefPoseComponentSpace(const USkinnedAsset* Asset, TArray<FTransform>& Out)
	{
		const FReferenceSkeleton& RefSkel = Asset->GetRefSkeleton();
		const TArray<FTransform>& Local = RefSkel.GetRefBonePose();
		Out.SetNum(Local.Num());
		for (int32 B = 0; B < Local.Num(); ++B)
		{
			const int32 Parent = RefSkel.GetParentIndex(B);
			Out[B] = (Parent >= 0 && Parent < B) ? Local[B] * Out[Parent] : Local[B];
		}
	}
}

// ---------------------------------------------------------------------------
// UPianoHandSkinDeformer
// ---------------------------------------------------------------------------

UMeshDeformerInstanceSettings* UPianoHandSkinDeformer::CreateSettingsInstance(UMeshComponent* InMeshComponent)
{
	return NewObject<UPianoHandSkinDeformerInstanceSettings>(InMeshComponent, NAME_None, RF_Transient);
}

UMeshDeformerInstance* UPianoHandSkinDeformer::CreateInstance(UMeshComponent* InMeshComponent, UMeshDeformerInstanceSettings* InSettings)
{
	USkinnedMeshComponent* SkinnedComponent = Cast<USkinnedMeshComponent>(InMeshComponent);
	if (SkinnedComponent == nullptr)
	{
		return nullptr;
	}

	UPianoHandSkinDeformerInstance* Instance = NewObject<UPianoHandSkinDeformerInstance>(InMeshComponent, NAME_None, RF_Transient);
	Instance->Init(SkinnedComponent, this);
	return Instance;
}

// ---------------------------------------------------------------------------
// UPianoHandSkinDeformerInstance
// ---------------------------------------------------------------------------

void UPianoHandSkinDeformerInstance::Init(USkinnedMeshComponent* InComponent, UPianoHandSkinDeformer* InDeformer)
{
	Component = InComponent;
	Deformer = InDeformer;
	SkinMode = InDeformer ? InDeformer->SkinMode : EPianoHandSkinMode::LinearBlend;
	RenderState = MakeShared<FPianoHandDeformerRenderState, ESPMode::ThreadSafe>();
}

void UPianoHandSkinDeformerInstance::AllocateResources()
{
}

void UPianoHandSkinDeformerInstance::ReleaseResources()
{
	USkinnedMeshComponent* SkinnedComponent = Component.Get();
	FSkeletalMeshObject* MeshObject = SkinnedComponent ? SkinnedComponent->MeshObject : nullptr;
	if (MeshObject != nullptr && RenderState.IsValid())
	{
		ENQUEUE_RENDER_COMMAND(PianoHandSkinDeformerRelease)([MeshObject, State = RenderState](FRHICommandListImmediate& RHICmdList)
		{
			if (State->LastLodIndex != INDEX_NONE)
			{
				FSkeletalMeshDeformerHelpers::ResetVertexFactoryBufferOverrides(MeshObject, State->LastLodIndex);
				State->LastLodIndex = INDEX_NONE;
			}
		});
	}
}

void UPianoHandSkinDeformerInstance::EnqueueWork(FEnqueueWorkDesc const& InDesc)
{
	USkinnedMeshComponent* SkinnedComponent = Component.Get();
	FSkeletalMeshObject* MeshObject = SkinnedComponent ? SkinnedComponent->MeshObject : nullptr;
	USkeletalMesh* SkeletalMesh = SkinnedComponent ? Cast<USkeletalMesh>(SkinnedComponent->GetSkinnedAsset()) : nullptr;

	if (MeshObject == nullptr || SkeletalMesh == nullptr || !RenderState.IsValid())
	{
		ENQUEUE_RENDER_COMMAND(PianoHandSkinDeformerFallback)([Fallback = InDesc.FallbackDelegate](FRHICommandListImmediate& RHICmdList)
		{
			Fallback.ExecuteIfBound();
		});
		return;
	}

	// RefPoseInverse * ComponentSpace for every bone of the skeleton (UE row-vector convention).
	const TArray<FTransform>& ComponentSpaceTransforms = SkinnedComponent->GetComponentSpaceTransforms();
	const TArray<FMatrix44f>& RefBasesInvMatrix = SkeletalMesh->GetRefBasesInvMatrix();
	const int32 NumBones = FMath::Min(ComponentSpaceTransforms.Num(), RefBasesInvMatrix.Num());

	const UPianoHandSkinDeformer* Source = Deformer.Get();
	const bool bProportioned = Source != nullptr && !Source->Proportions.IsIdentity();

	TArray<FSkinBoneTransform> Bones;
	Bones.SetNumUninitialized(NumBones);
	// Normals go through the inverse-transpose; identical to Bones unless a bone is scaled (proportions).
	TArray<FSkinBoneTransform> BoneNormals;
	BoneNormals.SetNumUninitialized(NumBones);
	// Phase 3 also needs RefPoseInverse on its own, to get rest-pose bone-local coordinates.
	TArray<FSkinBoneTransform> RefInverses;
	RefInverses.SetNumUninitialized(NumBones);
	// Phase 5: proportion-only transforms (RefPoseInverse * Scale * scaled ref pose) that skin the rest
	// pose into the strain reference. Empty when the proportions are identity.
	TArray<FSkinBoneTransform> RestBones;
	TArray<FSkinBoneTransform> RestBoneNormals;

	if (!bProportioned)
	{
		for (int32 BoneIndex = 0; BoneIndex < NumBones; ++BoneIndex)
		{
			const FMatrix44f BoneMatrix = RefBasesInvMatrix[BoneIndex] * FMatrix44f(ComponentSpaceTransforms[BoneIndex].ToMatrixWithScale());
			Bones[BoneIndex] = FSkinBoneTransform::FromMatrix(BoneMatrix);
			BoneNormals[BoneIndex] = Bones[BoneIndex];
			RefInverses[BoneIndex] = FSkinBoneTransform::FromMatrix(RefBasesInvMatrix[BoneIndex]);
		}
	}
	else
	{
		// Every scale lives in its bone's local frame (x along the bone, y palmar, z across). A child's
		// local translation is expressed in its PARENT's frame, so scaling the parent moves the child
		// joint with the scaled segment; the child's own frame is not inherited-scaled (no compounding
		// down the chain), it carries only its own scale. Component space is rebuilt parent-first with
		// those scaled translations, for the animated pose and for the reference pose alike.
		TArray<FVector3f> Scale;
		PianoHandProportions::BuildBoneScales(SkinnedComponent, Source->Proportions, Scale);
		const FReferenceSkeleton& RefSkel = SkeletalMesh->GetRefSkeleton();
		const TArray<FTransform>& RefLocalPose = RefSkel.GetRefBonePose();

		TArray<FTransform> AnimCS, RefCS;
		AnimCS.SetNumUninitialized(NumBones);
		RefCS.SetNumUninitialized(NumBones);
		RestBones.SetNumUninitialized(NumBones);
		RestBoneNormals.SetNumUninitialized(NumBones);
		for (int32 BoneIndex = 0; BoneIndex < NumBones; ++BoneIndex)
		{
			const int32 Parent = RefSkel.GetParentIndex(BoneIndex);
			FTransform LocalAnim = (Parent >= 0 && Parent < BoneIndex)
				? ComponentSpaceTransforms[BoneIndex].GetRelativeTransform(ComponentSpaceTransforms[Parent])
				: ComponentSpaceTransforms[BoneIndex];
			FTransform LocalRef = RefLocalPose.IsValidIndex(BoneIndex) ? RefLocalPose[BoneIndex] : FTransform::Identity;
			if (Parent >= 0 && Parent < BoneIndex)
			{
				const FVector ParentScale(Scale[Parent]);
				LocalAnim.SetTranslation(LocalAnim.GetTranslation() * ParentScale);
				LocalRef.SetTranslation(LocalRef.GetTranslation() * ParentScale);
				AnimCS[BoneIndex] = LocalAnim * AnimCS[Parent];
				RefCS[BoneIndex] = LocalRef * RefCS[Parent];
			}
			else
			{
				AnimCS[BoneIndex] = LocalAnim;
				RefCS[BoneIndex] = LocalRef;
			}
			const FMatrix44f S = FScaleMatrix44f(Scale[BoneIndex]);
			const FMatrix44f M = RefBasesInvMatrix[BoneIndex] * S * FMatrix44f(AnimCS[BoneIndex].ToMatrixWithScale());
			const FMatrix44f M0 = RefBasesInvMatrix[BoneIndex] * S * FMatrix44f(RefCS[BoneIndex].ToMatrixWithScale());
			Bones[BoneIndex] = FSkinBoneTransform::FromMatrix(M);
			BoneNormals[BoneIndex] = FSkinBoneTransform::FromMatrix(M.Inverse().GetTransposed());
			RestBones[BoneIndex] = FSkinBoneTransform::FromMatrix(M0);
			RestBoneNormals[BoneIndex] = FSkinBoneTransform::FromMatrix(M0.Inverse().GetTransposed());
			RefInverses[BoneIndex] = FSkinBoneTransform::FromMatrix(RefBasesInvMatrix[BoneIndex]);
		}
	}

	++EnqueuedFrames;

	// Phase 7: capsules are measured once per mesh.
	if (Source != nullptr && Source->bContactBulge && (CapsuleCache.Asset.Get() != SkeletalMesh || CapsuleCache.Capsules.Num() == 0))
	{
		PianoHandProportions::BuildCapsules(SkinnedComponent, CapsuleCache.Capsules);
		CapsuleCache.Asset = SkeletalMesh;
	}
	TArray<FPianoHandBoneCapsule> Capsules = (Source != nullptr && Source->bContactBulge) ? CapsuleCache.Capsules : TArray<FPianoHandBoneCapsule>();

	// Phase 8: implicit fields are built once per mesh (and rebuilt when the sample counts or the serial change).
	TSharedPtr<const FPianoHandImplicitData, ESPMode::ThreadSafe> ImplicitForFrame;
	TArray<FSkinBoneTransform> PrimInverses;
	TArray<FSkinBoneTransform> PrimForward;
	TArray<float> PairBend;
	if (Source != nullptr && Source->bImplicitSkinning)
	{
		const bool bStale = !ImplicitData.IsValid() || ImplicitAsset.Get() != SkeletalMesh
			|| ImplicitSamplesBuilt != Source->ImplicitSamplesPerBone || ImplicitPalmSamplesBuilt != Source->ImplicitPalmSamples
			|| ImplicitSerialBuilt != Source->ImplicitBuildSerial;
		if (bStale)
		{
			TSharedPtr<FPianoHandImplicitData, ESPMode::ThreadSafe> Data = MakeShared<FPianoHandImplicitData, ESPMode::ThreadSafe>();
			FPianoHandImplicitBuildSettings Settings;
			Settings.SamplesPerBone = Source->ImplicitSamplesPerBone;
			Settings.PalmSamples = Source->ImplicitPalmSamples;
			const double T0 = FPlatformTime::Seconds();
			PianoHandImplicit::Build(SkinnedComponent, Settings, *Data);
			static uint32 GBuildCounter = 0;
			Data->BuildId = ++GBuildCounter;
			UE_LOG(LogPianoHand, Display, TEXT("[SkinDeformer] implicit build %s in %.2fs: %s"), Data->bValid ? TEXT("ok") : TEXT("FAILED"), FPlatformTime::Seconds() - T0, *Data->Summary);
			ImplicitData = Data;
			ImplicitAsset = SkeletalMesh;
			ImplicitSamplesBuilt = Source->ImplicitSamplesPerBone;
			ImplicitPalmSamplesBuilt = Source->ImplicitPalmSamples;
			ImplicitSerialBuilt = Source->ImplicitBuildSerial;
		}
		if (ImplicitData.IsValid() && ImplicitData->bValid)
		{
			ImplicitForFrame = ImplicitData;
			// bend angle of every joint pair this frame: rotation of (R_a^-1 R_b) away from its rest value
			PairBend.SetNumZeroed(ImplicitData->PrimNeighbours.Num());
			for (int32 P = 0; P < ImplicitData->PrimMeta.Num(); ++P)
			{
				const FUintVector4& Meta = ImplicitData->PrimMeta[P];
				const int32 BoneA = ImplicitData->PrimBone[P];
				for (uint32 N = 0; N < Meta.Z; ++N)
				{
					const int32 Entry = (int32)(Meta.W + N);
					const int32 PrimB = ImplicitData->PrimNeighbours.IsValidIndex(Entry) ? ImplicitData->PrimNeighbours[Entry].X : INDEX_NONE;
					if (PrimB < 0 || !ImplicitData->PrimBone.IsValidIndex(PrimB) || !ImplicitData->PairRestRelative.IsValidIndex(Entry)) { continue; }
					const int32 BoneB = ImplicitData->PrimBone[PrimB];
					if (!ComponentSpaceTransforms.IsValidIndex(BoneA) || !ComponentSpaceTransforms.IsValidIndex(BoneB)) { continue; }
					const FQuat4f RA(ComponentSpaceTransforms[BoneA].GetRotation());
					const FQuat4f RB(ComponentSpaceTransforms[BoneB].GetRotation());
					const FQuat4f Rel = RA.Inverse() * RB;
					const FQuat4f Delta = ImplicitData->PairRestRelative[Entry].Inverse() * Rel;
					PairBend[Entry] = FMath::Abs(Delta.GetNormalized().GetAngle());
					if (PairBend[Entry] > PI) { PairBend[Entry] = 2.0f * PI - PairBend[Entry]; }
				}
			}
			PrimInverses.SetNumUninitialized(ImplicitData->PrimBone.Num());
			PrimForward.SetNumUninitialized(ImplicitData->PrimBone.Num());
			for (int32 P = 0; P < ImplicitData->PrimBone.Num(); ++P)
			{
				const int32 B = ImplicitData->PrimBone[P];
				FMatrix44f M = FMatrix44f::Identity;
				if (Bones.IsValidIndex(B))
				{
					M = Bones[B].ToMatrix();
				}
				PrimInverses[P] = FSkinBoneTransform::FromMatrix(M.Inverse());
				PrimForward[P] = FSkinBoneTransform::FromMatrix(M);
			}
		}
	}

	// Re-read the deformer properties every frame so Details-panel / Python edits apply live.
	FPianoHandDeformerFrameParams FrameParams;
	if (Source != nullptr)
	{
		FrameParams.Mode = Source->SkinMode;
		FrameParams.bComputeTension = Source->bComputeTension;
		FrameParams.TensionScale = Source->TensionScale;
		FrameParams.TensorSmoothIterations = Source->TensorSmoothIterations;
		FrameParams.TensorSmoothLambda = Source->TensorSmoothLambda;
		FrameParams.bDetailDisplacement = Source->bDetailDisplacement;
		FrameParams.bRecomputeNormals = Source->bRecomputeNormals;
		FrameParams.VolumeBulge = Source->VolumeBulge;
		FrameParams.CreaseDepth = Source->CreaseDepth;
		FrameParams.CreaseSharpness = Source->CreaseSharpness;
		FrameParams.CreaseCompressionGain = Source->CreaseCompressionGain;
		FrameParams.WrinkleAmplitude = Source->WrinkleAmplitude;
		FrameParams.WrinkleFrequency = Source->WrinkleFrequency;
		FrameParams.CreaseStretchRelief = Source->CreaseStretchRelief;
		FrameParams.RelaxGain = Source->RelaxGain;
		FrameParams.RelaxTau = Source->RelaxTau;
		FrameParams.RelaxCreaseGain = Source->RelaxCreaseGain;
		FrameParams.WrinkleMaskResource = Source->WrinkleMask ? Source->WrinkleMask->GetResource() : nullptr;
		FrameParams.MaskCreaseDepth = Source->MaskCreaseDepth;
		FrameParams.MaskCreaseWidth = Source->MaskCreaseWidth;
		FrameParams.MaskCreaseRange = Source->MaskCreaseRange;
		FrameParams.MaskGain = Source->MaskGain;
		FrameParams.MaskSharpness = Source->MaskSharpness;
		FrameParams.MaskPalmSplit = Source->MaskPalmSplit;
		FrameParams.MaskPalmarBase = Source->MaskPalmarBase;
		FrameParams.MaskPalmarCompress = Source->MaskPalmarCompress;
		FrameParams.MaskPalmarIron = Source->MaskPalmarIron;
		FrameParams.MaskDorsalBase = Source->MaskDorsalBase;
		FrameParams.MaskDorsalIron = Source->MaskDorsalIron;
		FrameParams.DorsalGather = Source->DorsalGather;
		FrameParams.DorsalGatherSpacing = Source->DorsalGatherSpacing;
		FrameParams.DorsalGatherReach = Source->DorsalGatherReach;
		FrameParams.DorsalGatherBase = Source->DorsalGatherBase;
		FrameParams.DorsalGatherIron = Source->DorsalGatherIron;
		FrameParams.PalmarPadHeight = Source->PalmarPadHeight;
		FrameParams.PalmarPadDist = Source->PalmarPadDist;
		FrameParams.PalmarPadWidth = Source->PalmarPadWidth;
		FrameParams.PalmarFold2Depth = Source->PalmarFold2Depth;
		FrameParams.PalmarFold2Dist = Source->PalmarFold2Dist;
		FrameParams.PalmarFold2Width = Source->PalmarFold2Width;
		FrameParams.PalmarCreaseDeepen = Source->PalmarCreaseDeepen;
		FrameParams.PalmarFoldBendFull = Source->PalmarFoldBendFull;
		FrameParams.bProportioned = bProportioned;
		FrameParams.bContactBulge = Source->bContactBulge;
		FrameParams.ContactMargin = Source->ContactMargin;
		FrameParams.BulgeGain = Source->BulgeGain;
		FrameParams.BulgeReach = Source->BulgeReach;
		FrameParams.BulgeSpread = Source->BulgeSpread;
		FrameParams.BendStart = Source->BendStart;
		FrameParams.BendFull = Source->BendFull;
		FrameParams.CapsuleRadiusScale = Source->CapsuleRadiusScale;
		FrameParams.DorsalTighten = Source->DorsalTighten;
		FrameParams.bImplicitSkinning = Source->bImplicitSkinning;
		FrameParams.ImplicitIterations = Source->ImplicitIterations;
		FrameParams.ImplicitSigma = Source->ImplicitSigma;
		FrameParams.ImplicitStopAngle = Source->ImplicitStopAngle;
		FrameParams.ImplicitMaxStep = Source->ImplicitMaxStep;
		FrameParams.ImplicitTolerance = Source->ImplicitTolerance;
		FrameParams.ImplicitRelax = Source->ImplicitRelax;
		FrameParams.ImplicitBetaDiffusion = Source->ImplicitBetaDiffusion;
		FrameParams.ImplicitSmoothIterations = Source->ImplicitSmoothIterations;
		FrameParams.ImplicitSmoothBeta = Source->ImplicitSmoothBeta;
		FrameParams.ImplicitBulge = Source->ImplicitBulge;
		FrameParams.ImplicitBulgeStart = Source->ImplicitBulgeStart;
		FrameParams.ImplicitBulgeFull = Source->ImplicitBulgeFull;
		FrameParams.ImplicitBendStart = Source->ImplicitBendStart;
		FrameParams.ImplicitBendFull = Source->ImplicitBendFull;
		FrameParams.ImplicitDebugMode = Source->ImplicitDebugMode;
		FrameParams.ImplicitContactDepth = Source->ImplicitContactDepth;
		FrameParams.ImplicitStretchKeep = Source->ImplicitStretchKeep;
		FrameParams.bImplicitTracking = Source->bImplicitTracking;
		FrameParams.ImplicitTrackMaxStepDeg = Source->ImplicitTrackMaxStepDeg;
	}
	else
	{
		FrameParams.Mode = SkinMode;
	}

	ENQUEUE_RENDER_COMMAND(PianoHandSkinDeformerEnqueue)(
		[MeshObject, Bones = MoveTemp(Bones), BoneNormals = MoveTemp(BoneNormals), RefInverses = MoveTemp(RefInverses),
		 RestBones = MoveTemp(RestBones), RestBoneNormals = MoveTemp(RestBoneNormals), Capsules = MoveTemp(Capsules),
		 PrimInverses = MoveTemp(PrimInverses), PrimForward = MoveTemp(PrimForward), PairBend = MoveTemp(PairBend), ImplicitForFrame,
		 FrameParams, State = RenderState, Fallback = InDesc.FallbackDelegate, OwnerName = InDesc.OwnerName](FRHICommandListImmediate& RHICmdList)
		{
			if (!PianoHandSkinDeformer::Execute_RenderThread(RHICmdList, MeshObject, Bones, BoneNormals, RefInverses, RestBones, RestBoneNormals, Capsules, PrimInverses, PrimForward, PairBend, ImplicitForFrame, FrameParams, *State, OwnerName))
			{
				Fallback.ExecuteIfBound();
			}
		});
}

EMeshDeformerOutputBuffer UPianoHandSkinDeformerInstance::GetOutputBuffers() const
{
	EMeshDeformerOutputBuffer Buffers = EMeshDeformerOutputBuffer::SkinnedMeshPosition | EMeshDeformerOutputBuffer::SkinnedMeshTangents;
	if (const UPianoHandSkinDeformer* Source = Deformer.Get(); Source && Source->bComputeTension)
	{
		Buffers |= EMeshDeformerOutputBuffer::SkinnedMeshVertexColor;
	}
	return Buffers;
}

// ---------------------------------------------------------------------------
// UPianoHandSkinningLibrary
// ---------------------------------------------------------------------------

UPianoHandSkinDeformer* UPianoHandSkinningLibrary::ApplyCustomSkinning(USkinnedMeshComponent* Component, EPianoHandSkinMode Mode, bool bComputeTension, float TensionScale, bool bDetailDisplacement)
{
	if (Component == nullptr)
	{
		return nullptr;
	}

	UPianoHandSkinDeformer* Deformer = NewObject<UPianoHandSkinDeformer>(Component, NAME_None, RF_Transient);
	Deformer->SkinMode = Mode;
	Deformer->bComputeTension = bComputeTension || bDetailDisplacement;   // detail needs the strain field
	Deformer->TensionScale = FMath::Max(TensionScale, 0.01f);
	Deformer->bDetailDisplacement = bDetailDisplacement;
	Component->SetMeshDeformer(Deformer);

	UE_LOG(LogPianoHand, Display, TEXT("[SkinDeformer] Attached custom %s skinning deformer to %s (tension=%d scale=%.2f detail=%d)"),
		Mode == EPianoHandSkinMode::LinearBlend ? TEXT("LBS") : TEXT("DQS"), *Component->GetPathName(),
		Deformer->bComputeTension ? 1 : 0, Deformer->TensionScale, bDetailDisplacement ? 1 : 0);
	return Deformer;
}

UPianoHandSkinDeformer* UPianoHandSkinningLibrary::GetCustomSkinDeformer(USkinnedMeshComponent* Component)
{
	return Component ? Cast<UPianoHandSkinDeformer>(Component->GetComponentMeshDeformer()) : nullptr;
}

void UPianoHandSkinningLibrary::RemoveCustomSkinning(USkinnedMeshComponent* Component)
{
	if (Component != nullptr)
	{
		Component->UnsetMeshDeformer();
	}
}

int32 UPianoHandSkinningLibrary::FindHandRootBone(const USkinnedMeshComponent* Component)
{
	if (Component == nullptr) { return INDEX_NONE; }
	const FString Suffix = PianoHandProportions::SideSuffix(Component);
	return Suffix.IsEmpty() ? INDEX_NONE : Component->GetBoneIndex(FName(*(TEXT("hand") + Suffix)));
}

int32 UPianoHandSkinningLibrary::FindHandBone(const USkinnedMeshComponent* Component, int32 Finger, int32 Segment)
{
	if (Component == nullptr || Finger < 0 || Finger > 4 || Segment < 0 || Segment > 3) { return INDEX_NONE; }
	const FString Suffix = PianoHandProportions::SideSuffix(Component);
	if (Suffix.IsEmpty()) { return INDEX_NONE; }
	FString Name;
	if (Segment == 3)
	{
		if (Finger == 0) { return INDEX_NONE; }   // the thumb's metacarpal IS thumb_01
		Name = FString::Printf(TEXT("%s_metacarpal%s"), PianoHandProportions::FingerNames[Finger], *Suffix);
	}
	else
	{
		Name = FString::Printf(TEXT("%s_%02d%s"), PianoHandProportions::FingerNames[Finger], Segment + 1, *Suffix);
	}
	return Component->GetBoneIndex(FName(*Name));
}

bool UPianoHandSkinningLibrary::SetHandProportions(USkinnedMeshComponent* Component, const FPianoHandProportions& Proportions)
{
	if (UPianoHandSkinDeformer* Deformer = GetCustomSkinDeformer(Component))
	{
		Deformer->Proportions = Proportions;
		return true;
	}
	return false;
}

FPianoHandMeasurements UPianoHandSkinningLibrary::MeasureHand(USkinnedMeshComponent* Component)
{
	FPianoHandMeasurements M;
	const USkinnedAsset* Asset = Component ? Component->GetSkinnedAsset() : nullptr;
	if (Asset == nullptr) { return M; }

	TArray<FTransform> CS;
	PianoHandProportions::RefPoseComponentSpace(Asset, CS);
	auto Pos = [&CS](int32 B) { return CS.IsValidIndex(B) ? CS[B].GetTranslation() : FVector::ZeroVector; };
	auto Dist = [&](int32 A, int32 B) { return (CS.IsValidIndex(A) && CS.IsValidIndex(B)) ? (float)FVector::Dist(Pos(A), Pos(B)) : 0.0f; };

	const int32 Root = FindHandRootBone(Component);
	M.PalmLength = Dist(Root, FindHandBone(Component, 2, 0));
	M.PalmWidth = Dist(FindHandBone(Component, 1, 0), FindHandBone(Component, 4, 0));

	// The distal phalanx has no child bone: its length is the farthest skin vertex along the bone
	// axis from the DIP joint, if the position buffer is readable on the CPU (it is in the editor),
	// otherwise the anatomical average of ~0.75x the middle phalanx.
	const FSkeletalMeshRenderData* RenderData = Asset->GetResourceForRendering();
	const FPositionVertexBuffer* Positions = (RenderData && RenderData->LODRenderData.Num() > 0)
		? &RenderData->LODRenderData[0].StaticVertexBuffers.PositionVertexBuffer : nullptr;
	const bool bCPU = Positions != nullptr && Positions->GetAllowCPUAccess() && Positions->GetNumVertices() > 0;

	FPianoHandFingerLengths* Fingers[5] = { &M.Thumb, &M.Index, &M.Middle, &M.Ring, &M.Pinky };
	for (int32 F = 0; F < 5; ++F)
	{
		const int32 B0 = FindHandBone(Component, F, 0), B1 = FindHandBone(Component, F, 1), B2 = FindHandBone(Component, F, 2);
		Fingers[F]->Proximal = Dist(B0, B1);
		Fingers[F]->Middle = Dist(B1, B2);
		float Distal = Fingers[F]->Middle * 0.75f;
		if (bCPU && CS.IsValidIndex(B2) && CS.IsValidIndex(B1))
		{
			const FVector Joint = Pos(B2);
			const FVector Axis = (Pos(B2) - Pos(B1)).GetSafeNormal();   // the bone's direction, continued past the DIP
			float Far = 0.0f;
			for (uint32 V = 0; V < Positions->GetNumVertices(); ++V)
			{
				const FVector P(Positions->VertexPosition(V));
				const FVector R = P - Joint;
				const float Along = (float)FVector::DotProduct(R, Axis);
				const float Off = (float)(R - Axis * Along).Size();
				if (Along > 0.0f && Off < 1.2f)
				{
					Far = FMath::Max(Far, Along);
				}
			}
			if (Far > 0.5f) { Distal = Far; }
		}
		Fingers[F]->Distal = Distal;
	}
	return M;
}

FPianoHandProportions UPianoHandSkinningLibrary::ProportionsFromMeasurements(USkinnedMeshComponent* Component, const FPianoHandMeasurements& Target)
{
	FPianoHandProportions P;
	const FPianoHandMeasurements Have = MeasureHand(Component);
	auto Ratio = [](float Want, float Got) { return (Want > 0.0f && Got > 1e-3f) ? FMath::Clamp(Want / Got, 0.5f, 2.0f) : 1.0f; };
	P.PalmLength = Ratio(Target.PalmLength, Have.PalmLength);
	P.PalmWidth = Ratio(Target.PalmWidth, Have.PalmWidth);
	const FPianoHandFingerLengths* T[5] = { &Target.Thumb, &Target.Index, &Target.Middle, &Target.Ring, &Target.Pinky };
	const FPianoHandFingerLengths* H[5] = { &Have.Thumb, &Have.Index, &Have.Middle, &Have.Ring, &Have.Pinky };
	FPianoHandFingerProportions* O[5] = { &P.Thumb, &P.Index, &P.Middle, &P.Ring, &P.Pinky };
	for (int32 F = 0; F < 5; ++F)
	{
		O[F]->Proximal = Ratio(T[F]->Proximal, H[F]->Proximal);
		O[F]->Middle = Ratio(T[F]->Middle, H[F]->Middle);
		O[F]->Distal = Ratio(T[F]->Distal, H[F]->Distal);
	}
	return P;
}

FString UPianoHandSkinningLibrary::GetImplicitSkinningSummary(USkinnedMeshComponent* Component)
{
	if (Component == nullptr) { return FString(); }
	if (const UPianoHandSkinDeformerInstance* Instance = Cast<UPianoHandSkinDeformerInstance>(Component->GetMeshDeformerInstance()))
	{
		return Instance->GetImplicitSummary();
	}
	return FString();
}

void UPianoHandSkinningLibrary::RebuildImplicitSkinning(USkinnedMeshComponent* Component)
{
	if (Component == nullptr) { return; }
	if (UPianoHandSkinDeformerInstance* Instance = Cast<UPianoHandSkinDeformerInstance>(Component->GetMeshDeformerInstance()))
	{
		Instance->InvalidateImplicitData();
	}
}

int32 UPianoHandSkinningLibrary::GetCustomSkinningFrameCount(USkinnedMeshComponent* Component)
{
	if (Component != nullptr)
	{
		if (UPianoHandSkinDeformerInstance* Instance = Cast<UPianoHandSkinDeformerInstance>(Component->GetMeshDeformerInstanceForLOD(Component->GetPredictedLODLevel())))
		{
			return Instance->EnqueuedFrames;
		}
	}
	return -1;
}
