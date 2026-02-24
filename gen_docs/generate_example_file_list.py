import mkdocs_gen_files
from pathlib import Path

input_dir = Path("docs/usage/example_input_files")
files = sorted(input_dir.glob("*json"))
with mkdocs_gen_files.open("generated.md", "w") as f:
    for file_path in files:
        rel_path = file_path.relative_to(file_path.parts[0])
        name = " ".join([part[0].upper() + part[1:] for part in rel_path.stem.split("_")])
        print(f"[{name}]({rel_path})\n", file=f)