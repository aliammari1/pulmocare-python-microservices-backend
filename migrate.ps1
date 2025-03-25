# PowerShell Script for Data Migration in SigNoz
# Equivalent to migrate.sh but designed for Windows systems

# Initialize BASE_DIR before parameter block
$Script:BASE_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("standalone", "swarm")]
    [string]$DeploymentType,

    [Parameter(Mandatory=$true)]
    [ValidateSet("all", "clickhouse", "zookeeper", "signoz", "alertmanager")]
    [string]$MigrationComponent,

    [Parameter(Mandatory=$true)]
    [ValidateSet("migrate", "post-migrate")]
    [string]$Operation,

    [string]$SignozRootDir = (Join-Path $Script:BASE_DIR "..\..\"),

    [switch]$Silent,

    [switch]$Help
)

# Script constants
$Script:NAME = "volume-migration"
$Script:DOCKER_COMPOSE_DIR = "deploy/docker"
$Script:DOCKER_SWARM_COMPOSE_DIR = "deploy/docker-swarm"
$Script:STANDALONE_DATA_DIR = "$DOCKER_COMPOSE_DIR/clickhouse-setup/data"
$Script:SWARM_DATA_DIR = "$DOCKER_SWARM_COMPOSE_DIR/clickhouse-setup/data"
$Script:SIGNOZ_NETWORK = "signoz-net"
$Script:SIGNOZ_NETWORK_OLD = "clickhouse-setup_default"

# Runtime variables
$Script:DOCKER_COMPOSE_CMD = "docker compose"
$Script:DEPLOYMENT_TYPE = ""
$Script:MIGRATION_COMPONENT = ""
$Script:OPERATION = ""
$Script:SIGNOZ_ROOT_DIR = Join-Path $BASE_DIR "..\..\""
$Script:SILENT = $false

function Write-Help {
    Write-Host "NAME"
    Write-Host "`t$NAME - Migrate data from bind mounts to Docker volumes`n"
    Write-Host "USAGE"
    Write-Host "`t$NAME [-DeploymentType <type>] [-MigrationComponent <component>] [-Operation <op>] [-SignozRootDir <path>] [-Silent] [-Help]`n"
    Write-Host "OPTIONS:"
    Write-Host "`t-DeploymentType`tDeployment type (standalone, swarm)"
    Write-Host "`t-MigrationComponent`tMigration component (all, clickhouse, zookeeper, signoz, alertmanager)"
    Write-Host "`t-Operation`tOperation (migrate, post-migrate)"
    Write-Host "`t-SignozRootDir`tSignoz root directory (default: parent of script location)"
    Write-Host "`t-Silent`tSilent mode"
    Write-Host "`t-Help`tShow this help message"
}

function Write-Message {
    param([string]$Message)
    if (-not $Script:SILENT) {
        Write-Host "$Script:NAME: $Message"
    }
}

function Write-Error {
    param([string]$Message)
    Write-Host "$Script:NAME: $Message" -ForegroundColor Red
}

function Test-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Error "Docker is not available. Please ensure Docker is installed and in your PATH."
        exit 1
    }
}

function Get-DockerComposeCmd {
    if (docker compose version 2>$null) {
        return 'docker compose'
    }
    return 'docker-compose'
}

function Get-ComposeDir {
    param(
        [string]$DeploymentType,
        [string]$SignozRootDir
    )
    
    if ($DeploymentType -eq "standalone") {
        return Join-Path $SignozRootDir $Script:DOCKER_COMPOSE_DIR
    }
    elseif ($DeploymentType -eq "swarm") {
        return Join-Path $SignozRootDir $Script:DOCKER_SWARM_COMPOSE_DIR
    }
}

function Get-DataDir {
    param(
        [string]$DeploymentType,
        [string]$SignozRootDir
    )
    
    if ($DeploymentType -eq "standalone") {
        return Join-Path $SignozRootDir $Script:STANDALONE_DATA_DIR
    }
    elseif ($DeploymentType -eq "swarm") {
        return Join-Path $SignozRootDir $Script:SWARM_DATA_DIR
    }
}

function Start-Services {
    param(
        [string]$DeploymentType,
        [string]$SignozRootDir
    )

    $composeDir = Get-ComposeDir $DeploymentType $SignozRootDir

    if ($DeploymentType -eq "standalone") {
        Write-Message "Starting Docker Standalone services"
        Invoke-Expression "$Script:DOCKER_COMPOSE_CMD -f `"$composeDir/docker-compose.yaml`" up -d --remove-orphans"
    }
    elseif ($DeploymentType -eq "swarm") {
        Write-Message "Starting Docker Swarm services"
        docker stack deploy -c "$composeDir/docker-compose.yaml" signoz
    }
}

function Test-DockerNetwork {
    param([string]$Network)
    
    $result = docker network inspect $Network 2>$null
    return $LASTEXITCODE -eq 0
}

function Stop-StandaloneServices {
    param([string]$ComposeDir)

    Write-Message "Stopping Docker Standalone services"
    Invoke-Expression "$Script:DOCKER_COMPOSE_CMD -f `"$ComposeDir/docker-compose.yaml`" down"

    Write-Message "Cleaning up containers and networks"
    $containers = docker ps -q --filter "label=com.docker.compose.project=clickhouse-setup"
    if ($containers) {
        docker stop $containers
        docker rm $containers
    }

    if (Test-DockerNetwork $Script:SIGNOZ_NETWORK) {
        $network = $Script:SIGNOZ_NETWORK
    }
    elseif (Test-DockerNetwork $Script:SIGNOZ_NETWORK_OLD) {
        $network = $Script:SIGNOZ_NETWORK_OLD
    }
    else {
        Write-Message "No signoz network found, skipping cleanup"
        return
    }

    $networkContainers = docker network inspect $network --format '{{ range $key, $value := .Containers }}{{printf "%s " .Name}}{{ end }}'
    if ($networkContainers) {
        $networkContainers.Split() | ForEach-Object {
            if ($_) {
                docker stop $_ 2>$null
                docker rm $_ 2>$null
            }
        }
    }
    docker network rm $network 2>$null
}

function Stop-SwarmServices {
    param([string]$ComposeDir)
    
    Write-Message "Stopping Docker Swarm services"
    docker stack rm -c "$ComposeDir/docker-compose.yaml" signoz
}

function Stop-Services {
    param(
        [string]$DeploymentType,
        [string]$SignozRootDir
    )

    $composeDir = Get-ComposeDir $DeploymentType $SignozRootDir

    if ($DeploymentType -eq "standalone") {
        Stop-StandaloneServices $composeDir
    }
    elseif ($DeploymentType -eq "swarm") {
        Stop-SwarmServices $composeDir
    }
}

function Invoke-Migration {
    param(
        [string]$Component,
        [string]$BindMounts,
        [string]$NewVolume,
        [string]$OwnerUidGid
    )

    Write-Message "Creating new volume $NewVolume"
    docker volume create $NewVolume --label "com.docker.compose.project=signoz" | Out-Null

    Write-Message "Migrating $Component data to new volume $NewVolume"
    if ($Component -eq "clickhouse") {
        Write-Message "Please be patient, this may take a while for clickhouse migration..."
    }

    $command = if ($OwnerUidGid) {
        "cp -rp /data/* /volume; chown -R $OwnerUidGid /volume"
    }
    else {
        "cp -rp /data/* /volume"
    }

    $result = docker run --rm -v "${BindMounts}:/data" -v "${NewVolume}:/volume" alpine sh -c $command
    if ($LASTEXITCODE -eq 0) {
        Write-Message "Migration of $Component completed successfully"
    }
    else {
        Write-Error "Migration of $Component failed"
        exit 1
    }
}

function Invoke-PostMigration {
    param(
        [string]$Component,
        [string]$DataDir
    )

    Write-Message "Running post-migration cleanup for $Component"
    if ($Component -eq "clickhouse") {
        Write-Message "Please be patient, this may take a while for clickhouse post-migration cleanup..."
    }

    $result = docker run --rm -v "${DataDir}:/data" alpine sh -c "rm -rf /data/*"
    if ($LASTEXITCODE -eq 0) {
        Write-Message "Post-migration cleanup for $Component completed successfully"
    }
    else {
        Write-Error "Post-migration cleanup for $Component failed"
        exit 1
    }
}

function Invoke-ComponentMigration {
    param(
        [string]$Component,
        [string]$DataDir
    )

    switch ($Component) {
        "clickhouse" {
            Invoke-Migration "clickhouse" "$DataDir/clickhouse" "signoz-clickhouse" "101:101"
            if (Test-Path "$DataDir/clickhouse-2/uuid") {
                Invoke-Migration "clickhouse-2" "$DataDir/clickhouse-2" "signoz-clickhouse-2" "101:101"
            }
            if (Test-Path "$DataDir/clickhouse-3/uuid") {
                Invoke-Migration "clickhouse-3" "$DataDir/clickhouse-3" "signoz-clickhouse-3" "101:101"
            }
        }
        "zookeeper" {
            Invoke-Migration "zookeeper" "$DataDir/zookeeper-1" "signoz-zookeeper-1" "1000:1000"
            if (Test-Path "$DataDir/zookeeper-2/data") {
                Invoke-Migration "zookeeper-2" "$DataDir/zookeeper-2" "signoz-zookeeper-2" "1000:1000"
            }
            if (Test-Path "$DataDir/zookeeper-3/data") {
                Invoke-Migration "zookeeper-3" "$DataDir/zookeeper-3" "signoz-zookeeper-3" "1000:1000"
            }
        }
        "signoz" {
            Invoke-Migration "signoz" "$DataDir/signoz" "signoz-sqlite" ""
        }
        "alertmanager" {
            Invoke-Migration "alertmanager" "$DataDir/alertmanager" "signoz-alertmanager" ""
        }
    }
}

function Invoke-ComponentPostMigration {
    param(
        [string]$Component,
        [string]$DataDir
    )

    switch ($Component) {
        "clickhouse" {
            Invoke-PostMigration "clickhouse" "$DataDir/clickhouse"
            if (Test-Path "$DataDir/clickhouse-2") {
                Invoke-PostMigration "clickhouse-2" "$DataDir/clickhouse-2"
            }
            if (Test-Path "$DataDir/clickhouse-3") {
                Invoke-PostMigration "clickhouse-3" "$DataDir/clickhouse-3"
            }
        }
        "zookeeper" {
            Invoke-PostMigration "zookeeper" "$DataDir/zookeeper-1"
            if (Test-Path "$DataDir/zookeeper-2") {
                Invoke-PostMigration "zookeeper-2" "$DataDir/zookeeper-2"
            }
            if (Test-Path "$DataDir/zookeeper-3") {
                Invoke-PostMigration "zookeeper-3" "$DataDir/zookeeper-3"
            }
        }
        "signoz" {
            Invoke-PostMigration "signoz" "$DataDir/signoz"
        }
        "alertmanager" {
            Invoke-PostMigration "alertmanager" "$DataDir/alertmanager"
        }
    }
}

function Start-Migration {
    param(
        [string]$DeploymentType,
        [string]$Component,
        [string]$SignozRootDir
    )

    $dataDir = Get-DataDir $DeploymentType $SignozRootDir
    Stop-Services $DeploymentType $SignozRootDir

    if ($Component -eq "all") {
        @("clickhouse", "zookeeper", "signoz", "alertmanager") | ForEach-Object {
            Invoke-ComponentMigration $_ $dataDir
        }
    }
    else {
        Invoke-ComponentMigration $Component $dataDir
    }

    Start-Services $DeploymentType $SignozRootDir
}

function Start-PostMigration {
    param(
        [string]$DeploymentType,
        [string]$Component,
        [string]$SignozRootDir
    )

    $dataDir = Get-DataDir $DeploymentType $SignozRootDir

    if ($Component -eq "all") {
        @("clickhouse", "zookeeper", "signoz", "alertmanager") | ForEach-Object {
            Invoke-ComponentPostMigration $_ $dataDir
        }
    }
    else {
        Invoke-ComponentPostMigration $Component $dataDir
    }
}

# Main execution block
if ($Help) {
    Write-Help
    exit 0
}

$Script:SILENT = $Silent
$Script:DEPLOYMENT_TYPE = $DeploymentType
$Script:MIGRATION_COMPONENT = $MigrationComponent
$Script:OPERATION = $Operation
$Script:SIGNOZ_ROOT_DIR = $SignozRootDir

Test-Docker
$Script:DOCKER_COMPOSE_CMD = Get-DockerComposeCmd

if ($Operation -eq "migrate") {
    Start-Migration $DeploymentType $MigrationComponent $SignozRootDir
}
elseif ($Operation -eq "post-migrate") {
    Start-PostMigration $DeploymentType $MigrationComponent $SignozRootDir
}