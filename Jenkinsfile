pipeline {
    agent any

    environment {
        DOCKER_COMPOSE = 'docker compose'
        SONAR_HOST_URL = 'http://sonarqube:9000'
    }

    tools {
        // Define Python tool installation
        python 'Python3'
    }

    stages {
        stage('Setup Tools') {
            steps {
                script {
                    // Install pip and upgrade it
                    sh '''
                        curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
                        python3 get-pip.py --user
                        python3 -m pip install --upgrade pip
                    '''
                    
                    // Install Docker Compose if not present
                    sh '''
                        if ! command -v docker compose &> /dev/null; then
                            curl -L "https://github.com/docker/compose/releases/download/v2.24.5/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
                            chmod +x /usr/local/bin/docker-compose
                        fi
                    '''
                }
            }
        }

        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Install Dependencies') {
            steps {
                script {
                    // Install dependencies for each service
                    sh '''
                        python3 -m pip install --user pytest pytest-cov
                        cd services/medecins && python3 -m pip install -r requirements.txt
                        cd ../ordonnances && python3 -m pip install -r requirements.txt
                        cd ../patients && python3 -m pip install -r requirements.txt
                        cd ../radiologues && python3 -m pip install -r requirements.txt
                        cd ../reports && python3 -m pip install -r requirements.txt
                    '''
                }
            }
        }

        stage('Run Tests') {
            steps {
                script {
                    // Run tests for each service and generate coverage reports
                    sh '''
                        cd services/medecins && python3 -m pytest --cov=. --cov-report=xml -v
                        cd ../ordonnances && python3 -m pytest --cov=. --cov-report=xml -v
                        cd ../patients && python3 -m pytest --cov=. --cov-report=xml -v
                        cd ../radiologues && python3 -m pytest --cov=. --cov-report=xml -v
                        cd ../reports && python3 -m pytest --cov=. --cov-report=xml -v
                    '''
                }
            }
        }

        stage('SonarQube Analysis') {
            steps {
                script {
                    def scannerHome = tool 'SonarScanner'
                    withSonarQubeEnv('SonarQube') {
                        sh "${scannerHome}/bin/sonar-scanner"
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

        stage('Build Docker Images') {
            steps {
                script {
                    sh 'docker compose build'
                }
            }
        }

        stage('Deploy') {
            when {
                branch 'main'
            }
            steps {
                script {
                    sh 'docker compose up -d'
                }
            }
        }
    }

    post {
        always {
            // Clean up
            sh 'docker compose down || true'
            cleanWs()
        }
        success {
            echo 'Pipeline completed successfully!'
        }
        failure {
            echo 'Pipeline failed! Check the logs for details.'
        }
    }
}