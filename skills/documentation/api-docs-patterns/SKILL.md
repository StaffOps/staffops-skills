---
name: api-docs-patterns
description: "Generate API docs from OpenAPI and protobuf."
version: 1.0.0
author: Carlos Felipe Gomes
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [api, docs, patterns, documentation]
    category: documentation
    related_skills: [markdown-docs, local-reference-docs]
---
# API Documentation Patterns

How to generate and maintain API documentation at <org>.

## When to Use

API documentation generation from OpenAPI/proto specs. Use when documenting REST/gRPC APIs, generating client SDKs, integrating API docs into MkDocs sites, or designing API contracts. Covers OpenAPI 3.x, protobuf docs, swagger-ui patterns, ReDoc, gRPC-Gateway.

## Decision matrix

| API type | Spec format | Docs tool | Output |
|----------|-------------|-----------|--------|
| **REST** | OpenAPI 3.x | Swagger UI / ReDoc / MkDocs | Interactive HTML |
| **gRPC** | Proto files | protoc-gen-doc | HTML / Markdown |
| **GraphQL** | SDL | GraphiQL / spectaql | Interactive |
| **Async/Events** | AsyncAPI | AsyncAPI Generator | HTML / Markdown |

## OpenAPI 3.x patterns

### Source of truth

Two approaches:

1. **Spec-first**: write OpenAPI YAML, generate code from it
2. **Code-first**: write code with annotations, generate spec

At <org>, spec-first is preferred for new APIs. Code-first is acceptable for legacy.

### File location

```
project/
├── api/
│   └── openapi.yaml          # Source of truth
├── docs/
│   └── api/
│       └── reference.md      # Generated or hand-curated
└── src/
```

### Standard OpenAPI sections

```yaml
openapi: 3.1.0
info:
  title: My Service API
  version: 1.0.0
  description: |
    Brief description (supports markdown).
  contact:
    name: <org> DevOps
    email: devops@<org-domain>
servers:
  - url: https://api.<org-domain>/v1
    description: Production
  - url: https://api-dev.<org-domain>/v1
    description: Development

tags:
  - name: orders
    description: Order management
  - name: health
    description: Health checks

paths:
  /orders/{id}:
    get:
      summary: Get order by ID
      operationId: getOrder
      tags: [orders]
      parameters:
        - $ref: '#/components/parameters/OrderId'
      responses:
        '200':
          description: Order found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Order'
        '404':
          $ref: '#/components/responses/NotFound'

components:
  schemas:
    Order:
      type: object
      required: [id, status]
      properties:
        id: { type: string, format: uuid }
        status: { type: string, enum: [pending, processing, completed] }

  parameters:
    OrderId:
      name: id
      in: path
      required: true
      schema: { type: string, format: uuid }

  responses:
    NotFound:
      description: Resource not found
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/Problem'
```

### Best practices

- Use `operationId` (camelCase, unique) — used by codegen
- Use `tags` — groups operations in docs
- Use `$ref: '#/components/...'` — DRY
- Use Problem Details (RFC 7807) for errors
- Use semantic HTTP status codes (200, 201, 204, 400, 401, 403, 404, 409, 422, 500, 503)
- Document AUTHENTICATION (`securitySchemes`)
- Use `format` for primitive types (`uuid`, `date-time`, `email`, `int64`)

### Generate docs from OpenAPI

#### Swagger UI (interactive)

```html
<!DOCTYPE html>
<html>
<head>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({ url: '/api/openapi.yaml', dom_id: '#swagger-ui' });
  </script>
</body>
</html>
```

#### ReDoc (single-page docs)

```html
<!DOCTYPE html>
<html>
<head><title>My API</title></head>
<body>
  <redoc spec-url="/api/openapi.yaml"></redoc>
  <script src="https://cdn.redocly.com/redoc/latest/bundles/redoc.standalone.js"></script>
</body>
</html>
```

#### MkDocs integration (mkdocs-render-swagger-plugin)

```yaml
# mkdocs.yml
plugins:
  - render_swagger:
      docExpansion: list
      filter: ""

# In docs:
```

```markdown
# API Reference

!!swagger api/openapi.yaml!!
```

### Validate OpenAPI

```bash
docker run --rm -v $(pwd):/spec wework/speccy lint /spec/openapi.yaml
```

Or use `redocly`:
```bash
docker run --rm -v $(pwd):/spec redocly/cli lint /spec/openapi.yaml
```

### Generate client SDKs

```bash
# Python client
docker run --rm -v $(pwd):/local openapitools/openapi-generator-cli generate \
  -i /local/api/openapi.yaml \
  -g python \
  -o /local/clients/python

# Generate to dotnet
docker run --rm -v $(pwd):/local openapitools/openapi-generator-cli generate \
  -i /local/api/openapi.yaml \
  -g csharp-netcore \
  -o /local/clients/dotnet
```

## gRPC / Protobuf docs

### Source of truth: `.proto` files

```proto
syntax = "proto3";

package order.v1;

import "google/api/annotations.proto";

service OrderService {
  // Get an order by its ID.
  rpc GetOrder(GetOrderRequest) returns (Order) {
    option (google.api.http) = {
      get: "/v1/orders/{id}"
    };
  }
}

message GetOrderRequest {
  string id = 1;
}

message Order {
  string id = 1;
  Status status = 2;

  enum Status {
    STATUS_UNSPECIFIED = 0;
    STATUS_PENDING = 1;
    STATUS_COMPLETED = 2;
  }
}
```

### Generate docs with protoc-gen-doc

```bash
docker run --rm -v $(pwd):/protos pseudomuto/protoc-gen-doc \
  --doc_opt=markdown,api.md \
  /protos/order.proto
```

Outputs:
- `--doc_opt=markdown,FILE` — Markdown
- `--doc_opt=html,FILE` — HTML
- `--doc_opt=json,FILE` — JSON

### gRPC-Gateway pattern

For exposing gRPC as REST:

```proto
service OrderService {
  rpc GetOrder(GetOrderRequest) returns (Order) {
    option (google.api.http) = {
      get: "/v1/orders/{id}"
    };
  }
}
```

This generates BOTH gRPC service AND HTTP/JSON gateway. Plus OpenAPI spec via `protoc-gen-openapiv2`.

### Doc conventions for proto

```proto
// Comment ABOVE the service describes the service.
service OrderService {
  // Comment ABOVE the RPC describes the operation.
  // Multi-line is fine.
  rpc GetOrder(GetOrderRequest) returns (Order);
}

message Order {
  // Field-level comments describe each field.
  string id = 1;
  Status status = 2;
}
```

## API documentation in MkDocs

### Embed OpenAPI spec

```markdown
# API Reference

## REST API

!!swagger ../api/openapi.yaml!!

## gRPC API

See [gRPC reference](../api/grpc.md) (generated from proto files).
```

### Manual narrative + auto-generated reference

```
docs/api/
├── index.md             # Manual: overview, getting started
├── authentication.md    # Manual: auth flows, tokens
├── rest-reference.md    # Auto-generated from OpenAPI
└── grpc-reference.md    # Auto-generated from .proto
```

This is best practice — narrative docs (concepts) + reference docs (auto-gen).

## Versioning APIs

### URL versioning (preferred for public APIs)

```
/v1/orders
/v2/orders
```

### Header versioning

```
Accept: application/vnd.<org>.api+json; version=1
```

### Deprecation

In OpenAPI:
```yaml
/old-endpoint:
  get:
    deprecated: true
    summary: '[DEPRECATED] use /new-endpoint instead'
```

In proto:
```proto
service OldService {
  option deprecated = true;
}

rpc OldMethod(...) returns (...) {
  option deprecated = true;
}
```

## Error response standards

### Use Problem Details (RFC 7807)

```json
{
  "type": "https://api.<org-domain>/errors/order-not-found",
  "title": "Order Not Found",
  "status": 404,
  "detail": "Order with ID 12345 does not exist.",
  "instance": "/v1/orders/12345"
}
```

In OpenAPI:
```yaml
components:
  schemas:
    Problem:
      type: object
      properties:
        type: { type: string, format: uri }
        title: { type: string }
        status: { type: integer }
        detail: { type: string }
        instance: { type: string }
```

## Common pitfalls

### Pitfall: spec drifts from implementation
Solution: validate spec in CI; generate either client OR server from spec to keep in sync.

### Pitfall: missing examples
Always include `example:` in OpenAPI schemas — makes docs much more useful.

### Pitfall: outdated docs after API changes
Treat it as one change: API change = OpenAPI/proto update + regenerate docs, in the same commit.

### Pitfall: too granular operationId
Bad: `getOrderById`, `getOrderByStatus`, `getOrderByCustomer`
Good: `getOrder` (with query params for filtering)

### Pitfall: error responses missing
Document EVERY non-2xx response (404, 400, 500). Otherwise clients can't handle them.

## Reference

- OpenAPI 3.1: https://spec.openapis.org/oas/v3.1.0
- Problem Details: https://datatracker.ietf.org/doc/html/rfc7807
- protoc-gen-doc: https://github.com/pseudomuto/protoc-gen-doc
- ReDoc: https://github.com/Redocly/redoc
- Swagger UI: https://swagger.io/tools/swagger-ui/
- Related: `markdown-docs`, `mkdocs-conventions`, `grpc-distributed-tracing`
