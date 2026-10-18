// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleInterface.h"

PIANOHAND_SIMULATOR_API DECLARE_LOG_CATEGORY_EXTERN(LogPianoHand, Log, All);

/**
 * Primary game module.
 * Registers the project shader directory ("/PianoHand" -> <Project>/Shaders) before the
 * global shader map is compiled. This requires LoadingPhase = PostConfigInit in the .uproject.
 */
class FPianoHandSimulatorModule : public IModuleInterface
{
public:
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;
};
