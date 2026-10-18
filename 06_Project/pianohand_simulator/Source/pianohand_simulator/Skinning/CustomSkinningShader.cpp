#include "CustomSkinningShader.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "DataDrivenShaderPlatformInfo.h"

IMPLEMENT_GLOBAL_SHADER(FCustomSkinningCS, "/PianoHand/Private/CustomSkinning.usf", "MainCS", SF_Compute);

bool FCustomSkinningCS::ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters)
{
	return IsFeatureLevelSupported(Parameters.Platform, ERHIFeatureLevel::SM5);
}

void FCustomSkinningCS::ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment)
{
	FGlobalShader::ModifyCompilationEnvironment(Parameters, OutEnvironment);
	OutEnvironment.SetDefine(TEXT("THREADGROUP_SIZE"), ThreadGroupSize);
}

FCustomSkinningRDGOutputs CustomSkinning::AddSkinningPass(
	FRDGBuilder& GraphBuilder,
	const FCustomSkinningRDGInputs& Inputs,
	ECustomSkinMode Mode)
{
	check(IsInRenderingThread());
	check(Inputs.NumVertices > 0 && Inputs.NumBones > 0);

	FCustomSkinningRDGOutputs Outputs;
	Outputs.Positions = GraphBuilder.CreateBuffer(
		FRDGBufferDesc::CreateStructuredDesc(sizeof(FVector3f), Inputs.NumVertices), TEXT("PianoHand.Skinning.OutPositions"));
	Outputs.Normals = GraphBuilder.CreateBuffer(
		FRDGBufferDesc::CreateStructuredDesc(sizeof(FVector3f), Inputs.NumVertices), TEXT("PianoHand.Skinning.OutNormals"));

	FCustomSkinningCS::FParameters* Params = GraphBuilder.AllocParameters<FCustomSkinningCS::FParameters>();
	Params->NumVertices = Inputs.NumVertices;
	Params->NumBones = Inputs.NumBones;
	Params->RestPositions = GraphBuilder.CreateSRV(Inputs.RestPositions);
	Params->RestNormals = GraphBuilder.CreateSRV(Inputs.RestNormals);
	Params->BoneIndices = GraphBuilder.CreateSRV(Inputs.BoneIndices);
	Params->BoneWeights = GraphBuilder.CreateSRV(Inputs.BoneWeights);
	Params->BoneTransforms = GraphBuilder.CreateSRV(Inputs.BoneTransforms);
	Params->OutPositions = GraphBuilder.CreateUAV(Outputs.Positions);
	Params->OutNormals = GraphBuilder.CreateUAV(Outputs.Normals);

	FCustomSkinningCS::FPermutationDomain PermutationVector;
	PermutationVector.Set<FCustomSkinningCS::FSkinModeDim>(static_cast<int32>(Mode));
	TShaderMapRef<FCustomSkinningCS> ComputeShader(GetGlobalShaderMap(GMaxRHIFeatureLevel), PermutationVector);

	FComputeShaderUtils::AddPass(
		GraphBuilder,
		RDG_EVENT_NAME("PianoHand.CustomSkinning(%s, %u verts)", Mode == ECustomSkinMode::LinearBlend ? TEXT("LBS") : TEXT("DQS"), Inputs.NumVertices),
		ComputeShader,
		Params,
		FComputeShaderUtils::GetGroupCount(Inputs.NumVertices, FCustomSkinningCS::ThreadGroupSize));

	return Outputs;
}
