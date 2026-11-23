# AniBox releases

Ready-to-run Windows packages of **AniBox**, a private player and organizer for the anime on your own
drives. No Python install needed.

- **First install:** download the newest `AniBox-<version>-windows.zip` from the
  [Releases page](https://github.com/patschgoo/AniBox-release/releases), right-click it → Properties → tick **Unblock**,
  unpack it anywhere and double-click `AniBox.bat`.
- **Updates:** AniBox notices new versions by itself (Home and Settings → Updates). Click **Download**,
  then **Update now**. Your library, progress and settings stay.

`latest.json` describes the newest version and points at its download (AniBox reads it); each release
lists the zip's SHA-256 and has it as a `.sha256` file too. New versions arrive on an `upload/v<version>`
branch; the Release workflow turns them into a release and updates `latest.json`.
