# MedApp - Medical Imaging Analysis Platform

A microservices-based platform for medical imaging analysis, focusing on X-ray interpretation and medical imaging management.

## Architecture Overview

The platform consists of several microservices:

### Core Services

- **Consul** (Port: 8500): Service discovery and registration
- **Mobile Gateway** (Port: 5000): API gateway for mobile/web clients
- **X-Ray Service** (Port: 8081): Handles X-ray image analysis and reporting

### Infrastructure Services

- **MongoDB** (Port: 27017): Primary database for storing medical records and analysis results
- **RabbitMQ** (Ports: 5672, 15672): Message broker for asynchronous communication between services
- **Redis** (Port: 6379): Caching layer for improved performance

### Monitoring

- **Prometheus** (Port: 9090): Metrics collection and storage
- **Grafana** (Port: 3000): Visualization and monitoring dashboards

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Git
- Flutter SDK (for frontend development)

### Environment Setup

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd medapp
   ```

2. Create a `.env` file in the root directory with the following variables:

   ```env
   # MongoDB
   MONGODB_USERNAME=admin
   MONGODB_PASSWORD=admin
   MONGODB_DATABASE=medapp

   # RabbitMQ
   RABBITMQ_USER=guest
   RABBITMQ_PASS=guest

   # Redis
   REDIS_PASSWORD=

   # Grafana
   GRAFANA_USER=admin
   GRAFANA_PASSWORD=admin
   ```

### Running the Platform

1. Start all services:

   ```bash
   docker-compose up -d
   ```

2. Monitor service health:

   ```bash
   docker-compose ps
   ```

3. Access service endpoints:
   - Consul UI: http://localhost:8500
   - Mobile Gateway: http://localhost:5000
   - RabbitMQ Management: http://localhost:15672
   - Grafana: http://localhost:3000
   - Prometheus: http://localhost:9090

### Development Setup

#### X-Ray Service Development

```bash
cd backend/services/xray
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
python main.py
```

#### Frontend Development

```bash
cd frontend
flutter pub get
flutter run -d chrome --web-port 8888
```

## Service Details

### X-Ray Service

- Analyzes chest X-ray images using computer vision and ML techniques
- Provides detailed analysis reports with findings and suggestions
- Stores analysis history in MongoDB
- Publishes analysis events to RabbitMQ

### Mobile Gateway

- Routes requests to appropriate microservices
- Handles service discovery and load balancing
- Provides unified API for mobile/web clients
- Implements circuit breakers for fault tolerance
- Caches responses using Redis

## API Documentation

### X-Ray Service Endpoints

- `POST /analyze`: Analyze X-ray image
- `GET /history/<patient_id>`: Get patient's analysis history

## Service Integration

The MedApp platform incorporates comprehensive service integration to enable seamless communication between microservices. This section describes the integration capabilities.

### Integration Routes

Each service exposes dedicated integration routes under the `/api/integration` path that facilitate service-to-service communication. These routes are:

- **Médecins Service**:
  - `/api/integration/request-radiology`: Request radiology examinations for patients
  - `/api/integration/patient-history/{patient_id}`: Retrieve a patient's medical history
  - `/api/integration/notify-patient/{patient_id}`: Send notifications to patients

- **Patients Service**:
  - `/api/integration/request-appointment`: Request appointments with doctors
  - `/api/integration/medical-history`: Retrieve patient's complete medical history
  - `/api/integration/prescriptions`: Retrieve patient's prescriptions

- **Radiologues Service**:
  - `/api/integration/accept-examination`: Accept radiology examination requests
  - `/api/integration/submit-report`: Submit radiology reports
  - `/api/integration/examination-requests`: Get examination requests

- **Ordonnances Service**:
  - `/api/integration/create-prescription`: Create new prescriptions
  - `/api/integration/update-prescription-status/{prescription_id}`: Update prescription status
  - `/api/integration/doctor-prescriptions`: Get doctor's prescriptions

- **Reports Service**:
  - `/api/integration/analyze-report`: Queue a report for analysis
  - `/api/integration/report-analysis/{report_id}`: Retrieve analysis results
  - `/api/integration/create-analysis-summary`: Generate summary from multiple reports

- **Auth Service**:
  - `/api/integration/verify-service`: Verify service identity for service-to-service auth
  - `/api/integration/user-roles/{user_id}`: Get user roles (admin only)

### Message-Based Integration

Services communicate asynchronously using RabbitMQ message queues. Each service has:

1. **Producer**: Publishes events/messages to appropriate exchanges
2. **Consumer**: Subscribes to relevant queues and processes incoming messages

Key message exchanges:

- `medical.events`: General medical events across the platform
- `medical.appointments`: Appointment-related messages
- `medical.prescriptions`: Prescription-related messages
- `medical.reports`: Radiology and medical report messages
- `medical.commands`: Direct command messages between services

### Testing Integration

To test the integration between services, use the included test script:

```bash
python test_integration.py --username admin@example.com --password adminpassword
```

You can also test specific services:

```bash
python test_integration.py --username admin@example.com --password adminpassword --services medecins radiologues
```

## Monitoring and Observability

### Metrics Collection

- Service-level metrics via Prometheus
- Business metrics for analysis counts and success rates
- Infrastructure metrics for resource usage

### Grafana Dashboards

- Service health overview
- Analysis throughput and latency
- Infrastructure resource utilization

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
