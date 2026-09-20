// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class pianohand_simulator : ModuleRules
{
	public pianohand_simulator(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"EnhancedInput"
		});

		// Custom GPU skinning pipeline (global compute shaders, RDG, readback)
		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"RenderCore",
			"RHI",
			"Renderer",
			"Projects"
		});
	}
}
