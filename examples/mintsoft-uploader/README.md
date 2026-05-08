# Example Pool: FodaFilment Mintsoft Uploader Project

This folder shows what a context pool looks like after a few days of use across three agents working on the same project.

To try it yourself:

```bash
# Read what's there
python3 ../../src/context_pool.py read .

# See structured state
python3 ../../src/context_pool.py state .

# Add your own entry
echo "Tested the upload — works on the staging brand." | \
  python3 ../../src/context_pool.py append . claude-code "mintsoft-uploader"
```

The files in this folder are committed as a worked example. In your real project, you'd `.gitignore` the pool's contents (or commit them — your call, depending on whether you want shared team context).
