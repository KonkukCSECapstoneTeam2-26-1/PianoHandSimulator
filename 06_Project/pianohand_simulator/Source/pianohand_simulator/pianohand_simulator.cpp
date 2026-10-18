// Copyright Epic Games, Inc. All Rights Reserved.

#include "pianohand_simulator.h"
#include "Modules/ModuleManager.h"
#include "Interfaces/IPluginManager.h"
#include "Misc/Paths.h"
#include "ShaderCore.h"

DEFINE_LOG_CATEGORY(LogPianoHand);

void FPianoHandSimulatorModule::StartupModule()
{
	// Map the virtual shader path "/PianoHand" to <ProjectDir>/Shaders so .usf/.ush files
	// can be referenced from IMPLEMENT_GLOBAL_SHADER and #include directives.
	const FString ShaderDir = FPaths::Combine(FPaths::ProjectDir(), TEXT("Shaders"));
	if (!AllShaderSourceDirectoryMappings().Contains(TEXT("/PianoHand")))
	{
		AddShaderSourceDirectoryMapping(TEXT("/PianoHand"), ShaderDir);
		UE_LOG(LogPianoHand, Log, TEXT("Registered shader directory mapping /PianoHand -> %s"), *ShaderDir);
	}
}

void FPianoHandSimulatorModule::ShutdownModule()
{
}

IMPLEMENT_PRIMARY_GAME_MODULE(FPianoHandSimulatorModule, pianohand_simulator, "pianohand_simulator");
