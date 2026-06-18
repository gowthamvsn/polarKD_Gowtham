# Project Setup Notes
## Git, Linux Server Deployment & Troubleshooting Log

---

## 1. Git Basics

### Check which repo you're connected to
```bash
git remote -v
git status
```

### Commit and push everything
```bash
git add .
git commit -m "your message"
git push origin feature/my-changes
```

### If push is rejected
```bash
git pull origin feature/my-changes
git push origin feature/my-changes
```

### Merge feature branch into main
```bash
git checkout main
git merge feature/my-changes
git push origin main
```

### Force push (only when working alone and sure)
```bash
git push --force origin feature/my-changes
```

---

## 2. GitHub Repo — Viewing Files on a Specific Branch

GitHub shows `main` by default. To see files on `feature/my-changes`:
- Go to the repo on GitHub
- Click the branch dropdown (top left, says "main")
- Select `feature/my-changes`

---

## 3. README Management

### Rename README.md to a different name
```bash
git mv README.md readforchanges.md
git add .
git commit -m "rename README to readforchanges.md"
git push origin feature/my-changes
```

### Restore a previous README from git history
```bash
# Find the commit that had the README
git log --oneline --all -- README.md

# Preview the README from a specific commit
git show <commit-hash>:README.md

# Restore it
git checkout <commit-hash> -- README.md
git add README.md
git commit -m "restore original README.md"
git push origin main
```

> In this project, `503ebbd` was the commit with the original comprehensive README.

---

## 4. Linux Server — Getting the Code Running

### SSH into the server
```bash
ssh gv0313@your-server-ip
```
> Must be connected to the UNT VPN first.

### Clone the repo (first time)
```bash
cd /mnt/storage/midas
git clone https://github.com/gowthamvsn/polarKD_Gowtham.git
cd polarKD_Gowtham
```

### Pull latest changes (already cloned)
```bash
cd /mnt/storage/midas/polarKD_Gowtham
git pull origin main
```

---

## 5. Conda/Mamba Environment

### The environment
- Name: `carelens`
- Originally at: `~/.conda/envs/carelens` (home filesystem — ran out of space)
- Miniforge base: `/mnt/storage/midas/applications/miniforge3`

### List environments
```bash
mamba env list
```

### Activate
```bash
mamba activate carelens
```

### `.zshrc` auto-activation line
```bash
mamba activate carelens
```
Located at end of `~/.zshrc`.

---

## 6. Disk Space Crisis & Fix

### The problem
The root filesystem (`/`) was 100% full. Home directory (`~`) was on root.

```
/dev/mapper/ubuntu--vg-ubuntu--lv  1.4T  1.3T  0  100% /
```

### What was using space in home (~19GB total)
```
7.8G    ~/.cache
6.1G    ~/.conda      ← conda environments
4.7G    ~/.local
```

### Fix: Move large folders to storage, create symlinks
```bash
mv ~/.cache /mnt/storage/midas/cache
ln -s /mnt/storage/midas/cache ~/.cache

mv ~/.conda /mnt/storage/midas/conda
ln -s /mnt/storage/midas/conda ~/.conda

mv ~/.local /mnt/storage/midas/local
ln -s /mnt/storage/midas/local ~/.local
```

This freed ~19GB on the root filesystem. The symlinks make everything work as if the folders are still in home.

---

## 7. Installing Python Packages

### The requirements.txt problem
The `requirements.txt` was generated on Windows — it was:
- UTF-16 encoded (spaces between every character)
- 480+ packages including Windows-only ones (`pywin32`, `pywinpty`, CUDA wheels)
- **Do not use this file on Linux**

### What the app actually needs (from checking imports)
```bash
grep -r "^import \|^from " Knowledge_graph/Code/frontend_light_v2.py
```

Only external packages needed:
- `streamlit`
- `pandas`
- `requests`
- `neo4j`
- `keybert`
- `sentence-transformers`
- `transformers`

### Full working install sequence (confirmed working as of 2026-06-17)

```bash
# Individual packages
pip install yake keybert nltk spacy scikit-learn

# Main packages — use storage tmp/cache to avoid filling root disk
TMPDIR=/mnt/storage/midas/pip_tmp pip install \
  --cache-dir /mnt/storage/midas/pip_cache \
  streamlit pandas requests neo4j keybert fuzzywuzzy torchvision ollama \
  pdfplumber pyvis dotenv fitz frontend tiktoken rank_bm25

# CPU-only torch (avoids NCCL/CUDA version mismatch errors)
TMPDIR=/mnt/storage/midas/pip_tmp pip install \
  --cache-dir /mnt/storage/midas/pip_cache \
  torch --index-url https://download.pytorch.org/whl/cpu --force-reinstall

# transformers + sentence-transformers
TMPDIR=/mnt/storage/midas/pip_tmp pip install \
  --cache-dir /mnt/storage/midas/pip_cache \
  transformers sentence-transformers --upgrade

# CPU-only torchvision
TMPDIR=/mnt/storage/midas/pip_tmp pip install \
  --cache-dir /mnt/storage/midas/pip_cache \
  torchvision --index-url https://download.pytorch.org/whl/cpu --force-reinstall

# PyMuPDF (provides the correct `fitz` module)
TMPDIR=/mnt/storage/midas/pip_tmp pip install \
  --cache-dir /mnt/storage/midas/pip_cache \
  PyMuPDF

# spaCy language model
python -m spacy download en_core_web_sm
```

### fitz conflict fix
If `fitz` is broken (wrong package installed alongside PyMuPDF):
```bash
# Check what's in fitz
cat ~/.conda/envs/carelens/lib/python3.12/site-packages/fitz/__init__.py | head -5

# Remove bad fitz, reinstall PyMuPDF to restore correct one
rm -rf ~/.conda/envs/carelens/lib/python3.12/site-packages/fitz
TMPDIR=/mnt/storage/midas/pip_tmp pip install \
  --cache-dir /mnt/storage/midas/pip_cache \
  PyMuPDF --force-reinstall
```

### Create a new conda env on storage (not home, to avoid disk full)
```bash
mamba create --prefix /mnt/storage/midas/gv0313/envs/carelens python=3.12 -y
```

### Packages that caused issues and how they were fixed

| Package | Problem | Fix |
|---|---|---|
| `TA-Lib` | Windows wheel, not supported on Linux | Removed — not used by app |
| `beepy==1.0.7` | Version doesn't exist | Removed — not used by app |
| `torch` (CUDA) | `ncclCommResume` symbol error — NCCL version mismatch | Reinstall CPU-only torch |
| `fitz` | Wrong package (`fitz` standalone) conflicts with `PyMuPDF` | Remove fitz dir, reinstall PyMuPDF |

---

## 8. Running the App on the Server

### Run command (from local Windows)
```
cd D:/KGPolar/polarKD_Gowtham/Knowledge_graph/Code
..\venv\Scripts\streamlit.exe run frontend_light_v2.py
```

### Run command on Linux server
```bash
cd /mnt/storage/midas/polarKD_Gowtham/Knowledge_graph/Code
mamba activate carelens
streamlit run frontend_light_v2.py --server.port 8502
```

> Port 8501 was already in use, so 8502 was used instead.

---

## 9. Viewing the App in Local Browser (SSH Tunnel)

Run this on your **local Windows machine** (not the server), while connected to VPN:

```bash
ssh -L 8502:localhost:8502 gv0313@your-server-ip
```

Then open in browser:
```
http://localhost:8502
```

---

## 10. VS Code Remote SSH to UNT Server

### Problem
VS Code Remote SSH doesn't accept `students\gv0313@ci-l-84cl144.is.unt.edu` in the Ctrl+Shift+P prompt (backslash in username breaks it).

### Fix: SSH config file
File location: `C:\Users\koole\.ssh\config`

```
Host unt-server
    HostName ci-l-84cl144.is.unt.edu
    User students\gv0313
```

### How to connect
1. Connect to UNT VPN first
2. `Ctrl+Shift+P` → **Remote-SSH: Connect to Host**
3. Select **`unt-server`** from the list — VS Code connects automatically using the config

---

## 11. Claude Code on the Server

Claude Code is installed via nvm (Node Version Manager) in the home directory — no root or conda permissions needed.

### Install steps (already done, for reference)

```bash
# Install nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash

# Load nvm in current session
export NVM_DIR="$HOME/.nvm"
source "$NVM_DIR/nvm.sh"

# Install Node.js LTS
nvm install --lts

# Install Claude Code
npm install -g @anthropic-ai/claude-code
```

### Run Claude Code
```bash
cd /mnt/storage/salif/polarKD_Gowtham
claude
```
Enter your Anthropic API key on first launch (find it at console.anthropic.com → API Keys).

### nvm loads automatically on new terminals via ~/.zshrc
If `claude` is ever not found, reload nvm manually:
```bash
export NVM_DIR="$HOME/.nvm"
source "$NVM_DIR/nvm.sh"
```

---

## 12. Storage Layout

| Path | What's there |
|---|---|
| `/mnt/storage/salif/polarKD_Gowtham` | Active project (use this) |
| `/mnt/storage/midas/polarKD_Gowtham` | Older copy |
| `/mnt/storage/midas/conda` | carelens conda env (symlinked from `~/.conda`) |
| `/mnt/storage/midas/applications/miniforge3` | Shared miniforge3 — read-only, owned by kh0718 |

> Use `pip install` for new Python packages (not `mamba install`) — the shared miniforge3 cache is not writable.

---

## 13. Quick Reference — Common Commands

| Task | Command |
|---|---|
| Check disk space | `df -h` |
| Check home folder usage | `du -sh ~/.[^.]* ~/* 2>/dev/null \| sort -rh \| head -20` |
| Check what's in /tmp | `ls -ltr /tmp` |
| Find files using space | `du -sh /home/* 2>/dev/null \| sort -rh \| head -20` |
| Gzip a file | `gzip filename` |
| Gzip keep original | `gzip -k filename` |
| Decompress | `gunzip filename.gz` |
| Check conda envs | `mamba env list` |
| Git log for a file | `git log --oneline --all -- filename` |
| Restore file from git | `git checkout <hash> -- filename` |
