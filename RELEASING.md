# Releasing a new version

1. Set the version in `voicefork/__init__.py`, e.g. `__version__ = "0.1.2"`.
2. Add a section for it at the top of `CHANGELOG.md`.
3. Commit and push:
   ```
   git add .
   git commit -m "v0.1.2"
   git push
   ```
4. On GitHub: **Releases → Draft a new release**. The tag must match the version: `v0.1.2`.
5. Paste the changelog section as the description. Optionally add **one line** for the app's
   update bar (hidden on the release page):
   ```
   <!-- voicefork: Fixes GTX 1060 support and adds a desktop shortcut. -->
   ```
   Keep it short: the bar shows about 70 characters, the rest is in the tooltip (max 160).
   Plain text only. Without this line the bar just says the new version is out.
6. **Publish release.** Apps on v0.1.2 or newer show the update bar within a day (not while they are in Offline mode).
