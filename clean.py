import os
import shutil

base_dir = r"C:\Users\SUMITH R\Desktop\SeedIQ1\SeedIQ"
dirs_to_delete = [
    os.path.join(base_dir, "templates"),
    os.path.join(base_dir, "static", "css")
]

for d in dirs_to_delete:
    if os.path.exists(d):
        print(f"Deleting {d}")
        shutil.rmtree(d)
        print(f"Deleted {d}")
    else:
        print(f"Directory {d} does not exist")
