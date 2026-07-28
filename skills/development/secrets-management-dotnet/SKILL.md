---
name: secrets-management-dotnet
description: "Load secrets into .NET configuration safely."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [secrets, management, dotnet, development]
    category: development
    related_skills: [dotnet-apm-metrics, dotnet-otel-patterns, dotnet-async-patterns, external-secrets-aws-sm]
---
# Secrets Management — .NET at <org>

How .NET services access secrets in the <org> EKS environment.

## When to Use

Use when configuring secrets in .NET services at <org>. Covers configuration providers, AWS Secrets Manager integration, IOptions pattern, External Secrets Operator flow, hot reload, local dev with user-secrets, and anti-patterns for secret handling.

## Critical: Secret flow at <org>

```
AWS Secrets Manager → External Secrets Operator → K8s Secret → Pod env var → IConfiguration
```

Applications NEVER access AWS Secrets Manager directly in production. The External Secrets Operator syncs secrets into K8s, and pods consume them as environment variables or mounted files.

## Configuration providers (priority order)

.NET `IConfiguration` loads from multiple sources. **Last one wins**:

```csharp
var builder = WebApplication.CreateBuilder(args);
// Default order (lowest to highest priority):
// 1. appsettings.json
// 2. appsettings.{Environment}.json
// 3. User secrets (Development only)
// 4. Environment variables  ← <org> production uses this
// 5. Command-line args
```

### <org> resolution strategy

| Environment | Primary source | Fallback |
|-------------|---------------|----------|
| LOCAL | `.env` file (DotNetEnv) + user-secrets | appsettings.Development.json |
| DEV/HML/PRD/BTC | Environment variables (from K8s Secret) | None — fail fast |

## IOptions<T> pattern

### Strongly-typed configuration

```csharp
public record DatabaseOptions
{
    public const string Section = "Database";

    public required string ConnectionString { get; init; }
    public int PoolSize { get; init; } = 20;
    public int CommandTimeout { get; init; } = 30;
}

// Registration
builder.Services.Configure<DatabaseOptions>(
    builder.Configuration.GetSection(DatabaseOptions.Section));

// Usage via DI
public class OrderRepository(IOptions<DatabaseOptions> options)
{
    private readonly string _connStr = options.Value.ConnectionString;
}
```

### Validation on startup

```csharp
builder.Services.AddOptions<DatabaseOptions>()
    .BindConfiguration(DatabaseOptions.Section)
    .ValidateDataAnnotations()
    .ValidateOnStart();  // Fail fast if config invalid

public record DatabaseOptions
{
    [Required]
    public required string ConnectionString { get; init; }

    [Range(1, 100)]
    public int PoolSize { get; init; } = 20;
}
```

### IOptionsMonitor for hot reload

```csharp
// IOptionsMonitor<T> — reloads when underlying config changes
public class NotificationService(IOptionsMonitor<SmtpOptions> options)
{
    public async Task SendAsync(string to, string body)
    {
        var smtp = options.CurrentValue;  // Always latest
        await _client.SendAsync(smtp.Host, smtp.Port, to, body);
    }
}
```

Hot reload works when:
- Config file changes (appsettings.json watched by default)
- External Secrets Operator updates the K8s Secret AND pod restarts (env vars don't hot-reload)

## K8s Secret → Environment variable

### Helm values (<org> app chart)

```yaml
# values.yaml
env:
  - name: Database__ConnectionString
    valueFrom:
      secretKeyRef:
        name: myapp-secrets
        key: db-connection-string
  - name: Redis__ConnectionString
    valueFrom:
      secretKeyRef:
        name: myapp-secrets
        key: redis-url
  - name: ExternalApi__ApiKey
    valueFrom:
      secretKeyRef:
        name: myapp-secrets
        key: external-api-key
```

### ExternalSecret CRD

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: myapp-secrets
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secretsmanager
    kind: ClusterSecretStore
  target:
    name: myapp-secrets
  data:
    - secretKey: db-connection-string
      remoteRef:
        key: /myapp/prd/database
        property: connection_string
    - secretKey: redis-url
      remoteRef:
        key: /myapp/prd/redis
        property: url
    - secretKey: external-api-key
      remoteRef:
        key: /myapp/prd/external-api
        property: api_key
```

### Naming convention (env var → IConfiguration)

.NET maps `__` (double underscore) to `:` (section separator):

```
Database__ConnectionString → Configuration["Database:ConnectionString"]
```

This maps directly to `IOptions<DatabaseOptions>` when section is `"Database"`.

## Local development

### dotnet user-secrets

```bash
# Initialize (one-time per project)
docker run --rm -v $(pwd):/src -w /src mcr.microsoft.com/dotnet/sdk:8.0 \
  dotnet user-secrets init

# Set secrets
docker run --rm -v $(pwd):/src -v ~/.microsoft/usersecrets:/root/.microsoft/usersecrets \
  -w /src mcr.microsoft.com/dotnet/sdk:8.0 \
  dotnet user-secrets set "Database:ConnectionString" "Host=localhost;Database=mydb;..."
```

### .env file with DotNetEnv

For `docker compose` local development:

```csharp
// Program.cs — LOCAL only
if (builder.Environment.IsDevelopment())
{
    DotNetEnv.Env.Load();  // Loads .env into Environment
}
```

```env
# .env (gitignored!)
Database__ConnectionString=Host=localhost;Database=mydb;Username=dev;Password=dev123
Redis__ConnectionString=localhost:6379
ExternalApi__ApiKey=dev-test-key-not-real
SERVICE_NAME=myapp
ENVIRONMENT=LOCAL
```

### .env.example (committed to git)

```env
# .env.example — template for developers
Database__ConnectionString=Host=localhost;Database=mydb;Username=dev;Password=CHANGE_ME
Redis__ConnectionString=localhost:6379
ExternalApi__ApiKey=YOUR_API_KEY_HERE
SERVICE_NAME=myapp
ENVIRONMENT=LOCAL
```

## Secret masking in logs

### Never log secret values

```csharp
// ❌ NEVER
_logger.LogInformation("Connecting with: {ConnStr}", options.Value.ConnectionString);

// ✅ Log key name, not value
_logger.LogInformation("Connecting to database using secret 'Database:ConnectionString'");
```

### [Sensitive] attribute pattern (custom)

```csharp
[AttributeUsage(AttributeTargets.Property)]
public class SensitiveAttribute : Attribute { }

public record DatabaseOptions
{
    [Sensitive]
    public required string ConnectionString { get; init; }

    public int PoolSize { get; init; } = 20;

    public override string ToString()
    {
        return $"DatabaseOptions {{ PoolSize={PoolSize}, ConnectionString=*** }}";
    }
}
```

### Structured logging — exclude secrets

```csharp
// When using ILogger with structured logging, never pass secrets as parameters
_logger.LogInformation("Database pool configured: {PoolSize} connections", options.Value.PoolSize);
// NOT: _logger.LogInformation("Config: {@Options}", options.Value);  // Leaks ConnectionString!
```

## Secret rotation

### Flow at <org>

```
1. Rotate secret in AWS Secrets Manager
2. External Secrets Operator detects change (refreshInterval: 1h)
3. K8s Secret updated
4. Pod restart required (env vars don't hot-reload)
```

### Triggering pod restart on secret change

Option A: Annotation hash (Helm chart handles this):
```yaml
spec:
  template:
    metadata:
      annotations:
        checksum/secrets: {{ include (print $.Template.BasePath "/externalsecret.yaml") . | sha256sum }}
```

Option B: Stakater Reloader (watches Secret changes, triggers rollout restart).

### For file-mounted secrets (hot reload without restart)

```yaml
# Mount as volume instead of env var
volumes:
  - name: secrets
    secret:
      secretName: myapp-secrets
volumeMounts:
  - name: secrets
    mountPath: /etc/secrets
    readOnly: true
```

```csharp
builder.Configuration.AddKeyPerFile("/etc/secrets", optional: true, reloadOnChange: true);
```

## <org> helper patterns

### Connection string builder with validation

```csharp
public static class ConnectionStringValidator
{
    public static string GetValidated(IConfiguration config, string key)
    {
        var value = config[key]
            ?? throw new InvalidOperationException($"Missing required config: {key}");

        if (value.Contains("CHANGE_ME") || value.Contains("YOUR_"))
            throw new InvalidOperationException($"Config '{key}' contains placeholder value");

        return value;
    }
}
```

### Health check for secret availability

```csharp
public class SecretsHealthCheck(IOptions<DatabaseOptions> dbOpts) : IHealthCheck
{
    public Task<HealthCheckResult> CheckHealthAsync(
        HealthCheckContext context, CancellationToken ct = default)
    {
        try
        {
            _ = dbOpts.Value.ConnectionString;
            return Task.FromResult(HealthCheckResult.Healthy());
        }
        catch (OptionsValidationException ex)
        {
            return Task.FromResult(HealthCheckResult.Unhealthy(ex.Message));
        }
    }
}
```

## Anti-patterns

### ❌ Hardcoded secrets in code

```csharp
// ❌ NEVER — visible in git, Docker layers, decompiled assemblies
var connStr = "Host=prod-db.internal;Password=SuperSecret123!";

// ✅ From configuration (env var in production)
var connStr = config["Database:ConnectionString"];
```

### ❌ Secrets in ConfigMap or Helm values

```yaml
# ❌ ConfigMaps are not encrypted at rest, visible to anyone with namespace access
apiVersion: v1
kind: ConfigMap
data:
  DB_PASSWORD: "my-secret-password"

# ✅ Use ExternalSecret → K8s Secret
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
```

### ❌ Logging secret values

```csharp
// ❌ Appears in Loki, accessible to anyone with log access
_logger.LogDebug("API Key: {Key}", apiKey);
_logger.LogInformation("Full config: {@Config}", config);  // May contain secrets

// ✅ Reference by name
_logger.LogDebug("Using API key from config 'ExternalApi:ApiKey'");
```

### ❌ Secrets as Docker build args

```dockerfile
# ❌ Visible in image layers (docker history)
ARG DB_PASSWORD
ENV Database__ConnectionString="Host=db;Password=${DB_PASSWORD}"

# ✅ Inject at runtime via K8s Secret → env var
```

### ❌ Committing .env files

```gitignore
# .gitignore — MUST include
.env
*.env.local
```

### ❌ Direct AWS Secrets Manager calls from app code in production

```csharp
// ❌ Adds AWS SDK dependency, IAM complexity, latency on startup
var client = new AmazonSecretsManagerClient();
var secret = await client.GetSecretValueAsync(new GetSecretValueRequest { SecretId = "myapp/db" });

// ✅ Let External Secrets Operator handle it — app just reads env vars
var connStr = Environment.GetEnvironmentVariable("Database__ConnectionString");
```

Exception: CLI tools or one-off scripts that run outside K8s may access Secrets Manager directly.

### ❌ Using IOptions<T> without ValidateOnStart

```csharp
// ❌ Missing config discovered only when first request hits the code path
builder.Services.Configure<DatabaseOptions>(config.GetSection("Database"));

// ✅ Fail fast on startup
builder.Services.AddOptions<DatabaseOptions>()
    .BindConfiguration("Database")
    .ValidateDataAnnotations()
    .ValidateOnStart();
```

## Reference

- <org> sample: `otel-telemetry-helper/dotnet/example/dotnet-api/`
- Related steering: `cloud-security.md` (secrets management section)
- Related skill: `external-secrets-aws-sm` (ESO configuration)
- Related skill: `helm-chart-app` (env/secret injection in Helm)
- Steering: `dev-environment.md` (all builds via Docker)
