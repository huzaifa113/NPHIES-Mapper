pipeline {
    agent any

    environment {
        // GitHub token stored in Jenkins credentials
        GITHUB_TOKEN = credentials('GITHUB_PERSONAL_TOKEN')
        GIT_USER = "huzaifa113"
        GIT_EMAIL = "your-email@example.com"
    }

    stages {
        stage('Checkout Code') {
            steps {
                checkout([$class: 'GitSCM',
                    branches: [[name: '*/dev']],
                    userRemoteConfigs: [[
                        url: 'https://github.com/huzaifa113/NPHIES-Mapper.git',
                        credentialsId: 'GITHUB_PERSONAL_TOKEN'
                    ]]
                ])
            }
        }

        stage('Setup Python') {
            steps {
                sh """
                python3 -m venv venv
                . venv/bin/activate
                pip install --upgrade pip
                pip install -r requirements.txt
                """
            }
        }

        stage('Run Tests') {
            steps {
                sh """
                . venv/bin/activate
                pytest -q
                """
            }
        }

        stage('Merge to Main if Tests Pass') {
            steps {
                sh """
                git config --global user.email "${GIT_EMAIL}"
                git config --global user.name "${GIT_USER}"

                git checkout main
                git pull origin main

                git merge dev --no-ff --no-edit

                git push https://${GITHUB_TOKEN}@github.com/huzaifa113/NPHIES-Mapper.git main
                """
            }
        }
    }

    post {
        failure {
            echo "Tests failed — merge aborted."
        }
        success {
            echo "Tests passed — code deployed to MAIN."
        }
    }
}
