pipeline {
    agent any

    environment {
        // Use standard docker-compose command for Windows
        DOCKER_COMPOSE = 'docker-compose'
        SONAR_HOST_URL = 'http://sonarqube:9002'
        DOCKER_REGISTRY = 'localhost:5000'
        // Use PowerShell to get version
        VERSION = powershell(script: '(git describe --tags --always) -Or "dev"', returnStdout: true).trim()
        CONSUL_HTTP_ADDR = 'http://localhost:8500'
    }

    tools {
        // Make sure this Python tool is configured in Jenkins
        python 'Python3'
    }

    stages {
        stage('Setup Tools') {
            steps {
                script {
                    // Windows-compatible pip installation
                    bat '''
                        curl -o get-pip.py https://bootstrap.pypa.io/get-pip.py
                        python get-pip.py --user
                        python -m pip install --upgrade pip
                        python -m pip install --user pytest pytest-cov pytest-asyncio aiohttp requests
                    '''
                }
            }
        }

        stage('Checkout') {
            steps {
                checkout scm
                bat 'git fetch --tags'
            }
        }

        stage('Install Dependencies') {
            parallel {
                stage('Medecins') {
                    steps {
                        dir('services/medecins') {
                            bat 'python -m pip install -r requirements.txt'
                        }
                    }
                }
                stage('Ordonnances') {
                    steps {
                        dir('services/ordonnances') {
                            bat 'python -m pip install -r requirements.txt'
                        }
                    }
                }
                stage('Patients') {
                    steps {
                        dir('services/patients') {
                            bat 'python -m pip install -r requirements.txt'
                        }
                    }
                }
                stage('Radiologues') {
                    steps {
                        dir('services/radiologues') {
                            bat 'python -m pip install -r requirements.txt'
                        }
                    }
                }
                stage('Reports') {
                    steps {
                        dir('services/reports') {
                            bat 'python -m pip install -r requirements.txt'
                        }
                    }
                }
                stage('Auth') {
                    steps {
                        dir('services/auth') {
                            bat 'python -m pip install -r requirements.txt'
                        }
                    }
                }
            }
        }

        stage('Static Code Analysis') {
            parallel {
                stage('Lint') {
                    steps {
                        bat '''
                            python -m pip install flake8 black
                            FOR /R %%F IN (*.py) DO (
                                echo Checking %%F
                                python -m flake8 "%%F"
                                python -m black --check "%%F"
                            )
                        '''
                    }
                }
                stage('Security Scan') {
                    steps {
                        bat '''
                            python -m pip install bandit safety
                            FOR /R %%F IN (*.py) DO (
                                echo Scanning %%F
                                python -m bandit "%%F"
                            )
                            python -m safety check
                        '''
                    }
                }
            }
        }

        stage('Run Tests') {
            parallel {
                stage('Medecins Tests') {
                    steps {
                        dir('services/medecins/app') {
                            bat 'python -m pytest --cov=. --cov-report=xml -v --junitxml=test-results.xml'
                        }
                    }
                }
                stage('Ordonnances Tests') {
                    steps {
                        dir('services/ordonnances/app') {
                            bat 'python -m pytest --cov=. --cov-report=xml -v --junitxml=test-results.xml'
                        }
                    }
                }
                stage('Patients Tests') {
                    steps {
                        dir('services/patients/app') {
                            bat 'python -m pytest --cov=. --cov-report=xml -v --junitxml=test-results.xml'
                        }
                    }
                }
                stage('Radiologues Tests') {
                    steps {
                        dir('services/radiologues/app') {
                            bat 'python -m pytest --cov=. --cov-report=xml -v --junitxml=test-results.xml'
                        }
                    }
                }
                stage('Reports Tests') {
                    steps {
                        dir('services/reports/app') {
                            bat 'python -m pytest --cov=. --cov-report=xml -v --junitxml=test-results.xml'
                        }
                    }
                }
                stage('Auth Tests') {
                    steps {
                        dir('services/auth/app') {
                            bat 'python -m pytest --cov=. --cov-report=xml -v --junitxml=test-results.xml'
                        }
                    }
                }
            }
        }

        stage('Integration Tests') {
            steps {
                bat 'python -m pytest test_integration.py -v --junitxml=integration-test-results.xml'
            }
        }

        stage('SonarQube Analysis') {
            steps {
                script {
                    def scannerHome = tool 'SonarScanner'
                    withSonarQubeEnv('SonarQube') {
                        bat "${scannerHome}\\bin\\sonar-scanner.bat -Dsonar.projectVersion=${VERSION}"
                    }
                }
            }
        }

        stage('Quality Gate') {
            steps {
                timeout(time: 1, unit: 'HOURS') {
                    waitForQualityGate abortPipeline: true
                }
            }
        }

        stage('Build and Push Images') {
            steps {
                script {
                    docker.withRegistry("https://${DOCKER_REGISTRY}", 'docker-credentials') {
                        bat """
                            ${DOCKER_COMPOSE} build
                            ${DOCKER_COMPOSE} push
                        """
                    }
                }
            }
        }

        stage('Deploy') {
            when {
                branch 'main'
            }
            stages {
                stage('Infrastructure') {
                    steps {
                        // Deploy infrastructure services first
                        bat """
                            ${DOCKER_COMPOSE} up -d consul mongodb redis rabbitmq elasticsearch kibana prometheus grafana jaeger
                            timeout /t 30 /nobreak
                        """
                    }
                }
                stage('API Gateway') {
                    steps {
                        // Deploy APISIX Gateway
                        bat "${DOCKER_COMPOSE} up -d etcd apisix apisix-dashboard apisix-init"
                    }
                }
                stage('Core Services') {
                    steps {
                        script {
                            def services = ['auth', 'medecins', 'ordonnances', 'patients', 'radiologues', 'reports']
                            for (service in services) {
                                bat """
                                    ${DOCKER_COMPOSE} up -d ${service}
                                    rem Wait for service to be ready
                                    timeout /t 10 /nobreak
                                """
                                // Use PowerShell for complex HTTP requests
                                powershell """
                                    \$maxRetries = 30
                                    \$retryCount = 0
                                    \$success = \$false
                                    
                                    while (-not \$success -and \$retryCount -lt \$maxRetries) {
                                        try {
                                            \$response = Invoke-WebRequest -Uri "${CONSUL_HTTP_ADDR}/v1/health/service/${service}" -UseBasicParsing
                                            if (\$response.StatusCode -eq 200) {
                                                \$success = \$true
                                                Write-Host "Service ${service} is registered with Consul"
                                            }
                                        } catch {
                                            Write-Host "Waiting for service ${service} to register with Consul... \$retryCount/\$maxRetries"
                                        }
                                        
                                        if (-not \$success) {
                                            Start-Sleep -Seconds 2
                                            \$retryCount++
                                        }
                                    }
                                    
                                    if (-not \$success) {
                                        Write-Error "Service ${service} failed to register with Consul after \$maxRetries attempts"
                                        exit 1
                                    }
                                """
                            }
                        }
                    }
                }
                stage('Monitoring Setup') {
                    steps {
                        bat "${DOCKER_COMPOSE} up -d otel-collector"
                        
                        // Use PowerShell for JSON posting
                        powershell '''
                            $dashboardJson = Get-Content -Raw "monitoring/grafana/dashboards/services-dashboard.json"
                            $headers = @{
                                "Content-Type" = "application/json"
                            }
                            $base64AuthInfo = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes(("admin:admin")))
                            $headers.Add("Authorization", "Basic $base64AuthInfo")
                            
                            Invoke-RestMethod -Uri "http://grafana:3000/api/dashboards/db" -Method Post -Body $dashboardJson -Headers $headers
                        '''
                    }
                }
                stage('Health Check') {
                    steps {
                        script {
                            // PowerShell for health checks
                            powershell '''
                                # Helper function for health checks with retry
                                function Test-ServiceHealth {
                                    param($Url, $MaxRetries = 5, $RetryDelay = 10)
                                    
                                    for ($i = 1; $i -le $MaxRetries; $i++) {
                                        try {
                                            Write-Host "Checking health for $Url (Attempt $i/$MaxRetries)"
                                            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing
                                            if ($response.StatusCode -eq 200) {
                                                Write-Host "Service is healthy: $Url" -ForegroundColor Green
                                                return $true
                                            }
                                        } catch {
                                            Write-Host "Service health check failed: $Url" -ForegroundColor Yellow
                                        }
                                        
                                        Start-Sleep -Seconds $RetryDelay
                                    }
                                    
                                    Write-Error "Service health check failed after $MaxRetries attempts: $Url"
                                    return $false
                                }
                                
                                # Check APISIX Gateway
                                Test-ServiceHealth -Url "http://apisix:9180/apisix/admin/health"
                                
                                # Check all services through APISIX
                                Test-ServiceHealth -Url "http://apisix:9080/api/medecins/health"
                                Test-ServiceHealth -Url "http://apisix:9080/api/ordonnances/health"
                                Test-ServiceHealth -Url "http://apisix:9080/api/patients/health"
                                Test-ServiceHealth -Url "http://apisix:9080/api/radiologues/health"
                                Test-ServiceHealth -Url "http://apisix:9080/api/reports/health"
                                Test-ServiceHealth -Url "http://apisix:9080/api/auth/health"
                            '''
                        }
                    }
                }
            }
        }
    }

    post {
        always {
            junit '**/test-results.xml, **/integration-test-results.xml'
            publishCoverage adapters: [coberturaAdapter('**/coverage.xml')]

            script {
                // Cleanup only if not on main branch
                if (env.BRANCH_NAME != 'main') {
                    bat "${DOCKER_COMPOSE} down --volumes --remove-orphans"
                }
            }
            cleanWs()
        }
        success {
            script {
                def message = "Pipeline for version ${VERSION} completed successfully!"
                echo message
                // Add notification logic here if needed
            }
        }
        failure {
            script {
                def message = "Pipeline for version ${VERSION} failed! Check the logs for details."
                echo message
                
                // Create logs directory and collect Docker logs
                bat '''
                    if not exist pipeline-logs mkdir pipeline-logs
                    docker-compose logs > pipeline-logs\\docker-compose.log 2>&1
                '''
                
                // Using PowerShell to create archive
                powershell '''
                    Compress-Archive -Path pipeline-logs -DestinationPath pipeline-logs.zip -Force
                '''
                
                archiveArtifacts artifacts: 'pipeline-logs.zip', fingerprint: true
            }
        }
    }
}
