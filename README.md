# SmartLab Health Monitoring

## Environment Setup

1. Copy the `.env.example` file to create your own local `.env` file:
```bash
cp .env.example .env
```
2. Open the `.env` file and replace the placeholder values with your actual database and application credentials. Do not commit this file to version control.
3. Once the environment variables are set, you can start the application using Docker Compose:
```bash
docker-compose up -d --build
```
