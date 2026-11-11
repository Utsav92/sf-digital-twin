# make all | make pilot | make tiles TILES=t+00_+00 | make unreal [PILOT=1] | make stats
all:    ; ./run_all.sh
pilot:  ; ./run_all.sh --pilot
tiles:  ; ./run_all.sh --tiles $(TILES)
stats:  ; .venv/bin/python src/checks/stats.py
UE ?= $(HOME)/unreal/UE_5.8
unreal:
	@test -x "$(UE)/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor" || { echo "UE not found at $(UE) (override: make unreal UE=...)"; exit 1; }
	"$(UE)/Engine/Build/BatchFiles/Mac/Build.sh" SF_DigitalTwinEditor Mac Development -project="$(CURDIR)/SF_DigitalTwin/SF_DigitalTwin.uproject" -waitmutex
	@echo "Import/map: see SF_DigitalTwin/Documentation/STATUS.md"
.PHONY: all pilot tiles stats unreal
