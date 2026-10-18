// PianoHand custom skinning - GPU smoke test.
//
// Console command:  PianoHand.SkinningSmokeTest
// Command line   :  -ExecCmds="PianoHand.SkinningSmokeTest" [-SkinningTestAutoQuit]
//
// Builds a tiny 2-bone test mesh, dispatches the LBS and DQS kernels, reads the
// results back and compares them against a CPU reference. Verifies that the
// shader directory mapping, the global shader, the RDG dispatch and the readback
// path all work before the kernel is wired to a real skeletal mesh.

#include "CustomSkinningShader.h"
#include "../pianohand_simulator.h"

#include "HAL/IConsoleManager.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "RenderGraphBuilder.h"
#include "RenderGraphUtils.h"
#include "RHIGPUReadback.h"
#include "RenderingThread.h"

namespace
{
	struct FSmokeTestMesh
	{
		TArray<FVector3f> Positions;
		TArray<FVector3f> Normals;
		TArray<FIntVector4> BoneIndices;
		TArray<FVector4f> BoneWeights;
		TArray<FSkinBoneTransform> BoneTransforms;
		TArray<FMatrix44f> BoneMatrices; // CPU reference
	};

	FSmokeTestMesh BuildTestMesh()
	{
		FSmokeTestMesh Mesh;

		// Bone 0: identity. Bone 1: rotate 90 deg about Z, then translate (10, 0, 0).
		Mesh.BoneMatrices.Add(FMatrix44f::Identity);
		Mesh.BoneMatrices.Add(FTransform3f(FQuat4f(FVector3f::ZAxisVector, HALF_PI), FVector3f(10.f, 0.f, 0.f)).ToMatrixWithScale());
		for (const FMatrix44f& M : Mesh.BoneMatrices)
		{
			Mesh.BoneTransforms.Add(FSkinBoneTransform::FromMatrix(M));
		}

		const FVector3f BasePositions[4] = {
			FVector3f(1.f, 0.f, 0.f), FVector3f(0.f, 1.f, 0.f), FVector3f(0.f, 0.f, 1.f), FVector3f(1.f, 2.f, 3.f) };
		const FVector3f BaseNormals[4] = {
			FVector3f(1.f, 0.f, 0.f), FVector3f(0.f, 1.f, 0.f), FVector3f(0.f, 0.f, 1.f), FVector3f(1.f, 1.f, 1.f).GetSafeNormal() };

		// Group 0: fully bone 0. Group 1: fully bone 1. Group 2: 50/50 blend.
		const FVector4f Weights[3] = { FVector4f(1.f, 0.f, 0.f, 0.f), FVector4f(0.f, 1.f, 0.f, 0.f), FVector4f(0.5f, 0.5f, 0.f, 0.f) };
		for (int32 Group = 0; Group < 3; ++Group)
		{
			for (int32 i = 0; i < 4; ++i)
			{
				Mesh.Positions.Add(BasePositions[i]);
				Mesh.Normals.Add(BaseNormals[i]);
				Mesh.BoneIndices.Add(FIntVector4(0, 1, 0, 0));
				Mesh.BoneWeights.Add(Weights[Group]);
			}
		}
		return Mesh;
	}

	/** CPU linear blend skinning reference. */
	void ComputeLBSReference(const FSmokeTestMesh& Mesh, TArray<FVector3f>& OutPositions, TArray<FVector3f>& OutNormals)
	{
		OutPositions.SetNum(Mesh.Positions.Num());
		OutNormals.SetNum(Mesh.Positions.Num());
		for (int32 v = 0; v < Mesh.Positions.Num(); ++v)
		{
			FVector3f P = FVector3f::ZeroVector;
			FVector3f N = FVector3f::ZeroVector;
			for (int32 i = 0; i < 4; ++i)
			{
				const float W = Mesh.BoneWeights[v][i];
				if (W > 0.f)
				{
					const FMatrix44f& M = Mesh.BoneMatrices[Mesh.BoneIndices[v][i]];
					P += W * M.TransformPosition(Mesh.Positions[v]);
					N += W * M.TransformVector(Mesh.Normals[v]);
				}
			}
			OutPositions[v] = P;
			OutNormals[v] = N.GetSafeNormal();
		}
	}

	bool ReadbackFloat3(FRHICommandListImmediate& RHICmdList, FRHIGPUBufferReadback& Readback, int32 Num, TArray<FVector3f>& Out)
	{
		// Wait until the copy has been executed by the GPU.
		int32 Spins = 0;
		while (!Readback.IsReady())
		{
			RHICmdList.BlockUntilGPUIdle();
			if (++Spins > 1000)
			{
				return false;
			}
			FPlatformProcess::Sleep(0.001f);
		}
		const uint32 NumBytes = Num * sizeof(FVector3f);
		const FVector3f* Data = static_cast<const FVector3f*>(Readback.Lock(NumBytes));
		if (!Data)
		{
			return false;
		}
		Out.SetNumUninitialized(Num);
		FMemory::Memcpy(Out.GetData(), Data, NumBytes);
		Readback.Unlock();
		return true;
	}

	struct FModeResult
	{
		ECustomSkinMode Mode;
		bool bReadbackOk = false;
		TArray<FVector3f> Positions;
		TArray<FVector3f> Normals;
	};

	void RunSkinningSmokeTest()
	{
		UE_LOG(LogPianoHand, Log, TEXT("[SkinningSmokeTest] Enqueueing GPU skinning test..."));

		FSmokeTestMesh Mesh = BuildTestMesh();
		TArray<FVector3f> RefPositions, RefNormals;
		ComputeLBSReference(Mesh, RefPositions, RefNormals);

		const bool bAutoQuit = FParse::Param(FCommandLine::Get(), TEXT("SkinningTestAutoQuit"));

		ENQUEUE_RENDER_COMMAND(PianoHandSkinningSmokeTest)(
			[Mesh = MoveTemp(Mesh), RefPositions = MoveTemp(RefPositions), RefNormals = MoveTemp(RefNormals), bAutoQuit](FRHICommandListImmediate& RHICmdList)
			{
				const int32 NumVerts = Mesh.Positions.Num();
				const ECustomSkinMode Modes[2] = { ECustomSkinMode::LinearBlend, ECustomSkinMode::DualQuaternion };
				TArray<FModeResult> Results;

				for (ECustomSkinMode Mode : Modes)
				{
					FModeResult& Result = Results.AddDefaulted_GetRef();
					Result.Mode = Mode;

					FRHIGPUBufferReadback ReadbackPos(TEXT("PianoHand.SmokeTest.ReadbackPos"));
					FRHIGPUBufferReadback ReadbackNrm(TEXT("PianoHand.SmokeTest.ReadbackNrm"));
					{
						FRDGBuilder GraphBuilder(RHICmdList, RDG_EVENT_NAME("PianoHandSkinningSmokeTest"));

						FCustomSkinningRDGInputs Inputs;
						Inputs.NumVertices = NumVerts;
						Inputs.NumBones = Mesh.BoneTransforms.Num();
						Inputs.RestPositions = CreateStructuredBuffer(GraphBuilder, TEXT("PianoHand.SmokeTest.RestPositions"), Mesh.Positions);
						Inputs.RestNormals = CreateStructuredBuffer(GraphBuilder, TEXT("PianoHand.SmokeTest.RestNormals"), Mesh.Normals);
						Inputs.BoneIndices = CreateStructuredBuffer(GraphBuilder, TEXT("PianoHand.SmokeTest.BoneIndices"), Mesh.BoneIndices);
						Inputs.BoneWeights = CreateStructuredBuffer(GraphBuilder, TEXT("PianoHand.SmokeTest.BoneWeights"), Mesh.BoneWeights);
						Inputs.BoneTransforms = CreateStructuredBuffer(GraphBuilder, TEXT("PianoHand.SmokeTest.BoneTransforms"), Mesh.BoneTransforms);

						const FCustomSkinningRDGOutputs Outputs = CustomSkinning::AddSkinningPass(GraphBuilder, Inputs, Mode);

						AddEnqueueCopyPass(GraphBuilder, &ReadbackPos, Outputs.Positions, NumVerts * sizeof(FVector3f));
						AddEnqueueCopyPass(GraphBuilder, &ReadbackNrm, Outputs.Normals, NumVerts * sizeof(FVector3f));
						GraphBuilder.Execute();
					}
					RHICmdList.SubmitCommandsAndFlushGPU();
					RHICmdList.BlockUntilGPUIdle();

					Result.bReadbackOk =
						ReadbackFloat3(RHICmdList, ReadbackPos, NumVerts, Result.Positions) &&
						ReadbackFloat3(RHICmdList, ReadbackNrm, NumVerts, Result.Normals);
				}

				// ---- Validate ----
				const float Tolerance = 1e-3f;
				bool bAllPassed = true;
				for (const FModeResult& Result : Results)
				{
					const TCHAR* ModeName = Result.Mode == ECustomSkinMode::LinearBlend ? TEXT("LBS") : TEXT("DQS");
					if (!Result.bReadbackOk)
					{
						UE_LOG(LogPianoHand, Error, TEXT("[SkinningSmokeTest] %s: GPU readback failed"), ModeName);
						bAllPassed = false;
						continue;
					}

					int32 NumMismatch = 0;
					for (int32 v = 0; v < NumVerts; ++v)
					{
						// Vertices with a single influence must match the CPU reference exactly in both modes.
						// Blended vertices are only compared for LBS (DQS legitimately differs there); DQS must at least be finite.
						const bool bSingleInfluence = Mesh.BoneWeights[v].X == 1.f || Mesh.BoneWeights[v].Y == 1.f;
						const bool bCompare = bSingleInfluence || Result.Mode == ECustomSkinMode::LinearBlend;

						const bool bFinite = Result.Positions[v].ContainsNaN() == false && Result.Normals[v].ContainsNaN() == false;
						const bool bMatch = !bCompare ||
							(Result.Positions[v].Equals(RefPositions[v], Tolerance) && Result.Normals[v].Equals(RefNormals[v], Tolerance));

						if (!bFinite || !bMatch)
						{
							++NumMismatch;
							UE_LOG(LogPianoHand, Error, TEXT("[SkinningSmokeTest] %s v%d: gpu P=%s N=%s | ref P=%s N=%s"),
								ModeName, v, *Result.Positions[v].ToString(), *Result.Normals[v].ToString(),
								*RefPositions[v].ToString(), *RefNormals[v].ToString());
						}
					}

					if (NumMismatch == 0)
					{
						UE_LOG(LogPianoHand, Display, TEXT("[SkinningSmokeTest] %s: PASS (%d vertices). Sample v8 (50/50 blend): P=%s"),
							ModeName, NumVerts, *Result.Positions[8].ToString());
					}
					else
					{
						UE_LOG(LogPianoHand, Error, TEXT("[SkinningSmokeTest] %s: FAIL (%d/%d mismatches)"), ModeName, NumMismatch, NumVerts);
						bAllPassed = false;
					}
				}

				UE_LOG(LogPianoHand, Display, TEXT("[SkinningSmokeTest] RESULT: %s"), bAllPassed ? TEXT("PASS") : TEXT("FAIL"));

				if (bAutoQuit)
				{
					AsyncTask(ENamedThreads::GameThread, [bAllPassed]()
					{
						FPlatformMisc::RequestExitWithStatus(false, bAllPassed ? 0 : 1);
					});
				}
			});
	}

	FAutoConsoleCommand GSkinningSmokeTestCmd(
		TEXT("PianoHand.SkinningSmokeTest"),
		TEXT("Dispatches the custom skinning compute shader (LBS + DQS) on a tiny test mesh and validates the readback against a CPU reference."),
		FConsoleCommandDelegate::CreateStatic(&RunSkinningSmokeTest));
}
