// PianoHand custom GPU skinning - global compute shader + RDG dispatch helper

#pragma once

#include "CoreMinimal.h"
#include "GlobalShader.h"
#include "ShaderParameterStruct.h"
#include "RenderGraphResources.h"

class FRDGBuilder;

/** Matches FBoneTransform in Shaders/Public/SkinningCommon.ush (3 rows of an affine matrix). */
struct FSkinBoneTransform
{
	FVector4f Row0;
	FVector4f Row1;
	FVector4f Row2;

	/** Build from a UE row-vector matrix (v' = v * M, translation in M[3]). */
	static FSkinBoneTransform FromMatrix(const FMatrix44f& M)
	{
		FSkinBoneTransform T;
		T.Row0 = FVector4f(M.M[0][0], M.M[1][0], M.M[2][0], M.M[3][0]);
		T.Row1 = FVector4f(M.M[0][1], M.M[1][1], M.M[2][1], M.M[3][1]);
		T.Row2 = FVector4f(M.M[0][2], M.M[1][2], M.M[2][2], M.M[3][2]);
		return T;
	}
};
static_assert(sizeof(FSkinBoneTransform) == 48, "FSkinBoneTransform must be 48 bytes to match HLSL");

enum class ECustomSkinMode : uint8
{
	LinearBlend = 0,
	DualQuaternion = 1,
};

/** Compute shader: blends rest-space vertices by up to 4 bone influences. */
class FCustomSkinningCS : public FGlobalShader
{
public:
	DECLARE_GLOBAL_SHADER(FCustomSkinningCS);
	SHADER_USE_PARAMETER_STRUCT(FCustomSkinningCS, FGlobalShader);

	static constexpr uint32 ThreadGroupSize = 64;

	class FSkinModeDim : SHADER_PERMUTATION_INT("SKIN_MODE", 2);
	using FPermutationDomain = TShaderPermutationDomain<FSkinModeDim>;

	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER(uint32, NumVertices)
		SHADER_PARAMETER(uint32, NumBones)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float3>, RestPositions)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float3>, RestNormals)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint4>, BoneIndices)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float4>, BoneWeights)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<FBoneTransform>, BoneTransforms)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<float3>, OutPositions)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<float3>, OutNormals)
	END_SHADER_PARAMETER_STRUCT()

	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters);
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment);
};

/** RDG-side inputs for one skinning dispatch. All buffers are structured buffers created on the same FRDGBuilder. */
struct FCustomSkinningRDGInputs
{
	uint32 NumVertices = 0;
	uint32 NumBones = 0;
	FRDGBufferRef RestPositions = nullptr;   // float3
	FRDGBufferRef RestNormals = nullptr;     // float3
	FRDGBufferRef BoneIndices = nullptr;     // uint4
	FRDGBufferRef BoneWeights = nullptr;     // float4
	FRDGBufferRef BoneTransforms = nullptr;  // FSkinBoneTransform
};

struct FCustomSkinningRDGOutputs
{
	FRDGBufferRef Positions = nullptr;       // float3
	FRDGBufferRef Normals = nullptr;         // float3
};

namespace CustomSkinning
{
	/**
	 * Adds the skinning compute pass to the graph. Output buffers are created here.
	 * Must be called on the render thread.
	 */
	FCustomSkinningRDGOutputs AddSkinningPass(
		FRDGBuilder& GraphBuilder,
		const FCustomSkinningRDGInputs& Inputs,
		ECustomSkinMode Mode);
}
