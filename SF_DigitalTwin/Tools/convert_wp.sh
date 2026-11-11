#!/bin/bash
# Convert /Game/Maps/SF_City to World Partition (writes SF_City_WP); 500 m tiles sit in 512 m cells.
P=$HOME/sf_twin/SF_DigitalTwin
$HOME/unreal/UE_5.8/Engine/Binaries/Mac/UnrealEditor-Cmd $P/SF_DigitalTwin.uproject /Game/Maps/SF_City -run=WorldPartitionConvertCommandlet -AllowCommandletRendering -ConversionSuffix=_WP -Verbose -unattended -nosplash
