// FPianoNoteRow.h
//
// ============================================================================
//  [참조용 스니펫 — 빌드 대상 아님]
//
//  이 파일은 `tools/export_datatable.py`가 생성한 CSV를 UE5 DataTable로
//  임포트할 때 필요한 USTRUCT 정의를 그대로 옮겨 적은 **참조용 코드**다.
//  01_Fingering 파트의 Python 도구 폴더에 있을 뿐이며 어떤 모듈에도
//  컴파일되지 않는다.
//
//  사용법: 아래 내용을 UE5 프로젝트의 게임 모듈
//          (예: Source/PianoHandSimulator/Public/PianoNoteRow.h)
//          로 복사한 뒤, #include 경로의 모듈명만 프로젝트에 맞게 수정한다.
//          복사 후 반드시 에디터/프로젝트를 리빌드해야 임포트 창의
//          구조체 목록에 `PianoNoteRow`가 나타난다.
// ============================================================================
//
//  CSV ↔ 멤버 대응 규칙
//    · CSV 첫 열 `Name`      : UE5가 RowName으로 소비하며 구조체 멤버가 아니다.
//    · CSV 2번째 열 이후 헤더: 아래 UPROPERTY 이름과 1:1로 일치해야 한다.
//    · CSV 열 순서는 임포트에 영향을 주지 않는다(이름으로 매칭).
//    · KeyHoldMs / PedalDown 열은 손가락 점유와 소리 지속을 분리한 값이다.
//      건반 해제 타이밍은 KeyHoldMs 기준 (DurationMs 아님).
//    · TargetXMm / TargetYMm / TargetZMm 열은 운지법 엔진이 좌표를 산출했을
//      때만 CSV에 존재한다. 열이 없으면 해당 멤버는 기본값 0으로 남는다.
//
//  단위 주의 (★ 중요)
//    Target*Mm 은 **밀리미터(mm)** 다. UE5의 기본 월드 단위는 **센티미터(cm)**
//    이므로 그대로 FVector에 넣으면 10배 크기가 된다.
//    반드시 GetTargetLocationCm() 처럼 0.1을 곱해 사용할 것.
// ============================================================================

#pragma once

#include "CoreMinimal.h"
#include "Engine/DataTable.h"
#include "PianoNoteRow.generated.h"

/** mm → cm 변환 계수. 엔진(운지법) 출력은 mm, UE5 월드 단위는 cm. */
#define PIANO_MM_TO_CM 0.1f

/**
 * 운지법 엔진 NoteEvent 1개(= CSV 1행)에 대응하는 DataTable 행 구조체.
 * 설계 명세서 `01_Design/03_Interface_Design_Spec.md` 2.2절 스키마 기반.
 */
USTRUCT(BlueprintType)
struct FPianoNoteRow : public FTableRowBase
{
	GENERATED_BODY()

	// ---- 운지법 엔진 원본 필드 (Interface A) -------------------------------

	/** MIDI 음고 (21~108, A0~C8) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Note")
	int32 Pitch = 0;

	/** 음표 시작 시각 (ms, 곡 시작 기준 절대 시각) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Timing")
	float StartMs = 0.f;

	/**
	 * 소리가 울리는 시간 (ms). Sustain 페달로 늘어난 '청각적' 지속이다.
	 * ★ 건반 해제 타이밍으로 쓰지 말 것 — KeyHoldMs 를 사용한다.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Timing")
	float DurationMs = 0.f;

	/**
	 * 손가락이 실제로 건반을 누르고 있는 시간 (ms).
	 * 페달이 눌린 구간에서는 DurationMs 보다 짧다 (건반을 떼도 소리는 유지되므로).
	 * ★ IK의 누름/해제는 반드시 이 값을 기준으로 한다. DurationMs 를 쓰면
	 *   한 손가락이 서로 다른 건반을 동시에 누르는 자세가 만들어진다.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Timing")
	float KeyHoldMs = 0.f;

	/** 타건 시점의 Sustain 페달 상태. true면 손가락을 떼도 소리가 유지된다. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Timing")
	bool PedalDown = false;

	/** "Left" | "Right" — 왼손/오른손 Skeletal Mesh 선택용 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hand")
	FString Hand;

	/** "MELODY" | "BASS" | "INNER" — 화음 충돌 시 우선순위(MELODY > BASS > INNER) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Note")
	FString Role;

	/** 배정 손가락 번호 (1=엄지 ~ 5=새끼) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hand")
	int32 Finger = 0;

	/** 타건 강도 (0.0~1.0). 손가락 가속도 곡선 조절용 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Note")
	float Pressure = 0.f;

	/** 건반 누름 깊이 (0.0~1.0). Z 오프셋 = KeyDepth * MAX_KEY_TRAVEL(10 mm) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Note")
	float KeyDepth = 0.f;

	/** 흑건 여부. CSV에는 True / False 로 기록된다. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Note")
	bool IsBlack = false;

	/** 손목 가로 위치 (0.0~1.0, 88키 전체 폭 기준 정규화) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wrist")
	float WristPosNormalized = 0.f;

	/** 손목 좌우 회전각 (도, ±35.0 범위) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wrist")
	float WristYawDeg = 0.f;

	/** 손목 기울기 (도, ±20.0 범위) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Wrist")
	float WristRollDeg = 0.f;

	// ---- 건반 3D 목표 좌표 (CSV에 열이 있을 때만 채워짐) --------------------
	// ★ 단위는 mm. UE5는 cm 이므로 GetTargetLocationCm() 사용 권장.

	/** 건반 목표 X (mm). 원점 = 88키 최좌단 A0(MIDI 21)의 좌측 모서리 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Target|mm")
	float TargetXMm = 0.f;

	/** 건반 목표 Y (mm). 백건 타건 접점 30.0 / 흑건 85.0 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Target|mm")
	float TargetYMm = 0.f;

	/** 건반 목표 Z (mm). (흑건 ? 12.5 : 0.0) - KeyDepth * 10.0 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Target|mm")
	float TargetZMm = 0.f;

	// ---- 변환 도구가 계산한 파생 필드 --------------------------------------

	/** IK End Effector 본 이름 (예: thumb_03_r). 명세서 2.6절 매핑 결과 */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hand")
	FName BoneName;

	/** 타건 프레임 번호 (StartMs를 변환 시 지정한 FPS로 환산, 반올림) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Timing")
	int32 FrameIndex = 0;

	/** 건반 해제 프레임 번호. 항상 FrameIndex보다 최소 1 크다. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Timing")
	int32 ReleaseFrameIndex = 0;

	// ---- 헬퍼 --------------------------------------------------------------

	/** 건반 목표 좌표를 UE5 단위(cm)로 변환해 반환. */
	FVector GetTargetLocationCm() const
	{
		return FVector(TargetXMm, TargetYMm, TargetZMm) * PIANO_MM_TO_CM;
	}

	/** 소리가 끝나는 시각 (ms). 오디오·리버브 동기용. 건반 해제는 GetReleaseMs(). */
	float GetSoundEndMs() const
	{
		return StartMs + DurationMs;
	}

	/** 건반 해제 시각 (ms). */
	float GetReleaseMs() const
	{
		// 손가락이 건반에서 떨어지는 시각 (소리 종료가 아님 → GetSoundEndMs)
		return StartMs + KeyHoldMs;
	}

	/** 유지 프레임 수 (타건 ~ 해제). */
	int32 GetHoldFrameCount() const
	{
		return ReleaseFrameIndex - FrameIndex;
	}
};

// ============================================================================
//  [선택] Hand / Role 을 enum으로 받고 싶은 경우
//
//  UE5의 CSV 임포터는 enum 열거자 이름 문자열을 그대로 해석하므로,
//  열거자 이름을 CSV 값과 똑같이("Left"/"Right", "MELODY"/"BASS"/"INNER")
//  맞추면 FString 대신 enum으로 임포트할 수 있다.
//  단, 이름이 하나라도 어긋나면 임포트 시 행 전체가 경고와 함께 스킵되므로
//  통합 초기에는 위의 FString 버전을 쓰는 것을 권장한다.
//
//  UENUM(BlueprintType)
//  enum class EPianoHand : uint8
//  {
//      Left,
//      Right
//  };
//
//  UENUM(BlueprintType)
//  enum class EPianoRole : uint8
//  {
//      MELODY,
//      BASS,
//      INNER
//  };
// ============================================================================
