# Multi-stage Dockerfile Template
# Principle: build dependencies never reach the final image

# ─── Stage 1: Build ───────────────────────────────────────────
FROM golang:1.25-alpine AS builder
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download                  # cached unless deps change
COPY . .
RUN CGO_ENABLED=0 GOARCH=${TARGETARCH:-amd64} \
    go build -ldflags="-s -w" -o /app ./cmd/server/

# ─── Stage 2: Runtime ─────────────────────────────────────────
FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=builder /app /app
USER 65534:65534
EXPOSE 8080
ENTRYPOINT ["/app"]

# ═══════════════════════════════════════════════════════════════
# VARIANTS
# ═══════════════════════════════════════════════════════════════

# --- .NET variant ---
# FROM mcr.microsoft.com/dotnet/sdk:8.0-alpine AS build
# WORKDIR /src
# COPY *.csproj ./
# RUN dotnet restore
# COPY . .
# RUN dotnet publish -c Release -o /out --no-restore
#
# FROM mcr.microsoft.com/dotnet/aspnet:8.0-alpine
# WORKDIR /app
# COPY --from=build /out .
# USER 65534
# ENTRYPOINT ["dotnet", "MyApp.dll"]

# --- Python variant ---
# FROM python:3.11-slim AS builder
# WORKDIR /app
# COPY requirements.txt .
# RUN pip install --prefix=/install --no-cache-dir -r requirements.txt
#
# FROM python:3.11-slim
# COPY --from=builder /install /usr/local
# WORKDIR /app
# COPY src/ ./src/
# USER 65534
# CMD ["python", "-m", "src.main"]

# --- Node variant ---
# FROM node:20-slim AS builder
# WORKDIR /app
# COPY package*.json ./
# RUN npm ci --omit=dev
# COPY . .
# RUN npm run build
#
# FROM node:20-slim
# WORKDIR /app
# COPY --from=builder /app/node_modules ./node_modules
# COPY --from=builder /app/dist ./dist
# USER 65534
# CMD ["node", "dist/index.js"]
