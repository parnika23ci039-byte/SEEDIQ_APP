# SeedIQ — AI-Powered Smart Agriculture Platform

SeedIQ is an AI-powered agriculture platform designed to help farmers and agricultural stakeholders make informed decisions through crop-related insights, yield prediction, seed viability analysis, weather information, and intelligent agricultural tools.

The project combines a web frontend, an Android mobile application, and a backend API to provide access to agricultural features through a unified platform.

## Key Features

- **Yield AI:** Provides crop-yield predictions and agricultural insights.
- **Seed AI:** Supports seed viability assessment and seed-related analysis.
- **Quantum ML:** Provides access to the project's experimental quantum-inspired machine-learning functionality.
- **Crop Information:** Displays crop-related information and visual assets.
- **Weather Information:** Presents weather data to support agricultural decision-making.
- **Storage AI:** Provides agricultural storage-related functionality.
- **Model Metrics:** Exposes model-performance information through the backend API.
- **Android Application:** Makes SeedIQ features accessible through a mobile interface.

*Feature availability and results depend on backend configuration, model availability, external services, and deployment status.*

## Technology Stack

The project includes:

- **Frontend:** Vite-based web application
- **Mobile:** React Native and Expo
- **Backend:** Python and Flask
- **Machine Learning:** Scikit-learn and related ML components
- **Deployment:** Vercel for the frontend and Railway for the backend
- **Agricultural Data:** Crop assets and agricultural model inputs

## Project Structure

```text
SeedIQ/
├── seediq-frontend/   # Web application and public crop assets
├── seediq-mobile/     # Android/mobile application
├── app.py             # Backend entry point, if located at repository root
└── deliverables/      # Local release artifacts, when included
```

Directory locations may vary depending on the checked-out repository version.

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/parnika23ci039-byte/SEEDIQ_APP.git
cd SEEDIQ_APP
```

### 2. Set up the frontend

```bash
cd seediq-frontend
npm install
```

Configure the API base URL using the environment variable supported by the frontend:

```env
VITE_API_BASE_URL=https://sublime-ambition-production-488f.up.railway.app
```

Use the variable name expected by the actual frontend source if it differs from this example.

Start the development server:

```bash
npm run dev
```

Create a production build:

```bash
npm run build
```

### 3. Set up the mobile application

```bash
cd ../seediq-mobile
npm install
npx tsc --noEmit
```

The TypeScript check verifies type consistency; it does not replace a complete Android build or physical-device test.

To run the application using Expo, follow the project's configured scripts and Expo SDK requirements.

## Backend API

The deployed backend is configured at:

**Base URL:** `https://sublime-ambition-production-488f.up.railway.app`

Health check:

```bash
curl -i https://sublime-ambition-production-488f.up.railway.app/api/health
```

Model metrics:

```bash
curl -i https://sublime-ambition-production-488f.up.railway.app/api/model_metrics
```

The backend may require authentication or additional configuration for particular endpoints.

## Environment Configuration

Configure API endpoints and service credentials through environment variables or the relevant hosting platform's secret settings.

- Do not commit `.env` files containing secrets.
- Never publish private API keys, service-role keys, signing credentials, or keystore passwords.
- Keep production credentials separate from development configuration.
- Configure SMS/OTP credentials privately when phone authentication is enabled.

## Deployment

### Frontend

The frontend can be deployed to Vercel after configuring the required environment variables and confirming that the deployment uses the intended project and repository.

The Vercel API rewrite should route `/api/*` requests to the configured Railway backend.

### Backend

The backend is configured for Railway deployment. Confirm that required environment variables, database connectivity, model files, and external service credentials are available in the production environment.

### Android

Build the Android application using the project's configured Expo/EAS or native Android workflow.

**Important:** Preserve the intended application ID when creating updates. The existing release APK uses `ai.seediq.mobile`, while the current local Expo configuration declares `ai.seediq.mobile.client`. Confirm the intended ID before generating an update build.

## Testing and Verification

The following checks have previously been reported for the project:

- Frontend production build completed successfully.
- Mobile TypeScript validation completed successfully.
- An OTP error-handling test passed.
- The Railway health and model-metrics endpoints returned successful responses.
- Crop assets were published to the repository.

These checks do not establish that every feature works on every device. Physical Android installation, live SMS delivery, authentication, and complete end-to-end production workflows should be verified separately.

## Security

- Keep production credentials private.
- Use authenticated endpoints for protected operations.
- Validate user input and API responses.
- Avoid exposing personal or agricultural data unnecessarily.
- Verify authentication, authorization, and transport security before production use.

## Project Status

SeedIQ includes web, mobile, backend, and agricultural AI components. Development and deployment verification should be tracked separately for each component. Experimental ML functionality and external integrations should be described according to their verified implementation and actual production behavior.

## License

Contact and Authorization

Requests for repository access, collaboration, licensing, or other permitted use must be directed to the project owner through an established, authorized communication channel.

SeedIQ — Private Project. Confidential Materials. Authorized Access Only.
