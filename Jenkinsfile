pipeline {
    agent any

    parameters {
        choice(name: 'SERVICES', choices: ['annuity-services', 'digtran-services', 'document-services', 'garwin-services', 'lifecad-services', 'generic-internal-service', 'portal-services', 'garwin-int-apps'], description: 'Select parent service group')
        choice(name: 'build_services', choices: ['document-engine'], description: 'Select specific service')
        choice(name: 'ENVIRONMENT', choices: ['dev', 'devb', 'devc'], description: 'Choose environment to deploy')
        booleanParam(name: 'INTERNAL_BUILD', defaultValue: true, description: 'Trigger internal image build')
        booleanParam(name: 'TRIGGER_DEPLOY', defaultValue: true, description: 'Trigger deployment step')
    }

    environment {
        RHEL_VERSION = 'tomcat-rhel8'
        BASE_IMAGE_TAG = '6.0.5-3.17'  // can also use a dynamic active choice
    }

    stages {

        stage('Package Build Job') {
            steps {
                script {
                    def pkgBuild = build job: 'BAS/MicroServices/microservice_package_build',
                        parameters: [
                            string(name: 'SERVICES', value: params.SERVICES),
                            string(name: 'build_services', value: params.build_services),
                            booleanParam(name: 'INTERNAL_BUILD', value: params.INTERNAL_BUILD)
                        ],
                        wait: true

                    env.BUILD_NUMBER_TAG = pkgBuild.getNumber().toString()
                    echo "Package Build Completed. BUILD_NUMBER_TAG: ${env.BUILD_NUMBER_TAG}"
                }
            }
        }

        stage('Image Build Job') {
            when {
                expression { return params.INTERNAL_BUILD }
            }
            steps {
                script {
                    build job: '/Shared/EKS/bas-microservices-build',
                        parameters: [
                            string(name: 'SERVICES', value: params.SERVICES),
                            string(name: 'IMAGE_NAME', value: params.build_services),
                            string(name: 'RHEL_VERSION', value: env.RHEL_VERSION),
                            string(name: 'BASE_IMAGE_TAG', value: env.BASE_IMAGE_TAG),
                            string(name: 'BUILD_NUMBER', value: env.BUILD_NUMBER_TAG),
                            booleanParam(name: 'IS_LATEST', value: true)
                        ],
                        wait: true
                }
            }
        }

        stage('Deploy Microservice') {
            when {
                expression { return params.TRIGGER_DEPLOY }
            }
            steps {
                script {
                    build job: "Shared/EKS/deploy-job-${params.ENVIRONMENT}",
                        parameters: [
                            string(name: 'IMAGE_TAG', value: "${env.BASE_IMAGE_TAG}-${env.BUILD_NUMBER_TAG}"),
                            string(name: 'ENVIRONMENT', value: params.ENVIRONMENT),
                            string(name: 'SERVICE_NAME', value: params.build_services)
                        ],
                        wait: false
                }
            }
        }
    }

    post {
        success {
            echo "Pipeline completed successfully."
        }
        failure {
            echo "Pipeline failed. Check logs."
        }
    }
}
