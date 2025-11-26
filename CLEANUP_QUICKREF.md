# Repository Cleanup - Quick Reference

## The Problem
- ❌ Git error: `fatal: mmap failed: Invalid argument`
- ❌ File named `nul` (Windows reserved name)
- ❌ 60+ temporary documentation files cluttering repo
- ❌ Deprecated scripts and output files tracked

## The Solution (3 Commands)

```powershell
cd C:\Users\tech\Projects\docling-n8n
.\CLEANUP_MASTER.ps1
# Follow prompts, then:
git add .
git commit -m "Clean up repository structure"
```

## What Happens

| Step | Action | Result |
|------|--------|--------|
| 1 | Fix git index | Removes `nul`, repairs corruption |
| 2 | Archive docs | 60+ files → `._archive/docs/` |
| 3 | Archive scripts | 10+ files → `._archive/scripts/` |
| 4 | Archive output | Directories → `._archive/output/` |
| 5 | Update .gitignore | Prevents future clutter |

## Quick Commands

```powershell
# Full cleanup (recommended)
.\CLEANUP_MASTER.ps1

# Preview changes only
.\CLEANUP_MASTER.ps1 -DryRun

# Just fix git index
.\fix-git-index.ps1

# Just archive files
.\cleanup-repo.ps1

# Check results
git status
ls ._archive

# Commit when ready
git add .
git commit -m "Clean up repository"

# Rebuild Docker
docker-compose down
docker-compose build
docker-compose up -d
```

## File Locations After Cleanup

```
docling-n8n/
├── ._archive/              # ← All temporary files moved here
│   ├── docs/              # 60+ status markdown files
│   ├── scripts/           # Deprecated Python scripts
│   ├── output/            # Old processed documents
│   └── old-workflows/     # Legacy JSON files
├── README.md              # ← Main docs (kept)
├── PROJECT_AUDIT_AND_ROADMAP.md  # ← Important (kept)
├── VIDEO_RAG_DEPLOYMENT_GUIDE.md # ← Important (kept)
├── IMPLEMENTATION_COMPLETE.md    # ← Important (kept)
├── backend/               # ← Source code (untouched)
├── frontend/              # ← Source code (untouched)
├── src/                   # ← Core modules (untouched)
└── .gitignore            # ← Updated to prevent future clutter
```

## Verification Checklist

- [ ] `git status` shows clean working directory
- [ ] `ls ._archive` shows archived files
- [ ] `docker-compose ps` shows services running
- [ ] `curl http://localhost:8000/health` returns 200
- [ ] Frontend accessible at http://localhost:3000

## After Cleanup

**Safe to delete after verification:**
```powershell
Remove-Item ._archive -Recurse -Force
```

**Or keep as backup:**
- Already in `.gitignore`
- Won't be committed to git
- Safe to leave indefinitely

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `nul` file persists | `cmd /c "del nul"` or `Remove-Item "\\?\C:\Users\tech\Projects\docling-n8n\nul"` |
| Git still corrupt | `Remove-Item .git\index -Force; git reset` |
| Missing files | Check `._archive/` subdirectories |
| Want file back | `Copy-Item ._archive/docs/FILE.md ./` |

## Need More Help?

Read full documentation:
- **CLEANUP_README.md** - Complete guide
- **fix-git-index.ps1** - Git repair script
- **cleanup-repo.ps1** - File archival script
- **CLEANUP_MASTER.ps1** - Orchestration script

---

**TL;DR:** Run `.\CLEANUP_MASTER.ps1`, follow prompts, commit changes. Done! ✅
