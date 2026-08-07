# Mermaid Diagram Examples

Copy-paste ready. Wrap in triple-backtick `mermaid` fences in Markdown.

---

## Flowchart (most common)

```mermaid
flowchart LR
    A[User Request] --> B{Auth Valid?}
    B -->|Yes| C[Process Request]
    B -->|No| D[401 Unauthorized]
    C --> E[Return Response]
```

## Sequence Diagram (API calls, request flows)

```mermaid
sequenceDiagram
    participant Client
    participant Gateway
    participant Service
    participant DB

    Client->>Gateway: POST /api/orders
    Gateway->>Service: Forward (+ trace context)
    Service->>DB: INSERT order
    DB-->>Service: OK
    Service-->>Gateway: 201 Created
    Gateway-->>Client: 201 + order_id
```

## Architecture (C4-ish containers)

```mermaid
flowchart TB
    subgraph EKS["EKS Cluster"]
        subgraph NS1["payments namespace"]
            API[Payment API]
            Worker[Payment Worker]
        end
        subgraph NS2["monitoring namespace"]
            Collector[OTel Collector]
            VM[VictoriaMetrics]
        end
    end

    Client([Client]) --> API
    API --> Worker
    Worker --> RDS[(RDS PostgreSQL)]
    API --> Collector
    Worker --> Collector
    Collector --> VM
```

## State Diagram (lifecycle)

```mermaid
stateDiagram-v2
    [*] --> Pending
    Pending --> Running: Scheduled
    Running --> Succeeded: Exit 0
    Running --> Failed: Exit != 0
    Running --> Running: Restart (CrashLoopBackOff)
    Failed --> [*]
    Succeeded --> [*]
```

## Deployment Pipeline

```mermaid
flowchart LR
    subgraph CI["GitLab CI"]
        Lint --> Test --> Build --> Push
    end

    subgraph CD["ArgoCD"]
        Sync --> Health
    end

    Push -->|Image tag update| Sync
    Health -->|Healthy| Done([✅ Deployed])
    Health -->|Degraded| Rollback([⬅️ Rollback])
```

## Entity Relationship (data models)

```mermaid
erDiagram
    TEAM ||--o{ SERVICE : owns
    SERVICE ||--o{ DEPLOYMENT : has
    SERVICE ||--|| NAMESPACE : "deployed in"
    DEPLOYMENT }o--|| CLUSTER : "runs on"

    TEAM {
        string name
        string costCenter
    }
    SERVICE {
        string name
        string image
        string version
    }
```

## Gantt Chart (project timelines)

```mermaid
gantt
    title Migration Timeline
    dateFormat YYYY-MM-DD
    section Phase 1
        Terraform modules    :done, p1a, 2026-01-01, 2026-01-15
        Helm chart migration :done, p1b, 2026-01-10, 2026-01-25
    section Phase 2
        DEV deploy           :active, p2a, 2026-01-26, 2026-02-05
        HML validation       :p2b, after p2a, 10d
    section Phase 3
        PRD cutover          :crit, p3a, after p2b, 5d
```

## GitOps Flow (common at BDC)

```mermaid
flowchart TD
    Dev[Developer] -->|MR| GL[GitLab]
    GL -->|CI Pipeline| Harbor[Harbor Registry]
    GL -->|Values update| EnvRepo[Environment Repo]
    EnvRepo -->|Sync| Argo[ArgoCD]
    Argo -->|Deploy| EKS[EKS Cluster]
    Harbor -->|Pull image| EKS
```

---

## Tips

| Tip | Example |
|-----|---------|
| Direction | `LR` (left-right), `TB` (top-bottom), `TD` (top-down) |
| Shapes | `[rect]`, `(round)`, `{diamond}`, `([stadium])`, `[(cylinder)]` |
| Links | `-->` solid, `-.->` dotted, `==>` thick |
| Labels | `-->|label text|` |
| Subgraphs | Group related nodes visually |
| Styling | `style NodeID fill:#f9f,stroke:#333` |
