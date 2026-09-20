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

// ---------------------------------------------------------------------------
// Compute shader
// ---------------------------------------------------------------------------

IMPLEMENT_GLOBAL_SHADER(FPianoHandSkinDeformerCS, "/PianoHand/Private/CustomSkinningDeformer.usf", "DeformCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FPianoHandTensionAccumulateCS, "/PianoHand/Private/CustomSkinningTension.usf", "AccumulateCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FPianoHandTensionResolveCS, "/PianoHand/Private/CustomSkinningTension.usf", "ResolveCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FPianoHandDetailDisplaceCS, "/PianoHand/Private/CustomSkinningDetail.usf", "DisplaceCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FPianoHandNormalAccumulateCS, "/PianoHand/Private/CustomSkinningDetail.usf", "NormalAccumulateCS", SF_Compute);
IMPLEMENT_GLOBAL_SHADER(FPianoHandNormalResolveCS, "/PianoHand/Private/CustomSkinningDetail.usf", "NormalResolveCS", SF_Compute);

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
	static bool Execute_RenderThread(
		FRHICommandListImmediate& RHICmdList,
		FSkeletalMeshObject* MeshObject,
		const TArray<FSkinBoneTransform>& AllBones,
		const TArray<FSkinBoneTransform>& AllRefInverses,
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
		if (bComputeTension)
		{
			const FRawStaticIndexBuffer16or32Interface* IndexBuffer = Lod.MultiSizeIndexContainer.IsIndexBufferValid() ? Lod.MultiSizeIndexContainer.GetIndexBuffer() : nullptr;
			IndexSRV = IndexBuffer ? IndexBuffer->GetSRV() : nullptr;
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

		FPianoHandSkinDeformerCS::FPermutationDomain PermutationVector;
		PermutationVector.Set<FPianoHandSkinDeformerCS::FSkinModeDim>(Mode == EPianoHandSkinMode::LinearBlend ? 0 : 1);
		PermutationVector.Set<FPianoHandSkinDeformerCS::FBoneIndex16Dim>(bIndex16);
		PermutationVector.Set<FPianoHandSkinDeformerCS::FBoneWeight16Dim>(bWeight16);
		TShaderMapRef<FPianoHandSkinDeformerCS> ComputeShader(GetGlobalShaderMap(GMaxRHIFeatureLevel), PermutationVector);

		for (int32 SectionIndex = 0; SectionIndex < Lod.RenderSections.Num(); ++SectionIndex)
		{
			const FSkelMeshRenderSection& Section = Lod.RenderSections[SectionIndex];
			if (Section.bDisabled || Section.NumVertices == 0)
			{
				continue;
			}

			// Section-local bone table (skin weight indices are relative to Section.BoneMap).
			TArray<FSkinBoneTransform> SectionBones;
			SectionBones.SetNumUninitialized(FMath::Max(Section.BoneMap.Num(), 1));
			for (int32 i = 0; i < Section.BoneMap.Num(); ++i)
			{
				const int32 BoneIndex = Section.BoneMap[i];
				SectionBones[i] = AllBones.IsValidIndex(BoneIndex) ? AllBones[BoneIndex] : FSkinBoneTransform::FromMatrix(FMatrix44f::Identity);
			}
			if (Section.BoneMap.Num() == 0)
			{
				SectionBones[0] = FSkinBoneTransform::FromMatrix(FMatrix44f::Identity);
			}

			FRDGBufferRef BoneBuffer = CreateStructuredBuffer(GraphBuilder, TEXT("PianoHandSkinDeformerBones"), SectionBones);

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
			SkinParams->PositionBufferUAV = PositionUAV;
			SkinParams->TangentBufferUAV = TangentUAV;

			FComputeShaderUtils::AddPass(
				GraphBuilder,
				RDG_EVENT_NAME("PianoHand.SkinDeformer(section %d, %u verts)", SectionIndex, Section.NumVertices),
				ComputeShader,
				SkinParams,
				FComputeShaderUtils::GetGroupCount(Section.NumVertices, FPianoHandSkinDeformerCS::ThreadGroupSize));
		}

		// -------------------------------------------------------------------
		// Phase 2: per-vertex tension (edge strain vs rest pose) -> vertex colour
		// -------------------------------------------------------------------
		FRDGBufferRef VertexStrainBuffer = nullptr;
		FRDGBufferSRVRef SkinnedPositionSRV = nullptr;
		const uint32 NumLodVertices = Lod.GetNumVertices();

		if (bComputeTension)
		{
			check(NumLodVertices > 0);

			FRDGBufferRef StrainAccum = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(sizeof(int32), FMath::Max(NumLodVertices, 1u)), TEXT("PianoHandTensionStrainAccum"));
			FRDGBufferRef StrainCount = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(sizeof(uint32), FMath::Max(NumLodVertices, 1u)), TEXT("PianoHandTensionStrainCount"));
			FRDGBufferUAVRef StrainAccumUAV = GraphBuilder.CreateUAV(StrainAccum);
			FRDGBufferUAVRef StrainCountUAV = GraphBuilder.CreateUAV(StrainCount);
			AddClearUAVPass(GraphBuilder, StrainAccumUAV, 0u);
			AddClearUAVPass(GraphBuilder, StrainCountUAV, 0u);

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
				AccParams->IndexBuffer = IndexSRV;
				AccParams->RestPositionBuffer = PositionSRV;
				AccParams->SkinnedPositionBuffer = SkinnedPositionSRV;
				AccParams->StrainAccum = StrainAccumUAV;
				AccParams->StrainCount = StrainCountUAV;

				FComputeShaderUtils::AddPass(
					GraphBuilder,
					RDG_EVENT_NAME("PianoHand.TensionAccumulate(section %d, %u tris)", SectionIndex, Section.NumTriangles),
					AccumulateShader,
					AccParams,
					FComputeShaderUtils::GetGroupCount(Section.NumTriangles, FPianoHandTensionAccumulateCS::ThreadGroupSize));
			}

			// Raw averaged strain, kept for the Phase 3 detail pass.
			VertexStrainBuffer = GraphBuilder.CreateBuffer(FRDGBufferDesc::CreateStructuredDesc(sizeof(float), FMath::Max(NumLodVertices, 1u)), TEXT("PianoHandVertexStrain"));

			FRDGBufferUAVRef ColorUAV = GraphBuilder.CreateUAV(ColorBuffer, PF_R8G8B8A8);
			TShaderMapRef<FPianoHandTensionResolveCS> ResolveShader(GetGlobalShaderMap(GMaxRHIFeatureLevel));
			FPianoHandTensionResolveCS::FParameters* ResParams = GraphBuilder.AllocParameters<FPianoHandTensionResolveCS::FParameters>();
			ResParams->NumVertices = NumLodVertices;
			ResParams->TensionScale = Params.TensionScale;
			ResParams->StrainAccumIn = GraphBuilder.CreateSRV(StrainAccum);
			ResParams->StrainCountIn = GraphBuilder.CreateSRV(StrainCount);
			ResParams->ColorBufferUAV = ColorUAV;
			ResParams->VertexStrainOut = GraphBuilder.CreateUAV(VertexStrainBuffer);

			FComputeShaderUtils::AddPass(
				GraphBuilder,
				RDG_EVENT_NAME("PianoHand.TensionResolve(%u verts)", NumLodVertices),
				ResolveShader,
				ResParams,
				FComputeShaderUtils::GetGroupCount(NumLodVertices, FPianoHandTensionResolveCS::ThreadGroupSize));
		}

		// -------------------------------------------------------------------
		// Phase 3: detail displacement (volume preservation + joint creases)
		// -------------------------------------------------------------------
		if (Params.bDetailDisplacement && VertexStrainBuffer != nullptr && SkinnedPositionSRV != nullptr)
		{
			FRDGBufferSRVRef VertexStrainSRV = GraphBuilder.CreateSRV(VertexStrainBuffer);

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
				TArray<FSkinBoneTransform> SectionRefInverses;
				SectionRefInverses.SetNumUninitialized(FMath::Max(Section.BoneMap.Num(), 1));
				for (int32 i = 0; i < Section.BoneMap.Num(); ++i)
				{
					const int32 BoneIndex = Section.BoneMap[i];
					SectionRefInverses[i] = AllRefInverses.IsValidIndex(BoneIndex) ? AllRefInverses[BoneIndex] : FSkinBoneTransform::FromMatrix(FMatrix44f::Identity);
				}
				if (Section.BoneMap.Num() == 0)
				{
					SectionRefInverses[0] = FSkinBoneTransform::FromMatrix(FMatrix44f::Identity);
				}

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
				DispParams->RestPositionBuffer = PositionSRV;
				DispParams->InputWeightStream = WeightSRV;
				DispParams->RefPoseInverses = GraphBuilder.CreateSRV(RefInvBuffer);
				DispParams->VertexStrain = VertexStrainSRV;
				DispParams->PositionBufferUAV = PositionUAV;
				DispParams->TangentBufferUAV = TangentUAV;

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
					NAParams->IndexBuffer = IndexSRV;
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
				NRParams->TangentBufferUAV = TangentUAV;

				FComputeShaderUtils::AddPass(
					GraphBuilder,
					RDG_EVENT_NAME("PianoHand.NormalResolve(%u verts)", NumLodVertices),
					NormalResShader,
					NRParams,
					FComputeShaderUtils::GetGroupCount(NumLodVertices, FPianoHandNormalResolveCS::ThreadGroupSize));
			}
		}

		FSkeletalMeshDeformerHelpers::UpdateVertexFactoryBufferOverrides(GraphBuilder, MeshObject, LodIndex, bInvalidatePreviousPosition);
		ExternalAccessQueue.Submit(GraphBuilder);
		GraphBuilder.Execute();
		return true;
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

	TArray<FSkinBoneTransform> Bones;
	Bones.SetNumUninitialized(NumBones);
	// Phase 3 also needs RefPoseInverse on its own, to get rest-pose bone-local coordinates.
	TArray<FSkinBoneTransform> RefInverses;
	RefInverses.SetNumUninitialized(NumBones);
	for (int32 BoneIndex = 0; BoneIndex < NumBones; ++BoneIndex)
	{
		const FMatrix44f BoneMatrix = RefBasesInvMatrix[BoneIndex] * FMatrix44f(ComponentSpaceTransforms[BoneIndex].ToMatrixWithScale());
		Bones[BoneIndex] = FSkinBoneTransform::FromMatrix(BoneMatrix);
		RefInverses[BoneIndex] = FSkinBoneTransform::FromMatrix(RefBasesInvMatrix[BoneIndex]);
	}

	++EnqueuedFrames;

	// Re-read the deformer properties every frame so Details-panel / Python edits apply live.
	FPianoHandDeformerFrameParams FrameParams;
	if (const UPianoHandSkinDeformer* Source = Deformer.Get())
	{
		FrameParams.Mode = Source->SkinMode;
		FrameParams.bComputeTension = Source->bComputeTension;
		FrameParams.TensionScale = Source->TensionScale;
		FrameParams.bDetailDisplacement = Source->bDetailDisplacement;
		FrameParams.bRecomputeNormals = Source->bRecomputeNormals;
		FrameParams.VolumeBulge = Source->VolumeBulge;
		FrameParams.CreaseDepth = Source->CreaseDepth;
		FrameParams.CreaseSharpness = Source->CreaseSharpness;
		FrameParams.CreaseCompressionGain = Source->CreaseCompressionGain;
		FrameParams.WrinkleAmplitude = Source->WrinkleAmplitude;
		FrameParams.WrinkleFrequency = Source->WrinkleFrequency;
	}
	else
	{
		FrameParams.Mode = SkinMode;
	}

	ENQUEUE_RENDER_COMMAND(PianoHandSkinDeformerEnqueue)(
		[MeshObject, Bones = MoveTemp(Bones), RefInverses = MoveTemp(RefInverses), FrameParams, State = RenderState, Fallback = InDesc.FallbackDelegate, OwnerName = InDesc.OwnerName](FRHICommandListImmediate& RHICmdList)
		{
			if (!PianoHandSkinDeformer::Execute_RenderThread(RHICmdList, MeshObject, Bones, RefInverses, FrameParams, *State, OwnerName))
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
