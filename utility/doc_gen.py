"""
This script uses the aider CLI to add comprehensive Google-style docstrings to all Python files in the specified directory.
Not needed to run Talos-SDL.
"""
import os
import subprocess
from pathlib import Path

# Configuration
TARGET_DIR = "communicate"
MODEL = "ollama/qwen2.5-coder:14b"
PROMPT = (
    "Add comprehensive Google-style docstrings to all functions and classes. "
    "Include Args (with types), Returns (with types), and Raises. "
    "Ensure compatibility with mkdocstrings for API documentation. "
    "Do not change any functional code."
)

def process_files():
    # Convert to Path object for Windows compatibility
    base_path = Path(TARGET_DIR)
    
    if not base_path.exists():
        print(f"Error: Directory '{TARGET_DIR}' not found.")
        return

    # Find all .py files recursively
    py_files = list(base_path.rglob("*.py"))
    
    for file_path in py_files:
        print(f"\n--- Processing: {file_path} ---")
        
        # Construct the aider command
        # --message sends the instruction and exits after applying changes
        cmd = [
            "aider",
            "--model", MODEL,
            "--message", PROMPT,
            str(file_path)
        ]
        
        try:
            # Run the command and wait for it to finish
            subprocess.run(cmd, check=True)
            print(f"Successfully processed {file_path}")
        except subprocess.CalledProcessError as e:
            print(f"Error processing {file_path}: {e}")
        except FileNotFoundError:
            print("Error: 'aider' command not found. Ensure it is in your PATH.")
            break

if __name__ == "__main__":
    process_files()