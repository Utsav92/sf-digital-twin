# make all | make pilot | make tiles TILES=t+00_+00 | make unreal [PILOT=1] | make stats
all:    ; ./run_all.sh
pilot:  ; ./run_all.sh --pilot
tiles:  ; ./run_all.sh --tiles $(TILES)
stats:  ; .venv/bin/python src/checks/stats.py
unreal:
	@UE=$$(ls -d "/Users/Shared/Epic Games"/UE_5.*/Engine/Binaries/Mac/UnrealEditor.app 2>/dev/null | tail -1); \
	if [ -z "$$UE" ]; then echo "Unreal Engine 5 not installed (expected /Users/Shared/Epic Games/UE_5.x). See README > Unreal."; exit 1; fi; \
	echo "Unreal phases 12-16 are not implemented yet (found $$UE)"; exit 1
.PHONY: all pilot tiles stats unreal
