# Windows signed installer

This folder builds the single-file Windows setup executable for Local MoE Studio - Thai FDA Edition.

## Build locally on Windows

~~~powershell
.\installer\windows\build_installer.ps1 -DataPack "C:\secure\ThaiFDA_DataPack.zip"
~~~

The output is dist\ThaiFDA_LocalMoE_Setup.exe.

## Authenticode sign with a PFX certificate

~~~powershell
.\installer\windows\sign_installer.ps1 -ExePath ".\dist\ThaiFDA_LocalMoE_Setup.exe" -PfxPath "C:\secure\publisher-code-signing.pfx" -PfxPassword $env:PFX_PASSWORD
~~~

The signing script uses SHA-256, RFC3161 timestamping, and then runs signtool verify /pa /v.

## Production CI

The GitHub Actions workflow expects these repository secrets:

- THAI_FDA_DATA_PACK_URL
- THAI_FDA_DATA_PACK_SHA256
- WINDOWS_SIGNING_PFX_BASE64
- WINDOWS_SIGNING_PFX_PASSWORD

Never commit the PFX or private key to GitHub.

A self-signed certificate is suitable only for controlled internal environments where its trust chain is deliberately deployed to the target PCs. It is not equivalent to a publicly trusted production signature.
