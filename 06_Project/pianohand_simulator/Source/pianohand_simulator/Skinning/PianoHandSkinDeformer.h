// PianoHand custom GPU skinning - UMeshDeformer integration (Phase 1) + per-vertex tension (Phase 2)
//
// UPianoHandSkinDeformer      : deformer asset/object assigned to a USkinnedMeshComponent via SetMeshDeformer()
// UPianoHandSkinDeformerInstance : per-component instance; every frame it uploads RefPoseInverse*ComponentSpace
//                                   bone transforms and dispatches the CustomSkinningDeformer.usf kernel that
//                                   writes directly into the engine passthrough vertex factory buffers.
//                                   When tension output is enabled it then runs CustomSkinningTension.usf
//                                   (edge strain vs rest pose) and writes the result to the vertex colour buffer.
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
#include "PianoHandSkinDeformer.generated.h"

class USkinnedMeshComponent;
class FSkeletalMeshObject;

UENUM(BlueprintType)
enum class EPianoHandSkinMode : uint8
{
	LinearBlend    UMETA(DisplayName = "Linear Blend (LBS)"),
	DualQuaternion UMETA(DisplayName = "Dual Quaternion (DQS)"),
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
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<float>, PositionBufferUAV)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<SNORM float4>, TangentBufferUAV)
	END_SHADER_PARAMETER_STRUCT()

	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters);
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment);
};

/** Phase 2 - per-triangle edge strain accumulation (atomic, fixed point). */
class FPianoHandTensionAccumulateCS : public FGlobalShader
{
public:
	DECLARE_GLOBAL_SHADER(FPianoHandTensionAccumulateCS);
	SHADER_USE_PARAMETER_STRUCT(FPianoHandTensionAccumulateCS, FGlobalShader);

	static constexpr uint32 ThreadGroupSize = 64;

	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER(uint32, NumTriangles)
		SHADER_PARAMETER(uint32, BaseIndex)
		SHADER_PARAMETER_SRV(Buffer<uint>, IndexBuffer)
		SHADER_PARAMETER_SRV(Buffer<float>, RestPositionBuffer)
		SHADER_PARAMETER_RDG_BUFFER_SRV(Buffer<float>, SkinnedPositionBuffer)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<int>, StrainAccum)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<uint>, StrainCount)
	END_SHADER_PARAMETER_STRUCT()

	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters);
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment);
};

/** Phase 2 - per-vertex strain average -> vertex colour. */
class FPianoHandTensionResolveCS : public FGlobalShader
{
public:
	DECLARE_GLOBAL_SHADER(FPianoHandTensionResolveCS);
	SHADER_USE_PARAMETER_STRUCT(FPianoHandTensionResolveCS, FGlobalShader);

	static constexpr uint32 ThreadGroupSize = 64;

	BEGIN_SHADER_PARAMETER_STRUCT(FParameters, )
		SHADER_PARAMETER(uint32, NumVertices)
		SHADER_PARAMETER(float, TensionScale)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<int>, StrainAccumIn)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<uint>, StrainCountIn)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<UNORM float4>, ColorBufferUAV)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWStructuredBuffer<float>, VertexStrainOut)
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
		SHADER_PARAMETER_SRV(Buffer<float>, RestPositionBuffer)
		SHADER_PARAMETER_SRV(Buffer<uint>, InputWeightStream)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<FBoneTransform>, RefPoseInverses)
		SHADER_PARAMETER_RDG_BUFFER_SRV(StructuredBuffer<float>, VertexStrain)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<float>, PositionBufferUAV)
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<SNORM float4>, TangentBufferUAV)
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
		SHADER_PARAMETER_SRV(Buffer<uint>, IndexBuffer)
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
		SHADER_PARAMETER_RDG_BUFFER_UAV(RWBuffer<SNORM float4>, TangentBufferUAV)
	END_SHADER_PARAMETER_STRUCT()

	static bool ShouldCompilePermutation(const FGlobalShaderPermutationParameters& Parameters);
	static void ModifyCompilationEnvironment(const FGlobalShaderPermutationParameters& Parameters, FShaderCompilerEnvironment& OutEnvironment);
};

/** Deformer object. Assign to a skinned mesh component with USkinnedMeshComponent::SetMeshDeformer(). */
UCLASS(BlueprintType)
class PIANOHAND_SIMULATOR_API UPianoHandSkinDeformer : public UMeshDeformer
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand")
	EPianoHandSkinMode SkinMode = EPianoHandSkinMode::LinearBlend;

	/** Compute per-vertex edge strain after skinning and write it to the vertex colour stream (R stretch, G compression, B signed). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Tension")
	bool bComputeTension = true;

	/** Multiplier from raw strain (|edge|/|rest edge| - 1) to the 0..1 colour range. 4 => 25% stretch saturates R. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Tension", meta = (ClampMin = "0.01", UIMin = "0.5", UIMax = "20"))
	float TensionScale = 4.0f;

	/** Phase 3: displace the skinned surface (volume preservation + joint creases). Requires bComputeTension. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Detail")
	bool bDetailDisplacement = false;

	/** Recompute normals from the displaced surface so the new folds actually shade. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Detail")
	bool bRecomputeNormals = true;

	/** cm of outward motion where the surface is compressed ~20%. This is the volume-preservation bulge. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Detail", meta = (UIMin = "0", UIMax = "1"))
	float VolumeBulge = 0.15f;

	/** cm, depth of the groove sitting on every joint band at rest - the crease you see on a straight finger. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Detail", meta = (UIMin = "0", UIMax = "0.5"))
	float CreaseDepth = 0.06f;

	/** Exponent narrowing the joint band. 1 = broad, 8 = a tight line right on the joint. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Detail", meta = (ClampMin = "1", UIMin = "1", UIMax = "8"))
	float CreaseSharpness = 3.0f;

	/** How much compression deepens the resting crease. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Detail", meta = (UIMin = "0", UIMax = "5"))
	float CreaseCompressionGain = 2.0f;

	/** cm, bending-only ripples inside the joint band (needs vertex density / tessellation to read). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Detail", meta = (UIMin = "0", UIMax = "0.3"))
	float WrinkleAmplitude = 0.05f;

	/** Radians per cm along the bone axis - controls how many ripples fit on a segment. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "PianoHand|Detail", meta = (UIMin = "0", UIMax = "30"))
	float WrinkleFrequency = 6.0f;

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
	bool bLoggedLayout = false;
	bool bLoggedUnsupported = false;
	bool bLoggedTensionUnavailable = false;
};

/** Per-frame parameters captured on the game thread and consumed on the render thread. */
struct FPianoHandDeformerFrameParams
{
	EPianoHandSkinMode Mode = EPianoHandSkinMode::LinearBlend;
	bool bComputeTension = false;
	float TensionScale = 4.0f;

	bool bDetailDisplacement = false;
	bool bRecomputeNormals = true;
	float VolumeBulge = 0.15f;
	float CreaseDepth = 0.06f;
	float CreaseSharpness = 3.0f;
	float CreaseCompressionGain = 2.0f;
	float WrinkleAmplitude = 0.05f;
	float WrinkleFrequency = 6.0f;
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
};
