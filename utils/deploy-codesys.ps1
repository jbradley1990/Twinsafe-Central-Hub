# ------------------------------------------------------------
# CODESYS Deployment Script
# Copies Archive.prj, .app/.crc files, and visu folder to targets
# ------------------------------------------------------------

param(
    [string]$ProjectRemotePath  = "/var/opt/codesys/PlcLogic",                                       # Base remote CODESYS path on target
    [string]$SourceDir          = "V:\Userdoc\Mechatronics\Applications\Twinsafe DLS\CODESYS\.app",  # Local folder containing .app/.crc
    [string]$RemotePath         = "$ProjectRemotePath/DLS/Updates/",                                 # Remote Updates directory
    [string]$VisuSourceDir      = (Join-Path $SourceDir "PlcLogic\visu"),                            # Local visu folder (derived from SourceDir)
    [string]$VisuRemotePath     = "$ProjectRemotePath/DLS/Updates/visu",                             # Remote visu directory
    [string]$ProjectFile        = "V:\Userdoc\Mechatronics\Applications\Twinsafe DLS\CODESYS\.project\Archive.prj", # Boot project file
    [string]$HostsFile          = ".\utils\hosts.txt",                                               # File containing target IPs/hostnames
    [string]$User               = "root",                                                            # SSH username
    [string]$Key                = "$env:USERPROFILE\.ssh\tl_prototype_key"                           # SSH private key path
)

$ErrorActionPreference = "Stop"                                                                     # Stop script immediately on any error

# ---- Validate required local paths ----
if (-not (Test-Path -LiteralPath $HostsFile))   { throw "Hosts file not found: $HostsFile" }        # Ensure hosts file exists
if (-not (Test-Path -LiteralPath $SourceDir))   { throw "SourceDir not found: $SourceDir" }         # Ensure .app folder exists
if (-not (Test-Path -LiteralPath $ProjectFile)) { throw "Project file not found: $ProjectFile" }    # Ensure Archive.prj exists

# ---- Check visu folder (optional) ----
if (-not (Test-Path -LiteralPath $VisuSourceDir)) {                                                 # Check if visu exists
    Write-Warning "VisuSourceDir not found: $VisuSourceDir (skipping visu copy)"                    # Warn if visu missing
    $CopyVisu = $false                                                                              # Disable visu copy
} else {
    $CopyVisu = $true                                                                               # Enable visu copy
}

# ---- Load target hosts (ignore blank lines and comments) ----
$Targets = Get-Content -LiteralPath $HostsFile | Where-Object { $_ -and $_ -notmatch '^\s*#' }      # Load hosts safely

# ---- Loop through each target ----
foreach ($Target in $Targets) {                                                                     # Deploy to each host

    Write-Host "==> Deploying to $Target"                                                           # Print target being processed

    # Build remote destination strings
    $DlsDest      = "$User@$Target`:$RemotePath"                                                     # Destination for .app/.crc
    $VisuDest     = "$User@$Target`:$VisuRemotePath/"                                                # Destination for visu contents
    $ProjectDest  = "$User@$Target`:$ProjectRemotePath/Archive.prj"                                  # Explicit remote Archive.prj path

    # ---- Copy Archive.prj ----
    Write-Host "   -> Copying Archive.prj"                                                           # Log action
    scp -i $Key -C -q "$ProjectFile" "$ProjectDest"                                                  # Copy project file

    # ---- Find .app and .crc files ----
    $AppFiles = @(Get-ChildItem -LiteralPath $SourceDir -Filter *.app -File)                         # Force array
    $CrcFiles = @(Get-ChildItem -LiteralPath $SourceDir -Filter *.crc -File)                         # Force array
    $Files    = @($AppFiles + $CrcFiles)                                                             # Combine arrays

    # ---- Copy each .app and .crc file ----
    foreach ($File in $Files) {                                                                      # Iterate files
        Write-Host "   -> Copying $($File.Name)"                                                     # Log file
        scp -i $Key -C -q "$($File.FullName)" "$DlsDest"                                             # Copy to Updates folder
    }

    # ---- Copy visu folder contents if present ----
    if ($CopyVisu) {                                                                                 # Only if visu exists

        Write-Host "   -> Ensuring remote visu directory exists"                                     # Log mkdir
        ssh -i $Key "$User@$Target" "mkdir -p '$VisuRemotePath'"                                     # Create remote folder

        Write-Host "   -> Copying visu contents"                                                     # Log copy

        $VisuItems = Get-ChildItem -LiteralPath $VisuSourceDir                                       # List items in visu folder
        foreach ($Item in $VisuItems) {                                                              # Copy each item
            scp -i $Key -C -r -q "$($Item.FullName)" "$VisuDest"                                     # Copy item to remote visu
        }
    }

    Write-Host "Deployment complete for $Target"                                                     # Done with this host
}

Write-Host "All deployments complete."                                                               # Final completion message