// PianoHand custom GPU skinning - UMeshDeformer integration (Phase 1) + per-vertex tension (Phase 2)
//
// UPianoHandSkinDeformer      : deformer asset/object assigned to a USkinnedMeshComponent via SetMeshDeformer()
// UPianoHandSkinDeformerInstance : per-component instance; every frame it uploads RefPoseInverse*ComponentSpace
//                                   bone transforms and dispatches the CustomSkinningDeformer.usf kernel that
//                                   writes directly into the engine passthrough vertex factory buffers.
//                                   When tension output is enabled it then runs CustomSkinningTension.usf
//                                   (per-triangle stretch tensor vs rest pose, Rohmer et al. 2010) and writes
//                                   the principal / bone-relative strain to the vertex colour buffer.
// UPianoHandSkinningLibrary   : Blueprint / Python helpers to attach and detach the deformer.

#pragma once

#include "CoreMinimal.h"
#include "Animation/MeshDeformer.h"
#include "Animation/MeshDeformerInstance.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "GlobalShader.h"
#include "ShaderParameterStruct.h"
#include "RenderGraphResources.h"
#include "CustomSkinningShader.h"
#include "Engine/Texture2D.h"
#include "PianoHandSkinDeformer.generated.h"

class USkinnedMeshComponent;
class FSkeletalMeshObject;

UENUM(BlueprintType)
enum class EPianoHandSkinMode : uint8
{
	LinearBlend    UMETA(DisplayName = "Linear Blend (LBS)"),
	DualQuaternion UMETA(DisplayName = "Dual Quaternion (DQS)"),
};

/**
 * Per-finger proportion scales (Phase 5 - individual hands). 1 = the mesh as authored.
 * Lengths scale the SEGMENT (the bone, and with it the skin bound to it and the joint at its far end);
 * Thickness scales the finger's cross-section. For the thumb, Proximal is the metacarpal
 * (thumb_01), Middle the proximal phalanx (thumb_02) and Distal the distal phalanx (thumb_03).
 */
USTRUCT(BlueprintType)
struct FPianoHandFingerProportions
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand", meta = (ClampMin = "0.5", ClampMax = "2.0", UIMin = "0.7", UIMax = "1.4"))
	float Proximal = 1.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand", meta = (ClampMin = "0.5", ClampMax = "2.0", UIMin = "0.7", UIMax = "1.4"))
	float Middle = 1.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand", meta = (ClampMin = "0.5", ClampMax = "2.0", UIMin = "0.7", UIMax = "1.4"))
	float Distal = 1.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand", meta = (ClampMin = "0.5", ClampMax = "2.0", UIMin = "0.7", UIMax = "1.4"))
	float Thickness = 1.0f;

	bool IsIdentity() const
	{
		return FMath::IsNearlyEqual(Proximal, 1.0f) && FMath::IsNearlyEqual(Middle, 1.0f)
			&& FMath::IsNearlyEqual(Distal, 1.0f) && FMath::IsNearlyEqual(Thickness, 1.0f);
	}
};

/**
 * The whole hand's proportions, as scale factors on the authored mesh. Applied inside the deformer:
 * every scale lives in its bone's LOCAL frame (x along the bone, y palmar, z across), the joints
 * downstream move with the scaled segment, and the strain tensor is taken against the SCALED rest
 * pose, so a longer finger is not read as a stretched one. Nothing outside the deformer changes -
 * the animation, the skeleton asset and the engine's own skinning are untouched.
 */
USTRUCT(BlueprintType)
struct FPianoHandProportions
{
	GENERATED_BODY()

	/** Uniform scale of the whole hand (every bone from the wrist down). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand", meta = (ClampMin = "0.5", ClampMax = "2.0", UIMin = "0.8", UIMax = "1.25"))
	float OverallScale = 1.0f;

	/** Wrist-to-knuckle length: the hand bone and the metacarpals along their axis. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand", meta = (ClampMin = "0.5", ClampMax = "2.0", UIMin = "0.8", UIMax = "1.25"))
	float PalmLength = 1.0f;

	/** Knuckle-to-knuckle breadth: the hand bone and the metacarpals across. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand", meta = (ClampMin = "0.5", ClampMax = "2.0", UIMin = "0.8", UIMax = "1.25"))
	float PalmWidth = 1.0f;

	/** Palm-to-back thickness. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand", meta = (ClampMin = "0.5", ClampMax = "2.0", UIMin = "0.8", UIMax = "1.25"))
	float PalmThickness = 1.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand")
	FPianoHandFingerProportions Thumb;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand")
	FPianoHandFingerProportions Index;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand")
	FPianoHandFingerProportions Middle;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand")
	FPianoHandFingerProportions Ring;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand")
	FPianoHandFingerProportions Pinky;

	bool IsIdentity() const
	{
		return FMath::IsNearlyEqual(OverallScale, 1.0f) && FMath::IsNearlyEqual(PalmLength, 1.0f)
			&& FMath::IsNearlyEqual(PalmWidth, 1.0f) && FMath::IsNearlyEqual(PalmThickness, 1.0f)
			&& Thumb.IsIdentity() && Index.IsIdentity() && Middle.IsIdentity() && Ring.IsIdentity() && Pinky.IsIdentity();
	}
};

/** Segment lengths of a finger in cm, as measured on the mesh or as a target for an individual hand. */
USTRUCT(BlueprintType)
struct FPianoHandFingerLengths
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand") float Proximal = 0.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand") float Middle = 0.0f;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand") float Distal = 0.0f;
};

/**
 * Hand measurements in cm - what a tape measure gives you for a real hand. MeasureHand() fills one
 * from the mesh's reference pose; ProportionsFromMeasurements() turns a target set into scale factors.
 * A zero entry means "leave as authored".
 */
USTRUCT(BlueprintType)
struct FPianoHandMeasurements
{
	GENERATED_BODY()

	/** Wrist crease to the middle-finger knuckle. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand") float PalmLength = 0.0f;
	/** Index knuckle to little-finger knuckle. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand") float PalmWidth = 0.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand") FPianoHandFingerLengths Thumb;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand") FPianoHandFingerLengths Index;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand") FPianoHandFingerLengths Middle;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand") FPianoHandFingerLengths Ring;
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand") FPianoHandFingerLengths Pinky;
};

/** Compute shader that skins one render section straight into the passthrough vertex factory buffers. */
class FPianoHandSkinDeformerCS : public FGlobalShader
{
public:
	DECLARE_GLOBAL_SHADER(FPianoHandSkinDeformerCS);
	SHADER_USE_PARAMETER_STRUCT(FPianoHandSkinDeformerCS, FGlobalShader);

	static constexpr uint32 ThreadGroupSize = 64;

	class FSkinModeDim     : SHADER_PERMUTATION_INT("SKIN_MODE", 2);
	class FBoneIndex16Dim  : SHADER_PERMUTATION_BOOL("GPUSKIN_BONE_INDEX_UINT16");
	class FBoneWeight16Dim : SHADER_PERMUTATION_BOOL("GPUSKIN_BONE_WEIGHTS_UINT16");
	using FPermutationDomain = TShaderPermutationDomain<FSkinModeDim, FBoneIndex16Dim, FBoneWeight16Dim>;

	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER(uint32, NumVertices)
		SHADER_PARAMETER(uint32, BaseVertexIndex)
		SHADER_PARAMETER(uint32, NumBoneInfluences)
		SHADER_PARAMETER(uint32, InputWeightStride)
		SHADER_PARAMETER(uint32, NumSectionBones)
		SHADER_PARAMETER_SRV(Buffer<float>, PositionInputBuffer)
		SHADER_PARAMETER_SRV(Buffer<SNORM float4>, TangentInputBuffer)
		SHADER_PARAMETER_SRV(Buffer<uint>, InputWeightStream)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<FBoneTransform>, BoneTransforms)
		/** Inverse-transpose of BoneTransforms' 3x3, for normals. Identical to BoneTransforms unless a bone carries a non-uniform (proportion) scale. */
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<FBoneTransform>, BoneNormalTransforms)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<float>, PositionBufferUAV)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<SNORM float4>, TangentBufferUAV)
		/** Per-vertex blended rotation (quaternion): the a-priori ARAP target of the elastic tangential relaxation (Vaillant 2014). */
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<float4>, VertexRotUAV)
	END_SHADER_PARAMETER_STRUCT()

	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters);
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment);
};

/** Phase 2 - per-triangle stretch tensor (right Cauchy-Green, rest component space) accumulation (atomic, fixed point). */
class FPianoHandTensionAccumulateCS : public FGlobalShader
{
public:
	DECLARE_GLOBAL_SHADER(FPianoHandTensionAccumulateCS);
	SHADER_USE_PARAMETER_STRUCT(FPianoHandTensionAccumulateCS, FGlobalShader);

	static constexpr uint32 ThreadGroupSize = 64;

	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER(uint32, NumTriangles)
		SHADER_PARAMETER(uint32, BaseIndex)
		/** 10-18: LOD indices with UV-seam twins replaced by their canonical vertex (see PianoHandImplicit::BuildWeldMap). */
		SHADER_PARAMETER_RDG_BUFFER_SRV(Buffer<uint>, IndexBuffer)
		SHADER_PARAMETER(uint32, bUseProportionedRest)
		SHADER_PARAMETER_SRV(Buffer<float>, RestPositionBuffer)
		/** Phase 5: the rest pose skinned with the proportion scales, used instead of RestPositionBuffer when bUseProportionedRest. */
		SHADER_PARAMETER_RDG_BUFFER_SRV(Buffer<float>, ProportionedRestPositionBuffer)
		SHADER_PARAMETER_RDG_BUFFER_SRV(Buffer<float>, SkinnedPositionBuffer)
		/** 6 ints per LOD vertex: xx yy zz xy xz yz of the summed tensor. */
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<int>, TensorAccum)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<uint>, TensorCount)
		/** Sum of rest face-normal outer products per vertex (crease correction, see the .usf). */
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<int>, NormalOuterAccum)
	END_SHADER_PARAMETER_STRUCT()

	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters);
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment);
};

/** Phase 2 - per-vertex tensor average, eigen-decomposition in the tangent plane -> vertex colour. */
class FPianoHandTensionResolveCS : public FGlobalShader
{
public:
	DECLARE_GLOBAL_SHADER(FPianoHandTensionResolveCS);
	SHADER_USE_PARAMETER_STRUCT(FPianoHandTensionResolveCS, FGlobalShader);

	static constexpr uint32 ThreadGroupSize = 64;

	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER(uint32, NumVertices)
		SHADER_PARAMETER(float, TensionScale)
		SHADER_PARAMETER(float, DeltaTime)
		SHADER_PARAMETER(float, RelaxGain)
		SHADER_PARAMETER(float, RelaxTau)
		SHADER_PARAMETER(uint32, bResetRelax)
		SHADER_PARAMETER(uint32, bUseProportionedRest)
		SHADER_PARAMETER_SRV(Buffer<SNORM float4>, RestTangentBuffer)
		SHADER_PARAMETER_RDG_BUFFER_SRV(Buffer<SNORM float4>, ProportionedRestTangentBuffer)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<int>, TensorAccumIn)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, TensorCountIn)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<int>, NormalOuterAccumIn)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, WeldCanon)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<UNORM float4>, ColorBufferUAV)
		/** Averaged tensor, 6 floats per LOD vertex, for the detail pass. */
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<float>, VertexTensorOut)
		/** Persistent across frames: .x = last frame's strain, .y = accumulated slack. */
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<float2>, RelaxState)
	END_SHADER_PARAMETER_STRUCT()

	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters);
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment);
};

/** Phase 7b - 1-ring Laplacian smoothing of the per-vertex strain tensor: scatter (per triangle). */
class FPianoHandTensorSmoothScatterCS : public FGlobalShader
{
public:
	DECLARE_GLOBAL_SHADER(FPianoHandTensorSmoothScatterCS);
	SHADER_USE_PARAMETER_STRUCT(FPianoHandTensorSmoothScatterCS, FGlobalShader);
	static constexpr uint32 ThreadGroupSize = 64;
	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER(uint32, NumTriangles)
		SHADER_PARAMETER(uint32, BaseIndex)
		/** 10-18: LOD indices with UV-seam twins replaced by their canonical vertex (see PianoHandImplicit::BuildWeldMap). */
		SHADER_PARAMETER_RDG_BUFFER_SRV(Buffer<uint>, IndexBuffer)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float>, SmoothTensorIn)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<int>, TensorAccum)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<uint>, TensorCount)
	END_SHADER_PARAMETER_STRUCT()
	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters);
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment);
};

/** Phase 7b - resolve (per vertex): blend each tensor towards its neighbour mean. */
class FPianoHandTensorSmoothResolveCS : public FGlobalShader
{
public:
	DECLARE_GLOBAL_SHADER(FPianoHandTensorSmoothResolveCS);
	SHADER_USE_PARAMETER_STRUCT(FPianoHandTensorSmoothResolveCS, FGlobalShader);
	static constexpr uint32 ThreadGroupSize = 64;
	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER(uint32, NumVertices)
		SHADER_PARAMETER(float, SmoothLambda)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float>, SmoothTensorIn)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<int>, TensorAccumIn)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, TensorCountIn)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, WeldCanon)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<float>, SmoothTensorOut)
	END_SHADER_PARAMETER_STRUCT()
	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters);
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment);
};

/** Phase 3 - volume-preserving bulge + joint creases, displacing the skinned surface along its normal. */
class FPianoHandDetailDisplaceCS : public FGlobalShader
{
public:
	DECLARE_GLOBAL_SHADER(FPianoHandDetailDisplaceCS);
	SHADER_USE_PARAMETER_STRUCT(FPianoHandDetailDisplaceCS, FGlobalShader);

	static constexpr uint32 ThreadGroupSize = 64;

	class FBoneIndex16Dim  : SHADER_PERMUTATION_BOOL("GPUSKIN_BONE_INDEX_UINT16");
	class FBoneWeight16Dim : SHADER_PERMUTATION_BOOL("GPUSKIN_BONE_WEIGHTS_UINT16");
	using FPermutationDomain = TShaderPermutationDomain<FBoneIndex16Dim, FBoneWeight16Dim>;

	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER(uint32, NumVertices)
		SHADER_PARAMETER(uint32, BaseVertexIndex)
		SHADER_PARAMETER(uint32, NumBoneInfluences)
		SHADER_PARAMETER(uint32, InputWeightStride)
		SHADER_PARAMETER(uint32, NumSectionBones)
		SHADER_PARAMETER(float, VolumeBulge)
		SHADER_PARAMETER(float, CreaseDepth)
		SHADER_PARAMETER(float, CreaseSharpness)
		SHADER_PARAMETER(float, CreaseCompressionGain)
		SHADER_PARAMETER(float, WrinkleAmplitude)
		SHADER_PARAMETER(float, WrinkleFrequency)
		SHADER_PARAMETER(float, CreaseStretchRelief)
		SHADER_PARAMETER(float, RelaxCreaseGain)
		SHADER_PARAMETER(float, TensionScale)
		/** Phase 5 - the baked wrinkle mask drives a narrow groove on the PRIMARY crease line only (see CustomSkinningDetail.usf). */
		SHADER_PARAMETER(uint32, bHasWrinkleMask)
		SHADER_PARAMETER(uint32, NumUVChannels)
		SHADER_PARAMETER(float, MaskCreaseDepth)
		SHADER_PARAMETER(float, MaskCreaseWidth)
		SHADER_PARAMETER(float, MaskCreaseRange)
		SHADER_PARAMETER(float, MaskGain)
		SHADER_PARAMETER(float, MaskSharpness)
		SHADER_PARAMETER(float, MaskPalmSplit)
		SHADER_PARAMETER(float, MaskPalmarBase)
		SHADER_PARAMETER(float, MaskPalmarCompress)
		SHADER_PARAMETER(float, MaskPalmarIron)
		SHADER_PARAMETER(float, MaskDorsalBase)
		SHADER_PARAMETER(float, MaskDorsalIron)
		SHADER_PARAMETER(float, DorsalGather)
		SHADER_PARAMETER(float, DorsalGatherSpacing)
		SHADER_PARAMETER(float, DorsalGatherReach)
		SHADER_PARAMETER(float, DorsalGatherBase)
		SHADER_PARAMETER(float, DorsalGatherIron)
		SHADER_PARAMETER(float, PalmarPadHeight)
		SHADER_PARAMETER(float, PalmarPadDist)
		SHADER_PARAMETER(float, PalmarPadWidth)
		SHADER_PARAMETER(float, PalmarFold2Depth)
		SHADER_PARAMETER(float, PalmarFold2Dist)
		SHADER_PARAMETER(float, PalmarFold2Width)
		SHADER_PARAMETER(float, PalmarCreaseDeepen)
		SHADER_PARAMETER(float, PalmarFoldBendFull)
		SHADER_PARAMETER_TEXTURE(Texture2D, WrinkleMask)
		SHADER_PARAMETER_SAMPLER(SamplerState, WrinkleMaskSampler)
		SHADER_PARAMETER_SRV(Buffer<float2>, UVInputBuffer)
		/** Phase 7 - joint contact + volume-preserving bulge (implicit-skinning style capsules per bone). */
		SHADER_PARAMETER(uint32, bContactBulge)
		SHADER_PARAMETER(float, ContactMargin)
		SHADER_PARAMETER(float, BulgeGain)
		SHADER_PARAMETER(float, BulgeReach)
		SHADER_PARAMETER(float, BulgeSpread)
		SHADER_PARAMETER(float, BendStart)
		SHADER_PARAMETER(float, BendFull)
		SHADER_PARAMETER(float, CapsuleRadiusScale)
		SHADER_PARAMETER(float, DorsalTighten)
		/** Animated bone transforms (RefPoseInverse * ComponentSpace), section BoneMap order - same table the skin pass used. */
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<FBoneTransform>, BoneTransforms)
		/** Per section bone: (rest origin xyz, capsule radius) and (rest axis end xyz, parent section index or -1). */
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float4>, BoneCapsules)
		SHADER_PARAMETER_SRV(Buffer<float>, RestPositionBuffer)
		SHADER_PARAMETER_SRV(Buffer<SNORM float4>, RestTangentBuffer)
		SHADER_PARAMETER(uint32, bUseProportionedRest)
		SHADER_PARAMETER_RDG_BUFFER_SRV(Buffer<float>, ProportionedRestPositionBuffer)
		SHADER_PARAMETER_RDG_BUFFER_SRV(Buffer<SNORM float4>, ProportionedRestTangentBuffer)
		SHADER_PARAMETER_SRV(Buffer<uint>, InputWeightStream)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<FBoneTransform>, RefPoseInverses)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float>, VertexTensor)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float2>, RelaxStateIn)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, WeldCanon)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<float>, PositionBufferUAV)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<SNORM float4>, TangentBufferUAV)
		/** Rewritten with the bone-relative strain (R stretch, G along-bone compression, B across, A slack). */
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<UNORM float4>, ColorBufferUAV)
	END_SHADER_PARAMETER_STRUCT()

	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters);
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment);
};

/** Phase 3 - per-triangle face normal accumulation over the displaced surface. */
class FPianoHandNormalAccumulateCS : public FGlobalShader
{
public:
	DECLARE_GLOBAL_SHADER(FPianoHandNormalAccumulateCS);
	SHADER_USE_PARAMETER_STRUCT(FPianoHandNormalAccumulateCS, FGlobalShader);

	static constexpr uint32 ThreadGroupSize = 64;

	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER(uint32, NumTriangles)
		SHADER_PARAMETER(uint32, BaseIndex)
		/** 10-18: LOD indices with UV-seam twins replaced by their canonical vertex (see PianoHandImplicit::BuildWeldMap). */
		SHADER_PARAMETER_RDG_BUFFER_SRV(Buffer<uint>, IndexBuffer)
		SHADER_PARAMETER_RDG_BUFFER_SRV(Buffer<float>, DisplacedPositionBuffer)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<int>, NormalAccum)
	END_SHADER_PARAMETER_STRUCT()

	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters);
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment);
};

/** Phase 3 - normalise the accumulated normals and rewrite the tangent frame. */
class FPianoHandNormalResolveCS : public FGlobalShader
{
public:
	DECLARE_GLOBAL_SHADER(FPianoHandNormalResolveCS);
	SHADER_USE_PARAMETER_STRUCT(FPianoHandNormalResolveCS, FGlobalShader);

	static constexpr uint32 ThreadGroupSize = 64;

	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER(uint32, NumLodVertices)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<int>, NormalAccumIn)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, WeldCanon)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<SNORM float4>, TangentBufferUAV)
	END_SHADER_PARAMETER_STRUCT()

	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters);
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment);
};

// ---------------------------------------------------------------------------
// Phase 8 - implicit skinning (Vaillant et al. 2013). See Shaders/Private/ImplicitSkinning.usf.
// ---------------------------------------------------------------------------

/** Shared read-only bindings of the implicit skinning passes. */
BEGIN_SHADER_PARAMETER_STRUCT(FPianoHandImplicitCommonParameters, )
	SHADER_PARAMETER(uint32, NumVertices)
	SHADER_PARAMETER(uint32, NumPrims)
	SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float4>, HrbfSamples)
	SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float4>, PrimInfo)
	SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float4>, PrimAxis)
	SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint4>, PrimMeta)
	SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<int2>, PrimNeighbours)
	SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<FBoneTransform>, PrimInverse)
	SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<int>, VertexPrim)
	SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float>, VertexIso)
	/** 2 float4 per vertex: (prim, c, prim, c) x2 - the other parts whose field exceeded 0.5 at the vertex at rest, and that rest value. -1 = none. */
	SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float4>, VertexOverlap)
	SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float4>, VertexOwn)
	/** 0..1 per vertex: how much of the implicit correction to keep (fades out towards the palm, which stays on the geometric skinning). */
	SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float>, VertexBlend)
	SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, AdjOffsets)
	SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, AdjIndices)
	SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float>, AdjWeights)
END_SHADER_PARAMETER_STRUCT()

/** Newton projection of every vertex onto its rest iso-value, in place. */
class FPianoHandImplicitProjectCS : public FGlobalShader
{
public:
	DECLARE_GLOBAL_SHADER(FPianoHandImplicitProjectCS);
	SHADER_USE_PARAMETER_STRUCT(FPianoHandImplicitProjectCS, FGlobalShader);
	static constexpr uint32 ThreadGroupSize = 64;
	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER_STRUCT_INCLUDE(FPianoHandImplicitCommonParameters, Common)
		SHADER_PARAMETER(uint32, NumSteps)
		SHADER_PARAMETER(uint32, bFirstPass)
		SHADER_PARAMETER(float, Sigma)
		SHADER_PARAMETER(float, IsoTolerance)
		SHADER_PARAMETER(float, StopCosAngle)
		SHADER_PARAMETER(float, MaxStepCm)
		SHADER_PARAMETER(float, BulgeAmount)
		SHADER_PARAMETER(float, BulgeStart)
		SHADER_PARAMETER(float, BulgeFull)
		SHADER_PARAMETER(float, BendGateStart)
		SHADER_PARAMETER(float, BendGateFull)
		SHADER_PARAMETER(float, ContactDepth)
		/** Per neighbour entry: the joint's bend angle this frame (radians), gating the bulge operator. */
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float>, PairBend)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<float>, PositionUAV)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<float4>, VertexGrad)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<uint>, VertexState)
		/** cm a vertex has been pushed by OTHER parts so far this frame. */
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<float>, VertexPush)
	END_SHADER_PARAMETER_STRUCT()
	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters);
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment);
};

/** Tangential relaxation towards the mean-value centroid of the one-ring (reads a snapshot, writes in place). */
class FPianoHandImplicitRelaxCS : public FGlobalShader
{
public:
	DECLARE_GLOBAL_SHADER(FPianoHandImplicitRelaxCS);
	SHADER_USE_PARAMETER_STRUCT(FPianoHandImplicitRelaxCS, FGlobalShader);
	static constexpr uint32 ThreadGroupSize = 64;
	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER_STRUCT_INCLUDE(FPianoHandImplicitCommonParameters, Common)
		SHADER_PARAMETER(float, RelaxScale)
		SHADER_PARAMETER_RDG_BUFFER_SRV(Buffer<float>, PositionIn)
		SHADER_PARAMETER_SRV(Buffer<float>, RestPositionIn)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float4>, VertexRot)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<float>, PositionUAV)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<float4>, VertexGrad)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<uint>, VertexState)
	END_SHADER_PARAMETER_STRUCT()
	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters);
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment);
};

/** Diffusion of the smoothing weight beta (seeded with 1 on vertices stopped at a contact). */
class FPianoHandImplicitBetaCS : public FGlobalShader
{
public:
	DECLARE_GLOBAL_SHADER(FPianoHandImplicitBetaCS);
	SHADER_USE_PARAMETER_STRUCT(FPianoHandImplicitBetaCS, FGlobalShader);
	static constexpr uint32 ThreadGroupSize = 64;
	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER_STRUCT_INCLUDE(FPianoHandImplicitCommonParameters, Common)
		SHADER_PARAMETER(uint32, bFirstPass)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float>, BetaIn)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<float>, BetaOut)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<uint>, VertexState)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<float>, VertexPush)
	END_SHADER_PARAMETER_STRUCT()
	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters);
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment);
};

/** Localised Laplacian smoothing v <- (1 - beta) v + beta centroid (reads a snapshot, writes in place). */
class FPianoHandImplicitSmoothCS : public FGlobalShader
{
public:
	DECLARE_GLOBAL_SHADER(FPianoHandImplicitSmoothCS);
	SHADER_USE_PARAMETER_STRUCT(FPianoHandImplicitSmoothCS, FGlobalShader);
	static constexpr uint32 ThreadGroupSize = 64;
	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER_STRUCT_INCLUDE(FPianoHandImplicitCommonParameters, Common)
		SHADER_PARAMETER(float, SmoothBeta)
		SHADER_PARAMETER_RDG_BUFFER_SRV(Buffer<float>, PositionIn)
		SHADER_PARAMETER_RDG_BUFFER_SRV(Buffer<float>, PrePosition)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float>, BetaIn)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<float>, PositionUAV)
	END_SHADER_PARAMETER_STRUCT()
	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters);
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment);
};

/** Final blend: X = lerp(pre-implicit X, X, VertexBlend) so the correction fades out where the palm's own skinning takes over. */
class FPianoHandImplicitFinalizeCS : public FGlobalShader
{
public:
	DECLARE_GLOBAL_SHADER(FPianoHandImplicitFinalizeCS);
	SHADER_USE_PARAMETER_STRUCT(FPianoHandImplicitFinalizeCS, FGlobalShader);
	static constexpr uint32 ThreadGroupSize = 64;
	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER_STRUCT_INCLUDE(FPianoHandImplicitCommonParameters, Common)
		SHADER_PARAMETER(float, StretchKeep)
		SHADER_PARAMETER(float, BendGateStart)
		SHADER_PARAMETER(float, BendGateFull)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float>, PairBend)
		SHADER_PARAMETER_RDG_BUFFER_SRV(Buffer<float>, PrePosition)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<float>, PositionUAV)
	END_SHADER_PARAMETER_STRUCT()
	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters);
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment);
};

/** Phase 11 (10-16) - incremental iso-surface tracking (Vaillant 2014 sec. 5, step 1): the previous frame's tracked
 *  positions are carried by the transform difference of each vertex's own primitive and become the initial guess
 *  instead of the fresh geometric skinning, so contacts form gradually frame by frame. */
class FPianoHandImplicitAdvectCS : public FGlobalShader
{
public:
	DECLARE_GLOBAL_SHADER(FPianoHandImplicitAdvectCS);
	SHADER_USE_PARAMETER_STRUCT(FPianoHandImplicitAdvectCS, FGlobalShader);
	static constexpr uint32 ThreadGroupSize = 64;
	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER_STRUCT_INCLUDE(FPianoHandImplicitCommonParameters, Common)
		SHADER_PARAMETER_RDG_BUFFER_SRV(Buffer<float>, TrackedIn)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<FBoneTransform>, PrimPrevInverse)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<FBoneTransform>, PrimNow)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<float>, PositionUAV)
	END_SHADER_PARAMETER_STRUCT()
	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters);
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment);
};

/** Debug: vertex colour = (stopped, |displacement| / 0.3 cm, |f - iso| * 20, 1) after the implicit passes. */
class FPianoHandImplicitDebugCS : public FGlobalShader
{
public:
	DECLARE_GLOBAL_SHADER(FPianoHandImplicitDebugCS);
	SHADER_USE_PARAMETER_STRUCT(FPianoHandImplicitDebugCS, FGlobalShader);
	static constexpr uint32 ThreadGroupSize = 64;
	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER_STRUCT_INCLUDE(FPianoHandImplicitCommonParameters, Common)
		SHADER_PARAMETER(uint32, DebugMode)
		SHADER_PARAMETER_RDG_BUFFER_SRV(Buffer<float>, PositionIn)
		SHADER_PARAMETER_RDG_BUFFER_SRV(Buffer<float>, PrePosition)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<float4>, VertexGrad)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<uint>, VertexState)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<UNORM float4>, ColorBufferUAV)
	END_SHADER_PARAMETER_STRUCT()
	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters);
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment);
};

/**
 * Phase 8 - everything the implicit skinning passes need that does not change per frame, built once
 * per mesh on the game thread (PianoHandImplicit::Build): the HRBF of every bone part, the joint
 * partner list per primitive, the rest iso-value and primitive of every LOD vertex, and the one-ring
 * adjacency with mean value coordinates. Shared read-only with the render thread.
 */
struct FPianoHandImplicitData
{
	uint32 BuildId = 0;
	uint32 NumVertices = 0;
	bool bValid = false;
	FString Summary;

	TArray<FVector4f> Samples;          // 2 per HRBF sample: (p.xyz, a), (b.xyz, 0) in normalised coordinates
	TArray<FVector4f> PrimInfo;         // origin.xyz (rest component space), support scale
	TArray<FVector4f> PrimAxis;         // bone direction.xyz (rest component space, origin -> distal joint), segment length
	TArray<FUintVector4> PrimMeta;      // sampleOffset, sampleCount, numNeighbours, neighbourOffset
	TArray<FIntPoint> PrimNeighbours;   // (partner prim, op)
	TArray<int32> PrimBone;             // skeleton bone that carries each primitive
	TArray<FQuat4f> PairRestRelative;   // per neighbour entry: rest-pose R_a^-1 R_b of the two bones
	TArray<FName> PrimName;
	TArray<int32> VertexPrim;           // per LOD vertex, -1 = untouched
	TArray<float> VertexIso;
	TArray<FVector4f> VertexOverlap;    // 2 per vertex, see FPianoHandImplicitCommonParameters
	TArray<FVector4f> VertexOwn;        // 1 per vertex: (prim, c, prim, c) - the OTHER phalanges this vertex is weighted to, with their exact rest field (10-16)
	TArray<float> VertexBlend;          // per vertex, see FPianoHandImplicitCommonParameters
	TArray<uint32> AdjOffsets;
	TArray<uint32> AdjIndices;
	TArray<float> AdjWeights;
};

/** Phase 8 - how the implicit data is built. */
struct FPianoHandImplicitBuildSettings
{
	int32 SamplesPerBone = 50;
	int32 PalmSamples = 100;
	int32 MinVertices = 30;
	float CullFraction = 0.05f;
	bool bPalmGroup = false;
	/** Project the palm / metacarpal vertices too (false: they keep the geometric skinning and only act as obstacles for the fingers). */
	bool bProjectPalm = false;
	/** Finger-weight sum below which the correction is fully faded out, and above which it is fully kept. */
	float BlendFadeStart = 0.45f;
	float BlendFadeFull = 0.85f;
	/** |iso - 0.5| at which the correction starts fading and is fully off (vertices far from their part's surface). */
	float IsoFadeStart = 0.08f;
	float IsoFadeFull = 0.2f;
	/** Skin weight (fraction) above which a second / third phalanx counts as the vertex's OWN surface (union, exact rest
	    value) instead of an obstacle. Below it the neighbouring field only pushes. 10-16: the hard per-vertex dominant-bone
	    choice tore the skin along the ragged weight boundary of every bent joint. */
	float OwnWeightMin = 0.15f;
};

/** Deformer object. Assign to a skinned mesh component with USkinnedMeshComponent::SetMeshDeformer(). */
UCLASS(BlueprintType)
class PIANOHAND_SIMULATOR_API UPianoHandSkinDeformer : public UMeshDeformer
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand")
	EPianoHandSkinMode SkinMode = EPianoHandSkinMode::LinearBlend;

	/**
	 * Compute the per-vertex strain tensor after skinning and write it to the vertex colour stream:
	 * R = stretch (lambda_max - 1), G = compression along the bone, B = compression across it, A = relax slack.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Tension")
	bool bComputeTension = true;

	/** Phase 7b: 1-ring Laplacian smoothing iterations on the strain tensor before anything reads it (0 = raw). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Tension", meta = (ClampMin = "0", ClampMax = "6", UIMin = "0", UIMax = "4"))
	int32 TensorSmoothIterations = 2;

	/** Blend towards the neighbour mean per iteration. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Tension", meta = (ClampMin = "0", ClampMax = "1"))
	float TensorSmoothLambda = 0.6f;

	/** Multiplier from raw strain (principal stretch - 1) to the 0..1 colour range. 4 => 25% stretch saturates R. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Tension", meta = (ClampMin = "0.01", UIMin = "0.5", UIMax = "20"))
	float TensionScale = 4.0f;

	/** Phase 3: displace the skinned surface (volume preservation + joint creases). Requires bComputeTension. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Detail")
	bool bDetailDisplacement = false;

	/** Recompute normals from the displaced surface so the new folds actually shade. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Detail")
	bool bRecomputeNormals = true;

	/** cm of outward motion where the surface AREA is compressed ~20% (thickness factor 1/J). This is the volume-preservation bulge. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Detail", meta = (UIMin = "0", UIMax = "1"))
	float VolumeBulge = 0.35f;

	/** cm, depth of the groove sitting on every joint band at rest - the crease you see on a straight finger. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Detail", meta = (UIMin = "0", UIMax = "0.5"))
	float CreaseDepth = 0.06f;

	/** Exponent narrowing the joint band. 1 = broad, 8 = a tight line right on the joint. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Detail", meta = (ClampMin = "1", UIMin = "1", UIMax = "8"))
	float CreaseSharpness = 3.0f;

	/** How much compression ALONG the bone deepens the resting crease. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Detail", meta = (UIMin = "0", UIMax = "5"))
	float CreaseCompressionGain = 2.0f;

	/** cm, bending-only ripples inside the joint band, perpendicular to the bone (needs vertex density / tessellation to read). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Detail", meta = (UIMin = "0", UIMax = "0.3"))
	float WrinkleAmplitude = 0.05f;

	/** Radians per cm along the bone axis - controls how many ripples fit on a segment. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Detail", meta = (UIMin = "0", UIMax = "30"))
	float WrinkleFrequency = 6.0f;

	/**
	 * How much stretch flattens the resting crease. Skin is not symmetric: the inside of a bend folds
	 * far more than the outside smooths out, so compression and stretch get separate gains instead of
	 * one signed strain term. 0 keeps the old symmetric behaviour.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Detail", meta = (UIMin = "0", UIMax = "4"))
	float CreaseStretchRelief = 1.4f;

	/**
	 * Viscoelastic strain memory (Montes Maestre et al. 2026): the log-strain is split into an elastic and a
	 * viscous part, E_v <- E_v + (1 - exp(-dt/tau)) (E - E_v). Skin that has been pulled taut accommodates
	 * (E_e decays over tau); released, it is left with a transient compression that gathers into folds on
	 * the back of a knuckle just after the finger straightens, and decays over the same tau.
	 * RelaxGain maps that transient compression (log-strain) to the 0..1 "slack" the material reads.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Relax", meta = (UIMin = "0", UIMax = "20"))
	float RelaxGain = 6.0f;

	/** Seconds, relaxation time constant tau. The paper uses 1/12 s for facial skin; longer makes release folds linger. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Relax", meta = (UIMin = "0.02", UIMax = "2"))
	float RelaxTau = 0.28f;

	/** cm of extra groove depth at full slack, on top of the resting crease. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Relax", meta = (UIMin = "0", UIMax = "0.3"))
	float RelaxCreaseGain = 0.05f;

	/**
	 * Phase 5 - geometric groove on the PRIMARY crease only. The band-wide trench (CreaseDepth) read as a
	 * cuff; with the baked wrinkle mask the compute pass can put a narrow, shallow groove exactly on the
	 * crease line the material draws, so the fold shows in the silhouette of a bent knuckle. Set to
	 * T_PH_WrinkleMask; null keeps the old band-wide groove.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease")
	TObjectPtr<UTexture2D> WrinkleMask = nullptr;

	/** cm, depth of the primary-crease groove at full gate. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease", meta = (UIMin = "0", UIMax = "0.2"))
	float MaskCreaseDepth = 0.04f;

	/** cm, Bando width of the groove (the V is this wide; the bank peaks at twice it). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease", meta = (UIMin = "0.02", UIMax = "0.5"))
	float MaskCreaseWidth = 0.12f;

	/** cm, MUST match S_RANGE in Tools/bake_skin_maps.py and CreaseRange in the material. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease", meta = (UIMin = "0.5", UIMax = "5"))
	float MaskCreaseRange = 2.0f;

	/** Band gain / sharpness, same meaning as the material's MaskGain / MaskSharpness. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease", meta = (UIMin = "0.2", UIMax = "4"))
	float MaskGain = 1.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease", meta = (UIMin = "0.5", UIMax = "8"))
	float MaskSharpness = 3.0f;

	/** cm, half-distance of the palmar PIP double crease (material's PalmSplit). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease", meta = (UIMin = "0", UIMax = "0.6"))
	float MaskPalmSplit = 0.3f;

	/** Palm-side gate: standing depth, deepening per unit compression, flattening per unit stretch (material's PalmarBase / Compress / Iron). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease", meta = (UIMin = "0", UIMax = "1"))
	float MaskPalmarBase = 0.45f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease", meta = (UIMin = "0", UIMax = "6"))
	float MaskPalmarCompress = 2.6f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease", meta = (UIMin = "0", UIMax = "4"))
	float MaskPalmarIron = 1.2f;

	/** Back-of-hand gate: gathered at rest, pulled taut by stretch (material's DorsalBase / DorsalIron). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease", meta = (UIMin = "0", UIMax = "1"))
	float MaskDorsalBase = 0.4f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease", meta = (UIMin = "0", UIMax = "10"))
	float MaskDorsalIron = 5.0f;

	/**
	 * Phase 9 - gathered skin over an EXTENDED knuckle. The skin on the back of a joint is slack when the
	 * finger is straight (it has to be, to cover the knuckle when it bends), so it stands in a few parallel
	 * ridges on both sides of the crease; flexion pulls it taut and irons them flat. Geometric ridges on
	 * the dorsal joint band, parallel to the primary crease, at rest; gone under stretch. cm of ridge height.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease", meta = (UIMin = "0", UIMax = "0.15"))
	float DorsalGather = 0.045f;

	/** cm between ridges. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease", meta = (UIMin = "0.1", UIMax = "0.6"))
	float DorsalGatherSpacing = 0.24f;

	/** cm from the crease at which the ridges have died out. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease", meta = (UIMin = "0.2", UIMax = "2"))
	float DorsalGatherReach = 0.7f;

	/** Standing gate on an extended knuckle, and how fast flexion stretch spends it. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease", meta = (UIMin = "0", UIMax = "1"))
	float DorsalGatherBase = 0.8f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease", meta = (UIMin = "0", UIMax = "12"))
	float DorsalGatherIron = 8.0f;

	/** 10-18 fold pile: cm, how far the skin on either side of a palmar crease bulges out at full fold. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease")
	float PalmarPadHeight = 0.05f;

	/** 10-18 fold pile: cm from the crease where the bulge peaks. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease")
	float PalmarPadDist = 0.3f;

	/** 10-18 fold pile: cm, half-width of the bulge. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease")
	float PalmarPadWidth = 0.22f;

	/** 10-18 fold pile: cm, depth of the secondary fold at full fold. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease")
	float PalmarFold2Depth = 0.03f;

	/** 10-18 fold pile: cm from the crease to the secondary fold. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease")
	float PalmarFold2Dist = 0.55f;

	/** 10-18 fold pile: cm, half-width of the secondary fold. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease")
	float PalmarFold2Width = 0.1f;

	/** 10-18 fold pile: cm, extra depth of the primary crease at full fold. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease")
	float PalmarCreaseDeepen = 0.05f;

	/** 10-18 fold pile: radians of real joint bend at which the fold is complete. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|MaskCrease")
	float PalmarFoldBendFull = 1.2f;

	/**
	 * Phase 7 - joint contact and volume-preserving bulge. The inside of a bent joint is where skin does
	 * what no skinning does: the two segments come into CONTACT and the tissue squeezed between them
	 * rolls up into a bulge around the fold. Following Vaillant et al. 2013 ("Implicit Skinning", the
	 * bulge-in-contact operator) each bone carries a capsule field; a vertex that enters the partner
	 * segment's capsule is pushed out to the contact surface, and the ring around the contact is raised
	 * by a volume-preserving profile (Brunel, Benard, Guennebaud 2021, "A Time-Independent Deformer for
	 * Elastic Contacts") whose amplitude follows the bend angle (Vaillant's theta(alpha): nothing at
	 * rest, full at 90 degrees). Requires bDetailDisplacement.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Contact")
	bool bContactBulge = true;

	/** cm, how far outside the partner capsule the contact surface sits (skin thickness that never flattens). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Contact", meta = (UIMin = "0", UIMax = "0.3"))
	float ContactMargin = 0.06f;

	/** cm, height of the bulge ring at a right-angle bend. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Contact", meta = (UIMin = "0", UIMax = "0.6"))
	float BulgeGain = 0.0f;

	/** cm, how far from the contact boundary the bulge has died out (Brunel's deformable region). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Contact", meta = (UIMin = "0.1", UIMax = "2"))
	float BulgeReach = 1.1f;

	/** 0..1 where in the ring the bulge peaks (0 = right at the contact edge, 1 = at the far end). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Contact", meta = (UIMin = "0", UIMax = "1"))
	float BulgeSpread = 0.35f;

	/** degrees of bend at which the bulge starts and at which it is full (Vaillant: union at 0, bulge-in-contact from 90). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Contact", meta = (UIMin = "0", UIMax = "90"))
	float BendStart = 15.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Contact", meta = (UIMin = "10", UIMax = "150"))
	float BendFull = 80.0f;

	/** Scale on the capsule radii measured from the rest mesh. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Contact", meta = (UIMin = "0.5", UIMax = "1.5"))
	float CapsuleRadiusScale = 1.0f;

	/** cm, how much the skin over the OUTSIDE of a bent joint is pulled onto the bone (taut over the knuckle). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Contact", meta = (UIMin = "0", UIMax = "0.3"))
	float DorsalTighten = 0.05f;

	/**
	 * Phase 5 - individual hand proportions. Scale factors on the authored mesh, applied per bone in the
	 * deformer (see FPianoHandProportions). Identity = the mesh as authored. Set from measurements with
	 * UPianoHandSkinningLibrary::ProportionsFromMeasurements().
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Proportions")
	FPianoHandProportions Proportions;

	/**
	 * Phase 8 - implicit skinning (Vaillant et al., SIGGRAPH 2013). Every bone part of the rest mesh is
	 * approximated by the 0.5 iso-surface of a Hermite RBF field; at run time the fields move rigidly
	 * with their bones, are composed with a union (contact surfaces in the folds) and a gradient-based
	 * bulge-in-contact operator, and every vertex of the LBS / DQS pose marches along the field gradient
	 * back to the iso-value it had at rest. The result keeps its volume at bent joints, never
	 * self-intersects (vertices stop at the contact crease) and rolls up next to the fold. Runs before
	 * the strain / detail passes, so those read the corrected geometry.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit")
	bool bImplicitSkinning = false;

	/** Newton iterations per frame (the paper interleaves a relaxation step after every pair). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (ClampMin = "0", ClampMax = "32", UIMin = "2", UIMax = "16"))
	int32 ImplicitIterations = 12;

	/** Newton step scale sigma (0.35 in the paper). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (UIMin = "0.1", UIMax = "1"))
	float ImplicitSigma = 0.35f;

	/** degrees; a gradient turning by more than this between two iterations means the vertex crossed a contact crease and is frozen (55 in the paper). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (UIMin = "20", UIMax = "120"))
	float ImplicitStopAngle = 55.0f;

	/** cm, clamp on a single Newton step. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (UIMin = "0.05", UIMax = "1"))
	float ImplicitMaxStep = 0.3f;

	/** |f - iso| below which a vertex counts as converged. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (UIMin = "0.0001", UIMax = "0.02"))
	float ImplicitTolerance = 0.002f;

	/** Multiplier on the tangential relaxation mu (1 = the paper; 0 = off). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (UIMin = "0", UIMax = "1"))
	float ImplicitRelax = 1.0f;

	/** Diffusion iterations of the contact mask beta before the localised Laplacian smoothing. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (ClampMin = "0", ClampMax = "12", UIMin = "0", UIMax = "8"))
	int32 ImplicitBetaDiffusion = 4;

	/** Localised Laplacian smoothing iterations at and around the contact regions. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (ClampMin = "0", ClampMax = "12", UIMin = "0", UIMax = "6"))
	int32 ImplicitSmoothIterations = 4;

	/** Multiplier on beta in the Laplacian step. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (UIMin = "0", UIMax = "1"))
	float ImplicitSmoothBeta = 1.0f;

	/** Bulge-in-contact amplitude in field units (0.1 reproduces the thesis' maximal bulge profile; 0 = plain union). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (UIMin = "0", UIMax = "0.3"))
	float ImplicitBulge = 0.0f;

	/** degrees, gradient angle at which the bulge controller d(alpha) starts and saturates. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (UIMin = "0", UIMax = "90"))
	float ImplicitBulgeStart = 15.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (UIMin = "10", UIMax = "180"))
	float ImplicitBulgeFull = 70.0f;

	/** degrees of actual joint bend below which the bulge operator stays off (it is a union at rest) and above which it is fully enabled. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (UIMin = "0", UIMax = "60"))
	float ImplicitBendStart = 10.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (UIMin = "5", UIMax = "120"))
	float ImplicitBendFull = 40.0f;


	/** HRBF centres per finger bone (Poisson-like farthest point sampling; 50..100 in the paper). Changing it rebuilds the fields. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (ClampMin = "12", ClampMax = "160", UIMin = "30", UIMax = "100"))
	int32 ImplicitSamplesPerBone = 50;

	/** HRBF centres for the palm group (hand + metacarpals). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (ClampMin = "12", ClampMax = "200", UIMin = "50", UIMax = "160"))
	int32 ImplicitPalmSamples = 100;

	/**
	 * cm, how far another part may push a vertex out of itself in one frame. The initial pose can
	 * interpenetrate far deeper than skin ever does (a thumb lying through the fingers of a tight fist);
	 * projecting such a vertex all the way to the other part's surface sends it to the wrong side
	 * (thesis fig. 4.15). Up to this depth the contact is resolved, beyond it the vertex is frozen there
	 * and smoothed like any contact vertex.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (UIMin = "0", UIMax = "1.5"))
	float ImplicitContactDepth = 0.1f;

	/**
	 * 10-18: how much of the implicit correction is kept on the STRETCHING side of a bent joint (the back of a
	 * knuckle), 1 = all of it. The union of two rest-relative tubes meeting at an angle has a concave corner on
	 * the outer side of the bend; projecting the dorsal skin onto it dents the knuckle crest while the real skin
	 * is pulled tight and smooth there. The geometric (DQS) skin is the better model on that side, so the
	 * correction fades to this fraction where the vertex's joint is bent and the vertex sits outside the fold.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (ClampMin = "0", ClampMax = "1"))
	float ImplicitStretchKeep = 0.25f;

	/** Debug: 1 = vertex colour shows (stopped, displacement, residual) of the implicit passes (view with M_PianoHandVColor). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (ClampMin = "0", ClampMax = "3"))
	int32 ImplicitDebugMode = 0;

	/**
	 * Phase 11 (Vaillant 2014): track the iso-surface incrementally. Each frame starts from last frame's result moved
	 * by the transform difference of the vertex's own primitive instead of from the fresh geometric skinning, so a
	 * closing fold meets itself gradually and never starts deep inside the other part. Falls back to the geometric
	 * initial pose on a jump larger than ImplicitTrackMaxStepDeg (scrubbing, a new mesh, the first frame).
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit")
	bool bImplicitTracking = true;

	/** Degrees of primitive rotation between two frames above which tracking restarts from the geometric pose. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit", meta = (UIMin = "1", UIMax = "90"))
	float ImplicitTrackMaxStepDeg = 25.0f;

	/** Bump to force the implicit fields to be rebuilt (also happens when the mesh or the sample counts change). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Implicit")
	int32 ImplicitBuildSerial = 0;

	virtual UMeshDeformerInstanceSettings* CreateSettingsInstance(UMeshComponent* InMeshComponent) override;
	virtual UMeshDeformerInstance* CreateInstance(UMeshComponent* InMeshComponent, UMeshDeformerInstanceSettings* InSettings) override;
};

UCLASS()
class UPianoHandSkinDeformerInstanceSettings : public UMeshDeformerInstanceSettings
{
	GENERATED_BODY()
};

/** State owned by the render thread across frames. */
struct FPianoHandDeformerRenderState
{
	int32 LastLodIndex = INDEX_NONE;

	/**
	 * Survives between frames, which nothing else in this deformer does: two floats per LOD vertex,
	 * .x = the stretch (lambda_max - 1) seen last frame and .y = the slack accumulated since. Extracted out of the RDG
	 * graph at the end of each frame and registered back in at the start of the next.
	 */
	TRefCountPtr<FRDGPooledBuffer> RelaxStateBuffer;
	uint32 RelaxStateNumVertices = 0;
	double RelaxLastTimeSeconds = 0.0;
	bool bLoggedLayout = false;
	bool bLoggedUnsupported = false;
	bool bLoggedTensionUnavailable = false;
	/** 10-18: UV-seam weld map (canonical vertex per LOD vertex) and the LOD index buffer rewritten with it. */
	TRefCountPtr<FRDGPooledBuffer> WeldCanon;
	TRefCountPtr<FRDGPooledBuffer> WeldIndices;
	uint32 WeldNumVerts = 0;
	uint32 WeldNumIndices = 0;
	bool bLoggedWeld = false;
	bool bLoggedProportionsDQS = false;
	bool bLoggedMaskUnavailable = false;

	/** Phase 8: GPU copies of the static implicit data, keyed by FPianoHandImplicitData::BuildId. */
	uint32 ImplicitBuildId = 0;
	TRefCountPtr<FRDGPooledBuffer> ImplicitSamples;
	TRefCountPtr<FRDGPooledBuffer> ImplicitPrimInfo;
	TRefCountPtr<FRDGPooledBuffer> ImplicitPrimAxis;
	TRefCountPtr<FRDGPooledBuffer> ImplicitPrimMeta;
	TRefCountPtr<FRDGPooledBuffer> ImplicitPrimNeighbours;
	TRefCountPtr<FRDGPooledBuffer> ImplicitVertexPrim;
	TRefCountPtr<FRDGPooledBuffer> ImplicitVertexIso;
	TRefCountPtr<FRDGPooledBuffer> ImplicitVertexOverlap;
	TRefCountPtr<FRDGPooledBuffer> ImplicitVertexOwn;
	TRefCountPtr<FRDGPooledBuffer> ImplicitVertexBlend;
	TRefCountPtr<FRDGPooledBuffer> ImplicitAdjOffsets;
	TRefCountPtr<FRDGPooledBuffer> ImplicitAdjIndices;
	TRefCountPtr<FRDGPooledBuffer> ImplicitAdjWeights;
	bool bLoggedImplicit = false;
	/** Phase 11: last frame's tracked positions and the primitive transforms they were tracked under. */
	TRefCountPtr<FRDGPooledBuffer> ImplicitTracked;
	uint32 ImplicitTrackedNumVerts = 0;
	uint32 ImplicitTrackedBuildId = 0;
	TArray<FSkinBoneTransform> ImplicitPrevPrimForward;
	TArray<FSkinBoneTransform> ImplicitPrevPrimInverse;
	bool bLoggedTracking = false;
};

/** Phase 7 - per-bone capsule measured from the rest mesh (component space): origin, axis end, radius. */
struct FPianoHandBoneCapsule
{
	FVector3f Origin = FVector3f::ZeroVector;
	FVector3f End = FVector3f::ZeroVector;
	float Radius = 0.0f;
	int32 Parent = INDEX_NONE;
};

/** Game-thread cache of the capsule table, rebuilt when the mesh changes. */
struct FPianoHandCapsuleCache
{
	TWeakObjectPtr<const USkinnedAsset> Asset;
	TArray<FPianoHandBoneCapsule> Capsules;
};

/** Per-frame parameters captured on the game thread and consumed on the render thread. */
struct FPianoHandDeformerFrameParams
{
	EPianoHandSkinMode Mode = EPianoHandSkinMode::LinearBlend;
	bool bComputeTension = false;
	float TensionScale = 4.0f;
	int32 TensorSmoothIterations = 2;
	float TensorSmoothLambda = 0.6f;

	bool bDetailDisplacement = false;
	bool bRecomputeNormals = true;
	float VolumeBulge = 0.35f;
	float CreaseDepth = 0.06f;
	float CreaseSharpness = 3.0f;
	float CreaseCompressionGain = 2.0f;
	float WrinkleAmplitude = 0.05f;
	float WrinkleFrequency = 6.0f;
	float CreaseStretchRelief = 1.4f;
	float RelaxGain = 6.0f;
	float RelaxTau = 0.28f;
	float RelaxCreaseGain = 0.05f;

	/** Mask-driven primary groove (null resource = band-wide groove as before). */
	FTextureResource* WrinkleMaskResource = nullptr;
	float MaskCreaseDepth = 0.04f;
	float MaskCreaseWidth = 0.12f;
	float MaskCreaseRange = 2.0f;
	float MaskGain = 1.0f;
	float MaskSharpness = 3.0f;
	float MaskPalmSplit = 0.3f;
	float MaskPalmarBase = 0.45f;
	float MaskPalmarCompress = 2.6f;
	float MaskPalmarIron = 1.2f;
	float MaskDorsalBase = 0.4f;
	float MaskDorsalIron = 5.0f;
	float DorsalGather = 0.045f;
	float DorsalGatherSpacing = 0.24f;
	float DorsalGatherReach = 0.7f;
	float DorsalGatherBase = 0.8f;
	float DorsalGatherIron = 8.0f;
	float PalmarPadHeight = 0.05f;
	float PalmarPadDist = 0.3f;
	float PalmarPadWidth = 0.22f;
	float PalmarFold2Depth = 0.03f;
	float PalmarFold2Dist = 0.55f;
	float PalmarFold2Width = 0.1f;
	float PalmarCreaseDeepen = 0.05f;
	float PalmarFoldBendFull = 1.2f;

	/** True when any proportion scale is not 1: the render thread then skins a scaled rest pose for the strain reference. */
	bool bProportioned = false;

	/** Contact bulge. */
	bool bContactBulge = false;
	float ContactMargin = 0.06f;
	float BulgeGain = 0.0f;
	float BulgeReach = 1.1f;
	float BulgeSpread = 0.35f;
	float BendStart = 15.0f;
	float BendFull = 90.0f;
	float CapsuleRadiusScale = 1.0f;
	float DorsalTighten = 0.05f;

	/** Phase 8: implicit skinning. */
	bool bImplicitSkinning = false;
	int32 ImplicitIterations = 12;
	float ImplicitSigma = 0.35f;
	float ImplicitStopAngle = 55.0f;
	float ImplicitMaxStep = 0.3f;
	float ImplicitTolerance = 0.002f;
	float ImplicitRelax = 1.0f;
	int32 ImplicitBetaDiffusion = 4;
	int32 ImplicitSmoothIterations = 4;
	float ImplicitSmoothBeta = 1.0f;
	float ImplicitBulge = 0.0f;
	float ImplicitBulgeStart = 15.0f;
	float ImplicitBulgeFull = 70.0f;
	float ImplicitBendStart = 10.0f;
	float ImplicitBendFull = 40.0f;
	int32 ImplicitDebugMode = 0;
	float ImplicitContactDepth = 0.1f;
	float ImplicitStretchKeep = 0.25f;
	bool bImplicitTracking = true;
	float ImplicitTrackMaxStepDeg = 25.0f;
};


UCLASS()
class UPianoHandSkinDeformerInstance : public UMeshDeformerInstance
{
	GENERATED_BODY()

public:
	void Init(USkinnedMeshComponent* InComponent, UPianoHandSkinDeformer* InDeformer);

	//~ UMeshDeformerInstance
	virtual void AllocateResources() override;
	virtual void ReleaseResources() override;
	virtual void EnqueueWork(FEnqueueWorkDesc const& InDesc) override;
	virtual EMeshDeformerOutputBuffer GetOutputBuffers() const override;
#if WITH_EDITORONLY_DATA
	virtual bool RequestReadbackDeformerGeometry(TUniquePtr<FMeshDeformerGeometryReadbackRequest> InRequest) override { return false; }
#endif
	virtual UMeshDeformerInstance* GetInstanceForSourceDeformer() override { return this; }

	/** Number of frames the deformer actually dispatched (game-thread counter, for verification). */
	UPROPERTY(Transient, BlueprintReadOnly, Category = "PianoHand")
	int32 EnqueuedFrames = 0;

private:
	UPROPERTY(Transient)
	TWeakObjectPtr<USkinnedMeshComponent> Component;

	/** Source deformer; its properties are re-read every frame so edits apply live. */
	UPROPERTY(Transient)
	TWeakObjectPtr<UPianoHandSkinDeformer> Deformer;

	EPianoHandSkinMode SkinMode = EPianoHandSkinMode::LinearBlend;
	TSharedPtr<FPianoHandDeformerRenderState, ESPMode::ThreadSafe> RenderState;
	FPianoHandCapsuleCache CapsuleCache;

	/** Phase 8: implicit fields, built once per mesh / sample count / serial. */
	TSharedPtr<FPianoHandImplicitData, ESPMode::ThreadSafe> ImplicitData;
	TWeakObjectPtr<const USkinnedAsset> ImplicitAsset;
	int32 ImplicitSamplesBuilt = 0;
	int32 ImplicitPalmSamplesBuilt = 0;
	int32 ImplicitSerialBuilt = -1;

public:
	/** Summary of the implicit build ("" when none). */
	FString GetImplicitSummary() const { return ImplicitData.IsValid() ? ImplicitData->Summary : FString(); }
	void InvalidateImplicitData() { ImplicitData.Reset(); ImplicitAsset.Reset(); }
};

UCLASS()
class PIANOHAND_SIMULATOR_API UPianoHandSkinningLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/** Attach the custom compute-shader skinning deformer to a skinned mesh component. Returns the deformer object. */
	UFUNCTION(BlueprintCallable, Category = "PianoHand|Skinning")
	static UPianoHandSkinDeformer* ApplyCustomSkinning(USkinnedMeshComponent* Component, EPianoHandSkinMode Mode = EPianoHandSkinMode::LinearBlend, bool bComputeTension = true, float TensionScale = 4.0f, bool bDetailDisplacement = false);

	/** Detach any mesh deformer and return the component to engine GPU skinning. */
	UFUNCTION(BlueprintCallable, Category = "PianoHand|Skinning")
	static void RemoveCustomSkinning(USkinnedMeshComponent* Component);

	/** Returns how many frames the custom deformer on this component has dispatched so far (-1 if none attached). */
	UFUNCTION(BlueprintCallable, Category = "PianoHand|Skinning")
	static int32 GetCustomSkinningFrameCount(USkinnedMeshComponent* Component);

	/** Returns the custom deformer attached to the component (nullptr if none). */
	UFUNCTION(BlueprintCallable, Category = "PianoHand|Skinning")
	static UPianoHandSkinDeformer* GetCustomSkinDeformer(USkinnedMeshComponent* Component);

	/** Phase 5 - set the hand proportions on the component's custom deformer. Returns false if none is attached. */
	UFUNCTION(BlueprintCallable, Category = "PianoHand|Proportions")
	static bool SetHandProportions(USkinnedMeshComponent* Component, const FPianoHandProportions& Proportions);

	/** Phase 5 - measure the mesh's reference pose: palm length / width and every finger's segment lengths, in cm. */
	UFUNCTION(BlueprintCallable, Category = "PianoHand|Proportions")
	static FPianoHandMeasurements MeasureHand(USkinnedMeshComponent* Component);

	/**
	 * Phase 5 - scale factors that turn this mesh into a hand with the given measurements (cm). Zero
	 * entries are left at 1. Thickness is not measured here; it stays 1 unless set afterwards.
	 */
	UFUNCTION(BlueprintCallable, Category = "PianoHand|Proportions")
	static FPianoHandProportions ProportionsFromMeasurements(USkinnedMeshComponent* Component, const FPianoHandMeasurements& Target);

	/** Phase 5 - bone-name lookup used by the proportions: finger 0..4 = thumb..pinky, segment 0..2 = proximal..distal (thumb: metacarpal..distal), 3 = the metacarpal. INDEX_NONE if missing. */
	static int32 FindHandBone(const USkinnedMeshComponent* Component, int32 Finger, int32 Segment);
	static int32 FindHandRootBone(const USkinnedMeshComponent* Component);

	/** Phase 8 - one-line summary of the implicit skinning fields built for this component ("" if none yet). */
	UFUNCTION(BlueprintCallable, Category = "PianoHand|Implicit")
	static FString GetImplicitSkinningSummary(USkinnedMeshComponent* Component);

	/** Phase 8 - drop the implicit fields so they are rebuilt on the next frame. */
	UFUNCTION(BlueprintCallable, Category = "PianoHand|Implicit")
	static void RebuildImplicitSkinning(USkinnedMeshComponent* Component);
};
