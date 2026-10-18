// PianoHand implicit skinning - the once-per-mesh precomputation (Vaillant et al. 2013, sections 3-4).
//
//  1. Partition the rest mesh by dominant skin weight. The hand and the four metacarpals form one
//     "palm" part (they barely move relative to each other); every phalanx and the thumb metacarpal
//     is a part of its own.
//  2. For every part, pick ~50 HRBF centres (farthest point sampling of the part vertices, after
//     culling the vertices within h = 5 % of the bone length of a joint, eq. 4.2 of the thesis), and
//     add the closure centres: one on the bone line at distance s_j from each joint, s_j being the
//     distance from the joint to the nearest vertex of the part, normal along the bone and pointing
//     outward. Two neighbouring parts are then closed by spherical caps of the same radius centred
//     at the joint, so they slide over each other without a gap or a bump when the joint bends.
//  3. Fit the Hermite RBF d(u) = sum a_k phi(|u - p_k|) + b_k . grad phi(|u - p_k|), phi(r) = r^3, with
//     d(p_k) = 0 and grad d(p_k) = n_k (4N x 4N dense system, LU with partial pivoting in double),
//     in normalised bone coordinates u = (x - origin) / s, s = distance from the bone to the
//     farthest centre, so the compact remap tr has radius 1 and f = 1 is reached on the bone only.
//  4. Store every vertex's rest iso-value f(v) of the composed field (max over the part's own field
//     and its joint partners; at rest the gradient controllers are 0, so the composition is a union).
//  5. One-ring adjacency with mean value coordinates (Hormann & Floater 2006) for the tangential
//     relaxation, uniform weights where the ring is open (mesh boundary, UV seam).

#include "PianoHandSkinDeformer.h"
#include "../pianohand_simulator.h"

#include "Components/SkinnedMeshComponent.h"
#include "Engine/SkinnedAsset.h"
#include "ReferenceSkeleton.h"
#include "Rendering/SkeletalMeshRenderData.h"
#include "Rendering/SkeletalMeshLODRenderData.h"
#include "Rendering/SkinWeightVertexBuffer.h"
#include "Rendering/MultiSizeIndexContainer.h"
#include "Rendering/PositionVertexBuffer.h"
#include "GPUSkinPublicDefs.h"

namespace PianoHandImplicit
{
	struct FClosure
	{
		FVector3f Joint;
		FVector3f Outward;   // unit, points away from the part
	};

	struct FPart
	{
		FName Name;
		int32 MainBone = INDEX_NONE;    // bone whose transform carries the field
		TArray<int32> Bones;            // bones whose dominated vertices belong to the part
		TArray<int32> Verts;
		FVector3f Origin = FVector3f::ZeroVector;
		FVector3f End = FVector3f::ZeroVector;
		FVector3f Dir = FVector3f::XAxisVector;
		bool bPalm = false;
		int32 Parent = INDEX_NONE;      // part index
		TArray<int32> Children;         // part indices
		TArray<FClosure> Closures;
		int32 Finger = INDEX_NONE;
		int32 Segment = INDEX_NONE;

		// fitted
		float Scale = 1.0f;
		TArray<FVector3f> Centers;      // normalised
		TArray<FVector3f> Normals;
		TArray<float> Alpha;
		TArray<FVector3f> Beta;
		float FitResidual = 0.0f;
	};

	/** Dense LU with partial pivoting, in place. Returns false on a singular pivot. */
	static bool SolveDense(TArray<double>& A, TArray<double>& B, int32 N)
	{
		for (int32 Col = 0; Col < N; ++Col)
		{
			int32 Pivot = Col;
			double Best = FMath::Abs(A[Col * N + Col]);
			for (int32 Row = Col + 1; Row < N; ++Row)
			{
				const double V = FMath::Abs(A[Row * N + Col]);
				if (V > Best) { Best = V; Pivot = Row; }
			}
			if (Best < 1e-14)
			{
				return false;
			}
			if (Pivot != Col)
			{
				for (int32 K = 0; K < N; ++K) { Swap(A[Col * N + K], A[Pivot * N + K]); }
				Swap(B[Col], B[Pivot]);
			}
			const double Inv = 1.0 / A[Col * N + Col];
			for (int32 Row = Col + 1; Row < N; ++Row)
			{
				const double F = A[Row * N + Col] * Inv;
				if (F == 0.0) { continue; }
				double* R = &A[Row * N];
				const double* P = &A[Col * N];
				for (int32 K = Col; K < N; ++K) { R[K] -= F * P[K]; }
				B[Row] -= F * B[Col];
			}
		}
		for (int32 Row = N - 1; Row >= 0; --Row)
		{
			double Sum = B[Row];
			const double* R = &A[Row * N];
			for (int32 K = Row + 1; K < N; ++K) { Sum -= R[K] * B[K]; }
			B[Row] = Sum / R[Row];
		}
		return true;
	}

	static float PointSegmentDistance(const FVector3f& P, const FVector3f& A, const FVector3f& B)
	{
		const FVector3f AB = B - A;
		const float L2 = FMath::Max(AB.SizeSquared(), 1e-8f);
		const float T = FMath::Clamp(FVector3f::DotProduct(P - A, AB) / L2, 0.0f, 1.0f);
		return (P - (A + AB * T)).Size();
	}

	/** Farthest point sampling: Count indices out of Candidates, spread as evenly as possible. */
	static void FarthestPointSample(const TArray<FVector3f>& Pos, const TArray<int32>& Candidates, int32 Count, TArray<int32>& Out)
	{
		Out.Reset();
		if (Candidates.Num() == 0) { return; }
		Count = FMath::Min(Count, Candidates.Num());
		FVector3f Centroid = FVector3f::ZeroVector;
		for (int32 V : Candidates) { Centroid += Pos[V]; }
		Centroid /= (float)Candidates.Num();
		int32 Start = Candidates[0];
		float Far = -1.0f;
		for (int32 V : Candidates)
		{
			const float D = (Pos[V] - Centroid).SizeSquared();
			if (D > Far) { Far = D; Start = V; }
		}
		TArray<float> MinDist;
		MinDist.Init(FLT_MAX, Candidates.Num());
		Out.Add(Start);
		for (int32 S = 1; S < Count; ++S)
		{
			const FVector3f Last = Pos[Out.Last()];
			int32 Best = INDEX_NONE;
			float BestD = -1.0f;
			for (int32 C = 0; C < Candidates.Num(); ++C)
			{
				const float D = (Pos[Candidates[C]] - Last).SizeSquared();
				if (D < MinDist[C]) { MinDist[C] = D; }
				if (MinDist[C] > BestD) { BestD = MinDist[C]; Best = Candidates[C]; }
			}
			if (Best == INDEX_NONE || BestD <= 0.0f) { break; }
			Out.Add(Best);
		}
	}

	/** Fit the HRBF of a part from its centres / normals (already normalised). */
	static bool FitHRBF(FPart& Part)
	{
		const int32 M = Part.Centers.Num();
		const int32 N = 4 * M;
		TArray<double> A;
		A.SetNumZeroed(N * N);
		TArray<double> B;
		B.SetNumZeroed(N);
		for (int32 J = 0; J < M; ++J)
		{
			const FVector3f& UJ = Part.Centers[J];
			B[4 * J + 1] = Part.Normals[J].X;
			B[4 * J + 2] = Part.Normals[J].Y;
			B[4 * J + 3] = Part.Normals[J].Z;
			for (int32 I = 0; I < M; ++I)
			{
				const FVector3f Vf = UJ - Part.Centers[I];
				const double V[3] = { Vf.X, Vf.Y, Vf.Z };
				const double R = FMath::Sqrt(V[0] * V[0] + V[1] * V[1] + V[2] * V[2]);
				const int32 RowV = 4 * J, ColA = 4 * I;
				A[RowV * N + ColA] = R * R * R;
				for (int32 K = 0; K < 3; ++K)
				{
					A[RowV * N + ColA + 1 + K] = 3.0 * R * V[K];
					A[(RowV + 1 + K) * N + ColA] = 3.0 * R * V[K];
				}
				if (R > 1e-12)
				{
					for (int32 Mm = 0; Mm < 3; ++Mm)
					{
						for (int32 K = 0; K < 3; ++K)
						{
							A[(RowV + 1 + Mm) * N + ColA + 1 + K] = 3.0 * (V[Mm] * V[K] / R + (Mm == K ? R : 0.0));
						}
					}
				}
			}
		}
		if (!SolveDense(A, B, N))
		{
			return false;
		}
		Part.Alpha.SetNum(M);
		Part.Beta.SetNum(M);
		for (int32 I = 0; I < M; ++I)
		{
			Part.Alpha[I] = (float)B[4 * I];
			Part.Beta[I] = FVector3f((float)B[4 * I + 1], (float)B[4 * I + 2], (float)B[4 * I + 3]);
		}
		return true;
	}

	/** d(u) and grad d(u) of a fitted part, normalised coordinates. */
	static void EvalHRBF(const FPart& Part, const FVector3f& U, float& OutD, FVector3f& OutG)
	{
		double D = 0.0;
		double G[3] = { 0, 0, 0 };
		for (int32 K = 0; K < Part.Centers.Num(); ++K)
		{
			const FVector3f Vf = U - Part.Centers[K];
			const double V[3] = { Vf.X, Vf.Y, Vf.Z };
			const double R = FMath::Sqrt(V[0] * V[0] + V[1] * V[1] + V[2] * V[2]);
			const double Bv[3] = { Part.Beta[K].X, Part.Beta[K].Y, Part.Beta[K].Z };
			const double BV = Bv[0] * V[0] + Bv[1] * V[1] + Bv[2] * V[2];
			D += Part.Alpha[K] * R * R * R + 3.0 * R * BV;
			const double InvR = (R > 1e-9) ? 1.0 / R : 0.0;
			for (int32 Mm = 0; Mm < 3; ++Mm)
			{
				G[Mm] += 3.0 * R * V[Mm] * Part.Alpha[K] + 3.0 * (V[Mm] * BV * InvR + R * Bv[Mm]);
			}
		}
		OutD = (float)D;
		OutG = FVector3f((float)G[0], (float)G[1], (float)G[2]);
	}

	/** The GPU's float32 evaluation, same operation order as ImplicitSkinning.usf, for precision checks. */
	static float EvalHRBFFloat(const FPart& Part, const FVector3f& U)
	{
		float D = 0.0f;
		for (int32 K = 0; K < Part.Centers.Num(); ++K)
		{
			const FVector3f V = U - Part.Centers[K];
			const float R = V.Size();
			const float BV = FVector3f::DotProduct(Part.Beta[K], V);
			D += Part.Alpha[K] * R * R * R + 3.0f * R * BV;
		}
		return D;
	}

	static float RemapTr(float X)
	{
		if (X <= -1.0f) return 1.0f;
		if (X >= 1.0f) return 0.0f;
		const float X2 = X * X;
		return ((-3.0f / 16.0f) * X2 * X2 + (5.0f / 8.0f) * X2 - 15.0f / 16.0f) * X + 0.5f;
	}

	static float FieldOf(const FPart& Part, const FVector3f& XRest)
	{
		const FVector3f U = (XRest - Part.Origin) / Part.Scale;
		float D; FVector3f G;
		EvalHRBF(Part, U, D, G);
		return RemapTr(D);
	}

	/** f and its gradient direction (rest component space) of a part. */
	static float FieldAndGrad(const FPart& Part, const FVector3f& XRest, FVector3f& OutG)
	{
		const FVector3f U = (XRest - Part.Origin) / Part.Scale;
		float D; FVector3f G;
		EvalHRBF(Part, U, D, G);
		const float X = FMath::Clamp(D, -1.0f, 1.0f);
		const float X2 = X * X;
		const float TrP = (FMath::Abs(D) >= 1.0f) ? 0.0f : ((-15.0f / 16.0f) * X2 * X2 + (15.0f / 8.0f) * X2 - 15.0f / 16.0f);
		OutG = G * (TrP / Part.Scale);
		return RemapTr(D);
	}

	/** Same support test as the GPU's EvalPrimBounded. */
	static bool InSupport(const FPart& Part, const FVector3f& XRest)
	{
		const FVector3f U = (XRest - Part.Origin) / Part.Scale;
		const FVector3f B = Part.Dir * ((Part.End - Part.Origin).Size() / Part.Scale);
		const float T = FMath::Clamp(FVector3f::DotProduct(U, B) / FMath::Max(FVector3f::DotProduct(B, B), 1e-6f), 0.0f, 1.0f);
		return (U - B * T).SizeSquared() <= 2.2f * 2.2f;
	}

	// 10-18: vertices duplicated along UV seams (the MetaHuman body UV splits every finger down its sides -
	// 1754 twins on the Dense hand) are one point of skin. Every pass that gathers over a one-ring or
	// accumulates per vertex (tangential relaxation, correction smoothing, strain tensor, recomputed normals)
	// must see them as one vertex, or the two copies drift apart and the seam opens into a hairline crack
	// (DQS + detail) or a see-through sliver (implicit). Canon[V] = the first vertex at the same rest position.
	int32 BuildWeldMap(const TArray<FVector3f>& Pos, TArray<uint32>& OutCanon)
	{
		const int32 NumVerts = Pos.Num();
		OutCanon.SetNumUninitialized(NumVerts);
		TMap<FIntVector, uint32> First;
		First.Reserve(NumVerts);
		int32 NumTwins = 0;
		for (int32 V = 0; V < NumVerts; ++V)
		{
			const FIntVector Key(FMath::RoundToInt(Pos[V].X * 2000.0f), FMath::RoundToInt(Pos[V].Y * 2000.0f), FMath::RoundToInt(Pos[V].Z * 2000.0f));
			if (const uint32* C = First.Find(Key))
			{
				OutCanon[V] = *C;
				++NumTwins;
			}
			else
			{
				First.Add(Key, (uint32)V);
				OutCanon[V] = (uint32)V;
			}
		}
		return NumTwins;
	}

	bool BuildWeldMap(const FSkeletalMeshLODRenderData& Lod, TArray<uint32>& OutCanon, TArray<uint32>& OutWeldedIndices, int32& OutNumTwins)
	{
		const FPositionVertexBuffer& Positions = Lod.StaticVertexBuffers.PositionVertexBuffer;
		if (!Positions.GetAllowCPUAccess() || Positions.GetNumVertices() == 0 || !Lod.MultiSizeIndexContainer.IsIndexBufferValid())
		{
			return false;
		}
		Lod.MultiSizeIndexContainer.GetIndexBuffer(OutWeldedIndices);
		if (OutWeldedIndices.Num() < 3)
		{
			return false;
		}
		const int32 NumVerts = (int32)Positions.GetNumVertices();
		TArray<FVector3f> Pos;
		Pos.SetNumUninitialized(NumVerts);
		for (int32 V = 0; V < NumVerts; ++V) { Pos[V] = Positions.VertexPosition(V); }
		OutNumTwins = BuildWeldMap(Pos, OutCanon);
		for (uint32& I : OutWeldedIndices)
		{
			if ((int32)I < NumVerts) { I = OutCanon[I]; }
		}
		return true;
	}

	void Build(const USkinnedMeshComponent* Component, const FPianoHandImplicitBuildSettings& Settings, FPianoHandImplicitData& Out)
	{
		Out.bValid = false;
		const USkinnedAsset* Asset = Component ? Component->GetSkinnedAsset() : nullptr;
		if (Asset == nullptr) { Out.Summary = TEXT("no asset"); return; }
		const FSkeletalMeshRenderData* RenderData = Asset->GetResourceForRendering();
		if (RenderData == nullptr || RenderData->LODRenderData.Num() == 0) { Out.Summary = TEXT("no render data"); return; }
		const FSkeletalMeshLODRenderData& Lod = RenderData->LODRenderData[0];
		const FPositionVertexBuffer& Positions = Lod.StaticVertexBuffers.PositionVertexBuffer;
		const FSkinWeightVertexBuffer* Weights = Lod.GetSkinWeightVertexBuffer();
		if (!Positions.GetAllowCPUAccess() || Weights == nullptr || !Weights->GetNeedsCPUAccess() || Positions.GetNumVertices() == 0)
		{
			Out.Summary = TEXT("no CPU access to positions / weights");
			return;
		}
		TArray<uint32> Indices;
		if (Lod.MultiSizeIndexContainer.IsIndexBufferValid())
		{
			Lod.MultiSizeIndexContainer.GetIndexBuffer(Indices);
		}
		if (Indices.Num() < 3)
		{
			Out.Summary = TEXT("no CPU access to the index buffer");
			return;
		}
		const int32 NumVerts = (int32)Positions.GetNumVertices();
		const FReferenceSkeleton& RefSkel = Asset->GetRefSkeleton();
		const int32 NumBones = RefSkel.GetNum();

		// ---- rest positions, dominant bone, normals -------------------------------------
		TArray<FVector3f> Pos;
		Pos.SetNumUninitialized(NumVerts);
		for (int32 V = 0; V < NumVerts; ++V) { Pos[V] = Positions.VertexPosition(V); }
		TArray<int32> Dominant;
		Dominant.Init(INDEX_NONE, NumVerts);
		TArray<int32> BestPhalanx;          // strongest phalanx influence, even where a metacarpal / the palm dominates
		BestPhalanx.Init(INDEX_NONE, NumVerts);
		// weight carried by the phalanges (thumb_01..03, *_01..03): the implicit correction is kept where this is high
		TArray<bool> IsPhalanx;
		IsPhalanx.Init(false, NumBones);
		for (int32 F = 0; F < 5; ++F)
		{
			for (int32 Seg = 0; Seg < 3; ++Seg)
			{
				const int32 Bone = UPianoHandSkinningLibrary::FindHandBone(Component, F, Seg);
				if (Bone != INDEX_NONE) { IsPhalanx[Bone] = true; }
			}
		}
		TArray<float> FingerWeight;
		FingerWeight.Init(0.0f, NumVerts);
		// 10-16: the other phalanges a vertex is weighted to (bone, weight fraction), strongest first
		TArray<FIntVector2> OtherBone;  OtherBone.Init(FIntVector2(INDEX_NONE, INDEX_NONE), NumVerts);
		TArray<FVector2f>   OtherW;     OtherW.Init(FVector2f(0.0f, 0.0f), NumVerts);
		for (const FSkelMeshRenderSection& Section : Lod.RenderSections)
		{
			for (uint32 V = Section.BaseVertexIndex; V < Section.BaseVertexIndex + Section.NumVertices && (int32)V < NumVerts; ++V)
			{
				const FSkinWeightInfo W = Weights->GetVertexSkinWeights(V);
				int32 Best = INDEX_NONE; uint16 BestW = 0;
				int32 BestPh = INDEX_NONE; uint16 BestPhW = 0;
				float Total = 0.0f, Finger = 0.0f;
				for (int32 I = 0; I < MAX_TOTAL_INFLUENCES; ++I)
				{
					if (!Section.BoneMap.IsValidIndex(W.InfluenceBones[I])) { continue; }
					const int32 Bone = (int32)Section.BoneMap[W.InfluenceBones[I]];
					const float Wf = (float)W.InfluenceWeights[I];
					Total += Wf;
					if (IsPhalanx.IsValidIndex(Bone) && IsPhalanx[Bone])
					{
						Finger += Wf;
						if (W.InfluenceWeights[I] > BestPhW) { BestPhW = W.InfluenceWeights[I]; BestPh = Bone; }
					}
					if (W.InfluenceWeights[I] > BestW)
					{
						BestW = W.InfluenceWeights[I];
						Best = Bone;
					}
				}
				Dominant[V] = Best;
				BestPhalanx[V] = BestPh;
				FingerWeight[V] = (Total > 0.0f) ? Finger / Total : 0.0f;
				// the two strongest OTHER phalanx influences
				for (int32 I = 0; I < MAX_TOTAL_INFLUENCES; ++I)
				{
					if (!Section.BoneMap.IsValidIndex(W.InfluenceBones[I])) { continue; }
					const int32 Bone = (int32)Section.BoneMap[W.InfluenceBones[I]];
					if (Bone == Best || !IsPhalanx.IsValidIndex(Bone) || !IsPhalanx[Bone] || Total <= 0.0f) { continue; }
					const float Wf = (float)W.InfluenceWeights[I] / Total;
					if (Wf > OtherW[V].X)      { OtherBone[V].Y = OtherBone[V].X; OtherW[V].Y = OtherW[V].X; OtherBone[V].X = Bone; OtherW[V].X = Wf; }
					else if (Wf > OtherW[V].Y) { OtherBone[V].Y = Bone; OtherW[V].Y = Wf; }
				}
			}
		}
		// 10-18: seam twins share one normal and (below) one ring - see BuildWeldMap
		TArray<uint32> Canon;
		const int32 NumTwins = BuildWeldMap(Pos, Canon);
		TArray<FVector3f> Normal;
		Normal.Init(FVector3f::ZeroVector, NumVerts);
		const int32 NumTris = Indices.Num() / 3;
		for (int32 T = 0; T < NumTris; ++T)
		{
			const uint32 I0 = Indices[T * 3], I1 = Indices[T * 3 + 1], I2 = Indices[T * 3 + 2];
			if ((int32)I0 >= NumVerts || (int32)I1 >= NumVerts || (int32)I2 >= NumVerts) { continue; }
			const FVector3f Face = FVector3f::CrossProduct(Pos[I2] - Pos[I0], Pos[I1] - Pos[I0]);   // same winding as the GPU normal pass
			Normal[Canon[I0]] += Face; Normal[Canon[I1]] += Face; Normal[Canon[I2]] += Face;
		}
		for (int32 V = 0; V < NumVerts; ++V) { Normal[V] = Normal[Canon[V]].GetSafeNormal(UE_SMALL_NUMBER, FVector3f::ZAxisVector); }

		// ---- reference pose, component space ---------------------------------------------
		TArray<FTransform> CS;
		{
			const TArray<FTransform>& Local = RefSkel.GetRefBonePose();
			CS.SetNum(Local.Num());
			for (int32 B = 0; B < Local.Num(); ++B)
			{
				const int32 Parent = RefSkel.GetParentIndex(B);
				CS[B] = (Parent >= 0 && Parent < B) ? Local[B] * CS[Parent] : Local[B];
			}
		}
		auto BoneOrigin = [&](int32 B) { return FVector3f(CS[B].GetTranslation()); };

		// ---- parts -----------------------------------------------------------------------
		TArray<FPart> Parts;
		TArray<int32> BoneToPart;
		BoneToPart.Init(INDEX_NONE, NumBones);
		const int32 HandRoot = UPianoHandSkinningLibrary::FindHandRootBone(Component);
		if (HandRoot == INDEX_NONE) { Out.Summary = TEXT("no hand root bone"); return; }

		// palm group: hand + metacarpals of the four fingers (+ any hand-subtree bone without a part of its own)
		{
			FPart& Palm = Parts.AddDefaulted_GetRef();
			Palm.Name = RefSkel.GetBoneName(HandRoot);
			Palm.MainBone = HandRoot;
			Palm.bPalm = true;
			Palm.Bones.Add(HandRoot);
			BoneToPart[HandRoot] = 0;
			for (int32 F = 1; F < 5; ++F)
			{
				const int32 Meta = UPianoHandSkinningLibrary::FindHandBone(Component, F, 3);
				if (Meta != INDEX_NONE && Settings.bPalmGroup) { Palm.Bones.Add(Meta); BoneToPart[Meta] = 0; }
			}
		}
		// finger parts: segments 0..2 (phalanges; thumb: metacarpal, proximal, distal) and, when the palm is
		// not grouped, segment 3 (the metacarpal of index..pinky) as a part of its own - the paper's hand
		// has 21 parts: hand + 5 metacarpals + 15 phalanges, so every MCP is a tube-to-tube joint
		int32 PartOfFinger[5][4];
		for (int32 F = 0; F < 5; ++F)
		{
			for (int32 Seg = 0; Seg < 4; ++Seg)
			{
				PartOfFinger[F][Seg] = INDEX_NONE;
				if (Seg == 3 && (F == 0 || Settings.bPalmGroup)) { continue; }
				const int32 Bone = UPianoHandSkinningLibrary::FindHandBone(Component, F, Seg);
				if (Bone == INDEX_NONE || BoneToPart[Bone] != INDEX_NONE) { continue; }
				FPart& P = Parts.AddDefaulted_GetRef();
				P.Name = RefSkel.GetBoneName(Bone);
				P.MainBone = Bone;
				P.Bones.Add(Bone);
				P.Finger = F;
				P.Segment = Seg;
				BoneToPart[Bone] = Parts.Num() - 1;
				PartOfFinger[F][Seg] = Parts.Num() - 1;
			}
		}
		// every other bone that dominates vertices goes with its nearest ancestor part (helpers, leftovers)
		for (int32 V = 0; V < NumVerts; ++V)
		{
			const int32 B = Dominant[V];
			if (B == INDEX_NONE || BoneToPart[B] != INDEX_NONE) { continue; }
			int32 Anc = RefSkel.GetParentIndex(B);
			for (int32 Guard = 0; Anc != INDEX_NONE && BoneToPart[Anc] == INDEX_NONE && Guard < 64; ++Guard) { Anc = RefSkel.GetParentIndex(Anc); }
			BoneToPart[B] = (Anc != INDEX_NONE) ? BoneToPart[Anc] : 0;
			Parts[BoneToPart[B]].Bones.Add(B);
		}
		for (int32 V = 0; V < NumVerts; ++V)
		{
			if (Dominant[V] != INDEX_NONE) { Parts[BoneToPart[Dominant[V]]].Verts.Add(V); }
		}
		// hierarchy between parts: metacarpal (if any) -> proximal -> middle -> distal, rooted at the palm
		for (int32 F = 0; F < 5; ++F)
		{
			for (int32 Seg = 0; Seg < 4; ++Seg)
			{
				const int32 P = PartOfFinger[F][Seg];
				if (P == INDEX_NONE) { continue; }
				int32 ParentPart;
				if (Seg == 3) { ParentPart = 0; }
				else if (Seg == 0) { ParentPart = (PartOfFinger[F][3] != INDEX_NONE) ? PartOfFinger[F][3] : 0; }
				else { ParentPart = PartOfFinger[F][Seg - 1]; }
				if (ParentPart != INDEX_NONE)
				{
					Parts[P].Parent = ParentPart;
					Parts[ParentPart].Children.Add(P);
				}
			}
		}
		// drop parts that are too small (their vertices stay untouched)
		TArray<bool> Alive;
		Alive.Init(true, Parts.Num());
		for (int32 P = 1; P < Parts.Num(); ++P)
		{
			if (Parts[P].Verts.Num() < Settings.MinVertices) { Alive[P] = false; }
		}

		// ---- axes and closures -----------------------------------------------------------
		for (int32 P = 0; P < Parts.Num(); ++P)
		{
			FPart& Part = Parts[P];
			if (!Alive[P]) { continue; }
			Part.Origin = BoneOrigin(Part.MainBone);
			if (Part.bPalm)
			{
				const int32 Mid = UPianoHandSkinningLibrary::FindHandBone(Component, 2, 0);
				const FVector3f Target = (Mid != INDEX_NONE) ? BoneOrigin(Mid) : (Part.Origin + FVector3f(8, 0, 0));
				Part.Dir = (Target - Part.Origin).GetSafeNormal(UE_SMALL_NUMBER, FVector3f::XAxisVector);
				Part.End = Target;
			}
			else
			{
				const int32 ChildBone = (Part.Segment == 3) ? UPianoHandSkinningLibrary::FindHandBone(Component, Part.Finger, 0)
					: (Part.Segment < 2) ? UPianoHandSkinningLibrary::FindHandBone(Component, Part.Finger, Part.Segment + 1) : INDEX_NONE;
				if (ChildBone != INDEX_NONE)
				{
					Part.Dir = (BoneOrigin(ChildBone) - Part.Origin).GetSafeNormal(UE_SMALL_NUMBER, FVector3f::XAxisVector);
					Part.End = BoneOrigin(ChildBone);
				}
				else
				{
					// distal phalanx: continue the previous segment's direction to the farthest vertex
					const int32 ParentBone = RefSkel.GetParentIndex(Part.MainBone);
					Part.Dir = (ParentBone != INDEX_NONE) ? (Part.Origin - BoneOrigin(ParentBone)).GetSafeNormal(UE_SMALL_NUMBER, FVector3f::XAxisVector) : FVector3f::XAxisVector;
					float Far = 0.5f;
					for (int32 V : Part.Verts) { Far = FMath::Max(Far, FVector3f::DotProduct(Pos[V] - Part.Origin, Part.Dir)); }
					Part.End = Part.Origin + Part.Dir * Far;
				}
			}
		}
		// The two parts of a joint must be closed by spherical caps of the SAME radius centred at the
		// joint (thesis 4.4), so the closure distance of a joint is the nearest vertex of either part.
		auto NearestDist = [&](const FPart& Part, const FVector3f& Joint)
		{
			float D = FLT_MAX;
			for (int32 V : Part.Verts) { D = FMath::Min(D, (Pos[V] - Joint).Size()); }
			for (int32 C : Part.Children)
			{
				if (Alive[C] && (Parts[C].Origin - Joint).Size() < 0.05f)
				{
					for (int32 V : Parts[C].Verts) { D = FMath::Min(D, (Pos[V] - Joint).Size()); }
				}
			}
			if (Part.Parent != INDEX_NONE && Alive[Part.Parent] && (Part.Origin - Joint).Size() < 0.05f)
			{
				for (int32 V : Parts[Part.Parent].Verts) { D = FMath::Min(D, (Pos[V] - Joint).Size()); }
			}
			return (D == FLT_MAX) ? 0.3f : FMath::Max(D, 0.1f);
		};
		for (int32 P = 0; P < Parts.Num(); ++P)
		{
			FPart& Part = Parts[P];
			if (!Alive[P]) { continue; }
			if (Part.bPalm)
			{
				for (int32 C : Part.Children)
				{
					if (!Alive[C]) { continue; }
					FClosure Cl;
					Cl.Joint = Parts[C].Origin;
					Cl.Outward = Parts[C].Dir;
					Part.Closures.Add(Cl);
				}
			}
			else
			{
				if (Part.Parent != INDEX_NONE && Alive[Part.Parent])
				{
					FClosure Cl;
					Cl.Joint = Part.Origin;
					Cl.Outward = -Part.Dir;
					Part.Closures.Add(Cl);
				}
				for (int32 C : Part.Children)
				{
					if (!Alive[C]) { continue; }
					FClosure Cl;
					Cl.Joint = Part.End;
					Cl.Outward = Part.Dir;
					Part.Closures.Add(Cl);
				}
			}
		}

		// ---- sampling + fit --------------------------------------------------------------
		int32 NumFitted = 0;
		float WorstResidual = 0.0f;
		for (int32 P = 0; P < Parts.Num(); ++P)
		{
			FPart& Part = Parts[P];
			if (!Alive[P]) { continue; }
			const float Len = FMath::Max((Part.End - Part.Origin).Size(), 0.5f);
			const float CullDist = Part.bPalm ? 0.2f : Settings.CullFraction * Len;
			TArray<int32> Candidates;
			Candidates.Reserve(Part.Verts.Num());
			for (int32 V : Part.Verts)
			{
				bool bCulled = false;
				for (const FClosure& Cl : Part.Closures)
				{
					if (FVector3f::DotProduct(Pos[V] - Cl.Joint, Cl.Outward) > -CullDist) { bCulled = true; break; }
				}
				if (!bCulled) { Candidates.Add(V); }
			}
			if (Candidates.Num() < 8) { Candidates = Part.Verts; }
			TArray<int32> Picked;
			FarthestPointSample(Pos, Candidates, Part.bPalm ? Settings.PalmSamples : Settings.SamplesPerBone, Picked);
			TArray<FVector3f> C, Nn;
			for (int32 V : Picked) { C.Add(Pos[V]); Nn.Add(Normal[V]); }
			for (const FClosure& Cl : Part.Closures)
			{
				const float S = NearestDist(Part, Cl.Joint);
				C.Add(Cl.Joint + Cl.Outward * S);
				Nn.Add(Cl.Outward);
			}
			float Scale = 0.0f;
			for (const FVector3f& X : C) { Scale = FMath::Max(Scale, PointSegmentDistance(X, Part.Origin, Part.End)); }
			Part.Scale = FMath::Max(Scale, 0.2f);
			Part.Centers.Reset();
			Part.Normals.Reset();
			for (int32 K = 0; K < C.Num(); ++K)
			{
				Part.Centers.Add((C[K] - Part.Origin) / Part.Scale);
				Part.Normals.Add(Nn[K]);
			}
			if (!FitHRBF(Part))
			{
				UE_LOG(LogPianoHand, Warning, TEXT("[Implicit] %s: HRBF solve failed (%d centres)"), *Part.Name.ToString(), Part.Centers.Num());
				Alive[P] = false;
				continue;
			}
			float Res = 0.0f;
			for (int32 K = 0; K < Part.Centers.Num(); ++K)
			{
				float D; FVector3f G;
				EvalHRBF(Part, Part.Centers[K], D, G);
				Res = FMath::Max(Res, FMath::Max(FMath::Abs(D), (G - Part.Normals[K]).Size()));
			}
			Part.FitResidual = Res;
			WorstResidual = FMath::Max(WorstResidual, Res);
			++NumFitted;
			// diagnostics: coefficient magnitude, float32 evaluation error, and whether the field is monotone
			// across the surface (f larger 1 mm inside than 1 mm outside) - ghost sheets between centres show up here
			{
				float MaxA = 0.0f, MaxB = 0.0f, MaxErr = 0.0f;
				for (int32 K = 0; K < Part.Centers.Num(); ++K) { MaxA = FMath::Max(MaxA, FMath::Abs(Part.Alpha[K])); MaxB = FMath::Max(MaxB, Part.Beta[K].Size()); }
				int32 Bad = 0, Tested = 0;
				for (int32 Vi = 0; Vi < Part.Verts.Num(); Vi += 7)
				{
					const int32 V = Part.Verts[Vi];
					const FVector3f U = (Pos[V] - Part.Origin) / Part.Scale;
					float Dd; FVector3f Gd;
					EvalHRBF(Part, U, Dd, Gd);
					MaxErr = FMath::Max(MaxErr, FMath::Abs(EvalHRBFFloat(Part, U) - Dd));
					const float Fin = FieldOf(Part, Pos[V] - Normal[V] * 0.1f);
					const float Fout = FieldOf(Part, Pos[V] + Normal[V] * 0.1f);
					const float F0 = RemapTr(Dd);
					if (!(Fin > F0 && F0 > Fout)) { ++Bad; }
					++Tested;
				}
				UE_LOG(LogPianoHand, Display, TEXT("[Implicit]   %s: max|a|=%.3g max|b|=%.3g float-err=%.2e non-monotone %d / %d"),
					*Part.Name.ToString(), MaxA, MaxB, MaxErr, Bad, Tested);
			}
		}

		// ---- pack primitives -------------------------------------------------------------
		TArray<int32> PartToPrim;
		PartToPrim.Init(INDEX_NONE, Parts.Num());
		for (int32 P = 0; P < Parts.Num(); ++P)
		{
			if (!Alive[P]) { continue; }
			const FPart& Part = Parts[P];
			PartToPrim[P] = Out.PrimInfo.Num();
			FUintVector4 Meta((uint32)(Out.Samples.Num() / 2), (uint32)Part.Centers.Num(), 0u, 0u);
			for (int32 K = 0; K < Part.Centers.Num(); ++K)
			{
				Out.Samples.Add(FVector4f(Part.Centers[K], Part.Alpha[K]));
				Out.Samples.Add(FVector4f(Part.Beta[K], 0.0f));
			}
			Out.PrimInfo.Add(FVector4f(Part.Origin, Part.Scale));
			Out.PrimAxis.Add(FVector4f(Part.Dir, (Part.End - Part.Origin).Size()));
			Out.PrimMeta.Add(Meta);
			Out.PrimBone.Add(Part.MainBone);
			Out.PrimName.Add(Part.Name);
		}
		auto JointOp = [&](const FPart& A, const FPart& B) -> int32
		{
			// bulge-in-contact on the hinge joints (MCP, PIP, DIP, thumb MP / IP); plain union at the
			// carpus (palm - metacarpal, palm - thumb metacarpal) and at a grouped palm's MCPs
			if (A.bPalm || B.bPalm)
			{
				const FPart& Fing = A.bPalm ? B : A;
				return (Fing.Segment == 0 && Fing.Finger != 0 && Settings.bPalmGroup) ? 1 : 0;
			}
			return 1;
		};
		for (int32 P = 0; P < Parts.Num(); ++P)
		{
			if (!Alive[P]) { continue; }
			const int32 Prim = PartToPrim[P];
			Out.PrimMeta[Prim].W = (uint32)Out.PrimNeighbours.Num();
			const FPart& Part = Parts[P];
			// op: 0 = union, 1 = bulge-in-contact with my parent, 2 = bulge-in-contact with my child
			if (Part.Parent != INDEX_NONE && Alive[Part.Parent])
			{
				Out.PrimNeighbours.Add(FIntPoint(PartToPrim[Part.Parent], JointOp(Part, Parts[Part.Parent]) ? 1 : 0));
			}
			for (int32 C : Part.Children)
			{
				if (Alive[C]) { Out.PrimNeighbours.Add(FIntPoint(PartToPrim[C], JointOp(Part, Parts[C]) ? 2 : 0)); }
			}
			Out.PrimMeta[Prim].Z = (uint32)Out.PrimNeighbours.Num() - Out.PrimMeta[Prim].W;
		}
		if (Out.PrimNeighbours.Num() == 0) { Out.PrimNeighbours.Add(FIntPoint(-1, 0)); }
		// rest relative rotation of every pair, for the per-frame bend angle
		Out.PairRestRelative.SetNum(Out.PrimNeighbours.Num());
		for (int32 Prim = 0; Prim < Out.PrimMeta.Num(); ++Prim)
		{
			const FUintVector4& Meta = Out.PrimMeta[Prim];
			const int32 BoneA = Out.PrimBone[Prim];
			for (uint32 N = 0; N < Meta.Z; ++N)
			{
				const int32 Entry = (int32)(Meta.W + N);
				const int32 PrimB = Out.PrimNeighbours[Entry].X;
				FQuat4f Rel = FQuat4f::Identity;
				if (PrimB >= 0)
				{
					const int32 BoneB = Out.PrimBone[PrimB];
					Rel = FQuat4f(CS[BoneA].GetRotation()).Inverse() * FQuat4f(CS[BoneB].GetRotation());
				}
				Out.PairRestRelative[Entry] = Rel;
			}
		}

		// ---- per-vertex primitive, rest iso-value and rest overlaps ------------------------------
		// iso_v is the vertex's OWN part field at rest. Every other part only ever acts as an obstacle,
		// relative to rest: the GPU composes  max( f_P(x),  f_o(x) - c_o + iso_v )  with c_o = max(f_o(v), 0.5),
		// so a neighbouring field that bulged over the vertex at rest (the metacarpal head over the base of
		// the finger, the thumb over the web) neither moves it at rest nor drags it along when the joint
		// opens, and only pushes it when that part comes CLOSER than at rest / inside its surface.
		Out.VertexPrim.Init(-1, NumVerts);
		Out.VertexIso.Init(0.5f, NumVerts);
		Out.VertexOverlap.Init(FVector4f(-1.0f, 0.5f, -1.0f, 0.5f), NumVerts * 2);
		Out.VertexOwn.Init(FVector4f(-1.0f, 0.5f, -1.0f, 0.5f), NumVerts);
		Out.VertexBlend.Init(0.0f, NumVerts);
		int32 NumOwn2 = 0;
		float IsoMin = 1.0f, IsoMax = 0.0f;
		int32 NumSkinned = 0, NumOverlaps = 0, NumLowIso = 0;
		for (int32 V = 0; V < NumVerts; ++V)
		{
			int32 B = Dominant[V];
			if (B == INDEX_NONE) { continue; }
			int32 P = BoneToPart[B];
			if (P == INDEX_NONE || !Alive[P]) { continue; }
			// the palm and the metacarpals keep their geometric skinning: they are soft, not tubes
			if (!Settings.bProjectPalm && (Parts[P].bPalm || Parts[P].Segment == 3))
			{
				// 10-18: deciding "projected or not" by the DOMINANT bone leaves a ragged boundary at every MCP where the
				// metacarpal and the proximal phalanx trade dominance (sawtooth in debug mode 2) and the blend is already
				// ~0.15 there - a visible cliff / slit along the knuckle while the finger bends. A vertex whose phalanx
				// weight is inside the blend ramp is projected onto its strongest phalanx instead, so the correction
				// fades to exactly 0 where the projection stops.
				if (FingerWeight[V] <= Settings.BlendFadeStart || BestPhalanx[V] == INDEX_NONE) { continue; }
				B = BestPhalanx[V];
				P = BoneToPart[B];
				if (P == INDEX_NONE || !Alive[P] || Parts[P].bPalm || Parts[P].Segment == 3) { continue; }
			}
			const FPart& Part = Parts[P];
			Out.VertexBlend[V] = FMath::SmoothStep(Settings.BlendFadeStart, Settings.BlendFadeFull, FingerWeight[V]);
			const float F = FieldOf(Part, Pos[V]);
			TArray<TPair<float, int32>, TInlineAllocator<8>> Over;
			for (int32 O = 0; O < Parts.Num(); ++O)
			{
				if (O == P || !Alive[O] || !InSupport(Parts[O], Pos[V])) { continue; }
				const float Fo = FieldOf(Parts[O], Pos[V]);
				if (Fo > 0.5f) { Over.Add(TPair<float, int32>(Fo, PartToPrim[O])); }
			}
			Over.Sort([](const TPair<float, int32>& A, const TPair<float, int32>& Bb) { return A.Key > Bb.Key; });
			for (int32 K = 0; K < FMath::Min(Over.Num(), 4); ++K)
			{
				FVector4f& Slot = Out.VertexOverlap[V * 2 + K / 2];
				if (K % 2 == 0) { Slot.X = (float)Over[K].Value; Slot.Y = Over[K].Key; }
				else            { Slot.Z = (float)Over[K].Value; Slot.W = Over[K].Key; }
			}
			NumOverlaps += (Over.Num() > 0) ? 1 : 0;
			Out.VertexPrim[V] = PartToPrim[P];
			Out.VertexIso[V] = F;
			// 10-16: the other phalanges this vertex is weighted to are part of its OWN surface - the GPU takes the
			// union max(f_own - iso, f_o - c_o) with the EXACT rest value c_o = f_o(v_rest), so two neighbouring
			// vertices on either side of a weight boundary see the same composed field and the skin stays continuous
			{
				FVector4f Own(-1.0f, 0.5f, -1.0f, 0.5f);
				int32 Slot = 0;
				for (int32 K = 0; K < 2 && Slot < 2; ++K)
				{
					const int32 OB = (K == 0) ? OtherBone[V].X : OtherBone[V].Y;
					const float OW = (K == 0) ? OtherW[V].X : OtherW[V].Y;
					if (OB == INDEX_NONE || OW < Settings.OwnWeightMin) { continue; }
					const int32 OP = BoneToPart[OB];
					if (OP == INDEX_NONE || OP == P || !Alive[OP]) { continue; }
					if (!Settings.bProjectPalm && (Parts[OP].bPalm || Parts[OP].Segment == 3)) { continue; }
					const float Fo = FieldOf(Parts[OP], Pos[V]);
					if (Slot == 0) { Own.X = (float)PartToPrim[OP]; Own.Y = Fo; }
					else           { Own.Z = (float)PartToPrim[OP]; Own.W = Fo; }
					++Slot;
				}
				Out.VertexOwn[V] = Own;
				NumOwn2 += (Slot > 0) ? 1 : 0;
			}
			// a vertex embedded far from its part's 0.5 surface (the web between two fingers, skin hanging
			// off the tube) is tracking a shell of the field that is a poor proxy for it: fade it out
			Out.VertexBlend[V] *= 1.0f - FMath::SmoothStep(Settings.IsoFadeStart, Settings.IsoFadeFull, FMath::Abs(F - 0.5f));
			IsoMin = FMath::Min(IsoMin, F);
			IsoMax = FMath::Max(IsoMax, F);
			if (F < 0.3f) { ++NumLowIso; }
			++NumSkinned;
		}

		// ---- adjacency + mean value coordinates -----------------------------------------
		{
			TArray<TArray<FIntPoint>> RingEdges;   // per vertex: directed ring edges (a -> b) from its incident triangles
			RingEdges.SetNum(NumVerts);
			for (int32 T = 0; T < NumTris; ++T)
			{
				if ((int32)Indices[T * 3] >= NumVerts || (int32)Indices[T * 3 + 1] >= NumVerts || (int32)Indices[T * 3 + 2] >= NumVerts) { continue; }
				const int32 I0 = (int32)Canon[Indices[T * 3]], I1 = (int32)Canon[Indices[T * 3 + 1]], I2 = (int32)Canon[Indices[T * 3 + 2]];
				RingEdges[I0].Add(FIntPoint(I1, I2));
				RingEdges[I1].Add(FIntPoint(I2, I0));
				RingEdges[I2].Add(FIntPoint(I0, I1));
			}
			Out.AdjOffsets.SetNum(NumVerts + 1);
			Out.AdjIndices.Reset();
			Out.AdjWeights.Reset();
			int32 NumClosed = 0;
			TArray<int32> Ring;
			for (int32 V = 0; V < NumVerts; ++V)
			{
				Out.AdjOffsets[V] = (uint32)Out.AdjIndices.Num();
				const TArray<FIntPoint>& E = RingEdges[Canon[V]];   // a seam twin uses the welded ring (neighbours are canonical ids)
				if (E.Num() == 0) { continue; }
				// try to chain the edges into one closed loop
				Ring.Reset();
				bool bClosed = false;
				{
					TMap<int32, int32> Next;
					bool bUnique = true;
					for (const FIntPoint& Ed : E)
					{
						if (Next.Contains(Ed.X)) { bUnique = false; break; }
						Next.Add(Ed.X, Ed.Y);
					}
					if (bUnique)
					{
						int32 Cur = E[0].X;
						for (int32 Guard = 0; Guard < E.Num(); ++Guard)
						{
							Ring.Add(Cur);
							const int32* N = Next.Find(Cur);
							if (N == nullptr) { break; }
							Cur = *N;
							if (Cur == E[0].X) { bClosed = (Ring.Num() == E.Num()); break; }
						}
					}
				}
				if (!bClosed)
				{
					// open ring (boundary, seam): unique neighbours, uniform weights
					Ring.Reset();
					for (const FIntPoint& Ed : E) { Ring.AddUnique(Ed.X); Ring.AddUnique(Ed.Y); }
					const float W = 1.0f / (float)Ring.Num();
					for (int32 R : Ring) { Out.AdjIndices.Add((uint32)R); Out.AdjWeights.Add(W); }
					continue;
				}
				++NumClosed;
				// mean value coordinates in the tangent plane
				const FVector3f N = Normal[V];
				FVector3f Tn, Bn;
				N.FindBestAxisVectors(Tn, Bn);
				const int32 K = Ring.Num();
				TArray<FVector2f> Q;
				Q.SetNum(K);
				for (int32 J = 0; J < K; ++J)
				{
					const FVector3f D = Pos[Ring[J]] - Pos[V];
					Q[J] = FVector2f(FVector3f::DotProduct(D, Tn), FVector3f::DotProduct(D, Bn));
				}
				TArray<float> Ang;
				Ang.SetNum(K);
				bool bOk = true;
				for (int32 J = 0; J < K; ++J)
				{
					const FVector2f& A = Q[J];
					const FVector2f& Bq = Q[(J + 1) % K];
					const float Cr = A.X * Bq.Y - A.Y * Bq.X;
					const float Dt = A.X * Bq.X + A.Y * Bq.Y;
					Ang[J] = FMath::Atan2(Cr, Dt);
					if (!FMath::IsFinite(Ang[J]) || FMath::Abs(Ang[J]) > 2.6f) { bOk = false; }
				}
				// all angles must turn the same way for the fan to be star-shaped around V
				if (bOk)
				{
					float Sum = 0.0f;
					for (float A : Ang) { Sum += A; }
					if (FMath::Abs(FMath::Abs(Sum) - 2.0f * PI) > 0.5f) { bOk = false; }
					const float Sign = (Sum < 0.0f) ? -1.0f : 1.0f;
					for (float& A : Ang) { A *= Sign; if (A <= 0.0f) { bOk = false; } }
				}
				TArray<float> W;
				W.SetNum(K);
				float WSum = 0.0f;
				if (bOk)
				{
					for (int32 J = 0; J < K; ++J)
					{
						const float Prev = Ang[(J + K - 1) % K];
						const float L = Q[J].Size();
						W[J] = (L > 1e-6f) ? (FMath::Tan(Prev * 0.5f) + FMath::Tan(Ang[J] * 0.5f)) / L : 0.0f;
						if (!FMath::IsFinite(W[J]) || W[J] < 0.0f) { bOk = false; break; }
						WSum += W[J];
					}
				}
				if (!bOk || WSum <= 1e-8f)
				{
					for (int32 J = 0; J < K; ++J) { W[J] = 1.0f / (float)K; }
					WSum = 1.0f;
				}
				for (int32 J = 0; J < K; ++J)
				{
					Out.AdjIndices.Add((uint32)Ring[J]);
					Out.AdjWeights.Add(W[J] / WSum);
				}
			}
			Out.AdjOffsets[NumVerts] = (uint32)Out.AdjIndices.Num();
			Out.Summary = FString::Printf(TEXT("%d prims (%d centres), %d / %d vertices skinned (%d share a 2nd phalanx), iso %.3f..%.3f (%d below 0.3), %d with rest overlaps, fit residual %.2e, %d closed rings, %d seam twins welded"),
				Out.PrimInfo.Num(), Out.Samples.Num() / 2, NumSkinned, NumVerts, NumOwn2, IsoMin, IsoMax, NumLowIso, NumOverlaps, WorstResidual, NumClosed, NumTwins);
		}
		for (int32 P = 0; P < Parts.Num(); ++P)
		{
			if (!Alive[P]) { continue; }
			const FPart& Part = Parts[P];
			UE_LOG(LogPianoHand, Display, TEXT("[Implicit] %-24s verts=%6d centres=%3d closures=%d scale=%.2fcm residual=%.1e"),
				*Part.Name.ToString(), Part.Verts.Num(), Part.Centers.Num(), Part.Closures.Num(), Part.Scale, Part.FitResidual);
		}
		if (Out.AdjIndices.Num() == 0) { Out.AdjIndices.Add(0u); Out.AdjWeights.Add(0.0f); }
		Out.NumVertices = (uint32)NumVerts;
		Out.bValid = NumFitted > 0 && NumSkinned > 0;
	}
}
