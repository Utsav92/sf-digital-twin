import os, runpy
for s in os.environ.get("SF_BATCH", "").split(","):
    if s: print("SFBATCH running", s); runpy.run_path(os.path.join(os.path.dirname(__file__), s), run_name="__main__")
print("SFBATCH_DONE")
