pipeline {
    agent any

    environment {
        DOCKER_COMPOSE = 'docker compose'
        SONAR_HOST_URL = 'http://sonarqube:9002'
        DOCKER_REGISTRY = 'localhost:5000'
        VERSION = sh(script: 'git describe --tags --always || echo "dev"', returnStdout: true).trim()
        CONSUL_HTTP_ADDR = 'http://localhost:8500'
    }

    tools {
        python 'Python3'
    }

    stages {
        stage('Setup Tools') {
            steps {
                script {
                    // Install required tools
                    sh '''
                        curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
                        python3 get-pip.py --user
                        python3 -m pip install --upgrade pip
                        python3 -m pip install --user pytest pytest-cov pytest-asyncio aiohttp requests
                    '''
                }
            }
        }

        stage('Checkout') {
            steps {
                checkout scm
                sh 'git fetch --tags'
            }
        }

        stage('Install Dependencies') {
            parallel {
                stage('Medecins') {
                    steps {
                        dir('services/medecins') {
                            sh 'python3 -m pip install -r requirements.txt'
                        }
                    }
                }
                stage('Ordonnances') {
                    steps {
                        dir('services/ordonnances') {
                            sh 'python3 -m pip install -r requirements.txt'
                        }
                    }
                }
                stage('Patients') {
                    steps {
                        dir('services/patients') {
                            sh 'python3 -m pip install -r requirements.txt'
                        }
                    }
                }
                stage('Radiologues') {
                    steps {
                        dir('services/radiologues') {
                            sh 'python3 -m pip install -r requirements.txt'
                        }
                    }
                }
                stage('Reports') {
                    steps {
                        dir('services/reports') {
                            sh 'python3 -m pip install -r requirements.txt'
                        }
                    }
                }
            }
        }

        stage('Static Code Analysis') {
            parallel {
                stage('Lint') {
                    steps {
                        sh '''
                            python3 -m pip install flake8 black
                            find . -name "*.py" -not -path "*/\.*" -not -path "*/venv/*" | xargs flake8
                            find . -name "*.py" -not -path "*/\.*" -not -path "*/venv/*" | xargs black --check
                        '''
                    }
                }
                stage('Security Scan') {
                    steps {
                        sh '''
                            python3 -m pip install bandit safety
                            find . -name "*.py" -not -path "*/\.*" -not -path "*/venv/*" | xargs bandit -r
                            safety check
                        '''
                    }
                }
            }
        }

        stage('Run Tests') {
            parallel {
                stage('Medecins Tests') {
                    steps {
                        dir('services/medecins') {
                            sh 'python3 -m pytest --cov=. --cov-report=xml -v --junitxml=test-results.xml'
                        }
                    }
                }
                stage('Ordonnances Tests') {
                    steps {
                        dir('services/ordonnances') {
                            sh 'python3 -m pytest --cov=. --cov-report=xml -v --junitxml=test-results.xml'
                        }
                    }
                }
                stage('Patients Tests') {
                    steps {
                        dir('services/patients') {
                            sh 'python3 -m pytest --cov=. --cov-report=xml -v --junitxml=test-results.xml'
                        }
                    }
                }
                stage('Radiologues Tests') {
                    steps {
                        dir('services/radiologues') {
                            sh 'python3 -m pytest --cov=. --cov-report=xml -v --junitxml=test-results.xml'
                        }
                    }
                }
                stage('Reports Tests') {
                    steps {
                        dir('services/reports') {
                            sh 'python3 -m pytest --cov=. --cov-report=xml -v --junitxml=test-results.xml'
                        }
                    }
                }
            }
        }

        stage('SonarQube Analysis') {
            steps {
                script {
                    def scannerHome = tool 'SonarScanner'
                    withSonarQubeEnv('SonarQube') {
                        sh "${scannerHome}/bin/sonar-scanner -Dsonar.projectVersion=${VERSION}"
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
                        sh """
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
                        sh """
                            ${DOCKER_COMPOSE} up -d consul mongodb redis rabbitmq elasticsearch kibana prometheus grafana jaeger
                            sleep 30  # Wait for infrastructure to be ready
                        """
                    }
                }
                stage('API Gateway') {
                    steps {
                        // Deploy APISIX Gateway
                        sh "${DOCKER_COMPOSE} up -d etcd apisix apisix-dashboard apisix-init"
                    }
                }
                stage('Core Services') {
                    steps {
                        script {
                            def services = ['medecins', 'ordonnances', 'patients', 'radiologues', 'reports']
                            for (service in services) {
                                sh """
                                    ${DOCKER_COMPOSE} up -d ${service}
                                    // Wait for service to register with Consul
                                    curl --retry 30 --retry-delay 2 --retry-connrefused ${CONSUL_HTTP_ADDR}/v1/health/service/${service}
                                """
                            }
                        }
                    }
                }
                stage('Monitoring Setup') {
                    steps {
                        sh """
                            ${DOCKER_COMPOSE} up -d otel-collector
                            curl -X POST -H "Content-Type: application/json" \\
                                -d @monitoring/grafana/dashboards/services-dashboard.json \\
                                http://admin:admin@grafana:3000/api/dashboards/db
                        """
                    }
                }
                stage('Health Check') {
                    steps {
                        script {
                            sh '''
                                # Check APISIX Gateway
                                curl --retry 5 --retry-delay 10 http://apisix:9180/apisix/admin/health

                                # Check all services through APISIX
                                curl --retry 5 --retry-delay 10 http://apisix:9080/api/medecins/health
                                curl --retry 5 --retry-delay 10 http://apisix:9080/api/ordonnances/health
                                curl --retry 5 --retry-delay 10 http://apisix:9080/api/patients/health
                                curl --retry 5 --retry-delay 10 http://apisix:9080/api/radiologues/health
                                curl --retry 5 --retry-delay 10 http://apisix:9080/api/reports/health
                            '''
                        }
                    }
                }
            }
        }
    }

    post {
        always {
            junit '**/test-results.xml'
            publishCoverage adapters: [coberturaAdapter('**/coverage.xml')]

            script {
                // Cleanup only if not on main branch
                if (env.BRANCH_NAME != 'main') {
                    sh "${DOCKER_COMPOSE} down --volumes --remove-orphans"
                }
            }
            cleanWs()
        }
        success {
            script {
                def message = "Pipeline for version ${VERSION} completed successfully!"
                // Add your notification logic here
            }
        }
        failure {
            script {
                def message = "Pipeline for version ${VERSION} failed! Check the logs for details."
                // Add your notification logic here
                sh '''
                    mkdir -p pipeline-logs
                    docker compose logs > pipeline-logs/docker-compose.log
                    tar -czf pipeline-logs.tar.gz pipeline-logs/
                '''
                archiveArtifacts artifacts: 'pipeline-logs.tar.gz', fingerprint: true
            }
        }
    }
}
