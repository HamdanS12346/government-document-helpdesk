# Technical Specification: Containerization & Docker Topology

## 1. Executive Summary & Core Objectives

### 1.1 Purpose
The **Government Document Helpdesk** is a multi-tier AI system consisting of an asynchronous FastAPI backend (running LangGraph, OCR image/PDF parsing, hybrid RAG, and safety guardrails), a Next.js 16 frontend (with SSR, Google OAuth, and Supabase auth), and managed cloud databases (Chroma Cloud for vector retrieval, Supabase for auth/session persistence).

Currently, running the system locally requires manual orchestration across separate terminal sessions:
1. Native Windows Python virtual environment requiring local system binaries (`tesseract-ocr`).
2. Node.js runtime for Next.js (`npm run dev`).

### 1.2 Objectives
This specification defines the containerization strategy for the project. It provides:
1. **Zero-Setup Portability**: Package complex system binaries (Tesseract OCR, Poppler, C++ libraries) directly into Linux containers, eliminating host-OS installation requirements.
2. **Clean 2-Service Architecture**: Strictly focused on the two core application components: **Backend** (FastAPI) and **Frontend** (Next.js 16).
3. **Cloud-Native Database Model**: Relies entirely on managed cloud services (**Chroma Cloud** for vector embeddings/retrieval and **Supabase Cloud** for auth and multi-turn memory), eliminating the need for local database container management.
4. **Internal Reverse Proxying**: Dynamic internal routing (`INTERNAL_API_URL=http://backend:8000`) preventing container isolation issues across Docker bridge networks.

---

## 2. Container Topology & Architecture

```mermaid
flowchart TD
    subgraph Host ["Host Machine"]
        Browser["Citizen Browser\n(http://localhost:3000)"]
    end

    subgraph DockerNetwork ["Docker Bridge Network (helpdesk-network)"]
        
        subgraph FrontendService ["Frontend Container (helpdesk-frontend)"]
            NextServer["Next.js 16 Server\n(Port 3000)"]
            InternalProxy["Next.js Reverse Proxy (/api/py/*)\n-> http://backend:8000"]
        end

        subgraph BackendService ["Backend Container (helpdesk-backend)"]
            FastAPI["Uvicorn / FastAPI\n(Port 8000)"]
            TesseractOCR["Tesseract 5.x Engine\n(System Binary + eng/hin)"]
            LangGraph["LangGraph Workflow\n(Input -> Intent -> RAG -> Response)"]
            Guardrails["Safety & Redaction Guardrails"]
        end
    end

    subgraph ExternalCloud ["External Managed Cloud Services (via .env)"]
        ChromaCloudDB[("Chroma Cloud (Managed Vector DB)")]
        SupabaseCloud[("Supabase Cloud (PostgreSQL & Auth)")]
        OpenAIAPI["OpenAI API (GPT-4o-mini & Embeddings)"]
        CohereAPI["Cohere API (Cross-Encoder Reranker)"]
    end

    Browser -->|HTTP :3000| NextServer
    NextServer --> InternalProxy
    InternalProxy -->|Internal DNS: http://backend:8000| FastAPI
    
    FastAPI --> TesseractOCR
    FastAPI --> LangGraph
    LangGraph --> Guardrails

    LangGraph -->|Dense Semantic Search| ChromaCloudDB
    FastAPI -->|User Auth & Thread History| SupabaseCloud
    LangGraph -->|LLM & Query Embeddings| OpenAIAPI
    LangGraph -->|Document Reranking| CohereAPI
```

---

## 3. Architecture Modes

| Mode | Best Suited For | Backend | Frontend | Cloud Services |
| :--- | :--- | :--- | :--- | :--- |
| **Production Mode** *(Default)* | Testing the full optimized build | Containerized FastAPI (Python 3.11) | Containerized Next.js 16 (Multi-stage build) | Chroma Cloud + Supabase Cloud |
| **Development Mode** | Rapid local feature iteration with live code sync | FastAPI (`--reload` + Volume Bind Mount) | Next.js (`npm run dev` + Volume Bind Mount) | Chroma Cloud + Supabase Cloud |

---

## 4. Container Specifications & Dockerfiles

### 4.1 Backend Service (`Dockerfile`)

The backend container packages Python 3.11 with Linux C-libraries for PDF rendering (`poppler`), image manipulation (`libgl1`, `libglib2.0`), and optical character recognition (`tesseract-ocr`).

```dockerfile
# Root: Dockerfile
FROM python:3.11-slim AS base

# 1. Environment configuration
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata/

# 2. Install essential system dependencies and OCR libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-hin \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 3. Cache Python dependencies in separate layer
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. Copy application source code
COPY app/ ./app/
COPY guardrails/ ./guardrails/

# 5. Create non-root user for security compliance
RUN useradd -m -u 1001 helpdesk && \
    chown -R helpdesk:helpdesk /app
USER helpdesk

EXPOSE 8000

# 6. Healthcheck endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

# 7. Start Uvicorn bound to 0.0.0.0
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

### 4.2 Frontend Service (`frontend/Dockerfile` — Production)

Next.js 16 multi-stage build to minimize the final image size (< 150MB) and isolate build-time dependencies:

```dockerfile
# frontend/Dockerfile
# ---------------------------------------------------------------------------
# Stage 1: Install Dependencies
# ---------------------------------------------------------------------------
FROM node:20-alpine AS deps
WORKDIR /app
RUN apk add --no-cache libc6-compat
COPY package.json package-lock.json ./
RUN npm ci

# ---------------------------------------------------------------------------
# Stage 2: Build Application
# ---------------------------------------------------------------------------
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build arguments for public client environment variables
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ARG NEXT_PUBLIC_API_URL

ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL \
    NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY \
    NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NODE_ENV=production

RUN npm run build

# ---------------------------------------------------------------------------
# Stage 3: Production Runner
# ---------------------------------------------------------------------------
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME="0.0.0.0"

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy static assets and built distribution
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.ts ./next.config.ts

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/ || exit 1

CMD ["npm", "start"]
```

---

### 4.3 Frontend Development Container (`frontend/Dockerfile.dev`)

For active frontend code editing without rebuilding images on every save:

```dockerfile
# frontend/Dockerfile.dev
FROM node:20-alpine
WORKDIR /app
RUN apk add --no-cache libc6-compat
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev"]
```

---

## 5. Master Docker Compose Orchestration (`docker-compose.yml`)

The root `docker-compose.yml` configures the clean two-tier application stack:

```yaml
version: '3.8'

networks:
  helpdesk-network:
    driver: bridge

services:
  # =========================================================================
  # 1. FastAPI Backend Service
  # =========================================================================
  backend:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: helpdesk-backend
    restart: unless-stopped
    env_file:
      - .env
    ports:
      - "8000:8000"
    networks:
      - helpdesk-network

  # =========================================================================
  # 2. Next.js Frontend Service
  # =========================================================================
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        NEXT_PUBLIC_SUPABASE_URL: ${NEXT_PUBLIC_SUPABASE_URL}
        NEXT_PUBLIC_SUPABASE_ANON_KEY: ${NEXT_PUBLIC_SUPABASE_ANON_KEY}
    container_name: helpdesk-frontend
    restart: unless-stopped
    environment:
      - INTERNAL_API_URL=http://backend:8000
    ports:
      - "3000:3000"
    depends_on:
      - backend
    networks:
      - helpdesk-network
```

---

## 6. Networking & Ingress Resolution

### 6.1 The Container Isolation Challenge
Inside Docker, `127.0.0.1` and `localhost` resolve strictly to the **isolated container itself**. 
- The frontend container cannot proxy requests to `http://localhost:8000` because the backend runs in a separate container.
- When accessed via browser, requests to `/api/py/chat` hit Next.js on port 3000. Next.js must proxy that request to `http://backend:8000` using Docker's internal DNS.

### 6.2 Solution: Parameterized Next.js Proxy Rewrite
In [`frontend/next.config.ts`](file:///C:/Users/AdarshShrikrishnaNai/Desktop/government-document-helpdesk/frontend/next.config.ts):

```typescript
import type { NextConfig } from "next";

// On host machine defaults to 127.0.0.1; in Docker Compose uses http://backend:8000
const INTERNAL_API_URL = process.env.INTERNAL_API_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/py/:path*",
        destination: `${INTERNAL_API_URL}/:path*`,
      },
    ];
  },
};

export default nextConfig;
```

This single configuration ensures zero code changes whether running bare-metal on your host machine or inside Docker Compose.

---

## 7. Storage & Volumes Matrix

Because **ChromaDB** and **Supabase** are managed in the cloud, there are **no persistent database volumes** required to manage on your local machine:

| Volume / Path | Type | Purpose | Lifecycle |
| :--- | :--- | :--- | :--- |
| `/tmp` | Ephemeral (tmpfs) | Staging area for temporary PDF page extraction and uploaded image OCR. | Automatically cleared by Linux when container restarts. |

---

## 8. Environment Variables & Secret Handling

A `.dockerignore` file prevents local credential and cache leaks:

```text
# .dockerignore
.venv/
__pycache__/
*.pyc
*.pyo
.git/
.env.local
node_modules/
.next/
*.log
scratch/
```

### Required `.env` Keys for Container Launch:
```env
# OpenAI & Cohere LLM Services
OPENAI_API_KEY=sk-...
COHERE_API_KEY=...

# Supabase Auth & PostgreSQL Cloud
SUPABASE_URL=https://<project-id>.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_JWT_SECRET=...

# Chroma Vector Store (Chroma Cloud SaaS)
CHROMA_TENANT=...
CHROMA_DATABASE=...
CHROMA_API_KEY=...

# Langfuse Observability (Optional)
LANGFUSE_ENABLED=false
```

---

## 9. Operation & Deployment Runbook

### 9.1 Standard Startup (Production Build)
Builds and starts both Backend and Frontend:
```bash
docker compose up --build -d
```

### 9.2 Development Mode with Live Code Sync
Using `docker-compose.override.yml` to bind-mount source code for live hot-reloading:
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

### 9.3 Verifying Container Status & Health
```bash
# Check running containers and health statuses
docker compose ps

# View real-time logs across services
docker compose logs -f

# Run backend unit & integration tests inside Docker
docker compose exec backend pytest
```

### 9.4 Graceful Teardown
```bash
# Stop containers
docker compose down
```

---

## 10. Verification & Test Plan

1. **OCR Verification Inside Container**:
   - Execute `docker compose exec backend tesseract --version` to ensure Tesseract 5.x is active.
   - Upload a sample Indian government ID image; verify OCR extracts text cleanly without `TesseractNotFoundError`.
2. **Chroma Cloud Connectivity**:
   - Verify `backend` container can reach Chroma Cloud over HTTPS without network proxy errors.
3. **Internal Proxy & Rewrite Test**:
   - Send `POST http://localhost:3000/api/py/chat`; confirm Next.js proxies to `http://backend:8000/chat` and returns `200 OK`.
4. **Automated Test Suite**:
   - Run `docker compose exec backend pytest` to verify all 761 tests pass inside the Linux container environment.
