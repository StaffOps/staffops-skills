# Skill Cross-Reference Graph

> Auto-generated from `Related Skills` sections in SKILL.md files.
> Only skills with **≥5 inbound references** are shown as hubs.
> Sources shown only if they reference ≥2 hubs.

## Hub Skills (most referenced)

| Skill | Category | Inbound Refs |
|-------|----------|:------------:|
| `monitoring-stack-overview` | observability | **16** |
| `otel-collector-multi-cluster` | observability | **14** |
| `python-otel-patterns` | development | **12** |
| `cost-explorer` | aws | **11** |
| `alerting-strategy` | sre | **11** |
| `iam-patterns` | aws | **10** |
| `dotnet-otel-patterns` | development | **10** |
| `vmalert-configuration` | observability | **9** |
| `victoriametrics-troubleshooting` | observability | **9** |
| `incident-triage` | sre | **9** |
| `grpc-distributed-tracing` | development | **9** |
| `eks-management` | aws | **9** |
| `vm-cardinality-management` | observability | **8** |
| `sbom-vulnerability-management` | security | **8** |
| `python-grpc-aio` | development | **8** |
| `loki-logql-patterns` | observability | **8** |
| `helm-chart-app` | infrastructure | **8** |
| `container-image-apko` | security | **8** |
| `victoriametrics-investigation` | observability | **7** |
| `streaming-aggregation` | observability | **7** |
| `llm-cost-optimization` | ai | **7** |
| `external-secrets-aws-sm` | infrastructure | **7** |
| `cosign-image-signing` | infrastructure | **7** |
| `argocd-patterns` | infrastructure | **7** |
| `alertmanager-slack-config` | observability | **7** |
| `ai-agent-security` | ai | **7** |
| `agent-observability` | ai | **7** |
| `telemetry-standard` | development | **6** |
| `root-cause-analysis` | sre | **6** |
| `python-fastapi-patterns` | development | **6** |
| `prompt-injection-defense` | ai | **6** |
| `grafana-cross-signal-correlation` | observability | **6** |
| `go-patterns` | development | **6** |
| `ai-red-teaming` | ai | **6** |
| `tempo-traceql-patterns` | observability | **5** |
| `runbook-authoring` | sre | **5** |
| `python-scripting` | development | **5** |
| `otel-pipeline-troubleshooting` | observability | **5** |
| `mcp-server-security` | ai | **5** |
| `incident-response-runbook` | sre | **5** |
| `helmfile-k8s-addon` | infrastructure | **5** |
| `helmfile-applicationset` | infrastructure | **5** |
| `docker-compose-patterns` | containers | **5** |
| `container-runtime-debugging` | containers | **5** |
| `collector-internal-metrics` | apm-metrics | **5** |
| `aws-ftr-compliance` | security | **5** |
| `agent-skills-new-skill-checklist` | aws | **5** |
| `agent-evals` | ai | **5** |

## Relationship Graph

```mermaid
flowchart LR

  subgraph ai["Ai"]
    agent_evals[["agent-evals (5)"]]
    agent_observability[["agent-observability (7)"]]
    ai_agent_security[["ai-agent-security (7)"]]
    ai_coding_agent_guardrails["ai-coding-agent-guardrails"]
    ai_pipeline_orchestration["ai-pipeline-orchestration"]
    ai_red_teaming[["ai-red-teaming (6)"]]
    ai_security_hardening["ai-security-hardening"]
    ai_sre_incident_response["ai-sre-incident-response"]
    llm_app_security["llm-app-security"]
    llm_caching["llm-caching"]
    llm_cost_optimization[["llm-cost-optimization (7)"]]
    llmops_platform_engineering["llmops-platform-engineering"]
    mcp_server_security[["mcp-server-security (5)"]]
    model_registry_governance["model-registry-governance"]
    model_supply_chain_security["model-supply-chain-security"]
    prompt_injection_defense[["prompt-injection-defense (6)"]]
    rag_observability_evals["rag-observability-evals"]
  end

  subgraph apm_metrics["Apm Metrics"]
    collector_internal_metrics[["collector-internal-metrics (5)"]]
    external_secrets_metrics["external-secrets-metrics"]
    loki_tempo_self_metrics["loki-tempo-self-metrics"]
  end

  subgraph aws["Aws"]
    agent_skills_metric_verification["agent-skills-metric-verification"]
    agent_skills_new_skill_checklist[["agent-skills-new-skill-checklist (5)"]]
    cloudfront_patterns["cloudfront-patterns"]
    cost_explorer[["cost-explorer (11)"]]
    eks_management[["eks-management (9)"]]
    eks_node_troubleshooting["eks-node-troubleshooting"]
    iam_patterns[["iam-patterns (10)"]]
    lambda_patterns["lambda-patterns"]
    rds_patterns["rds-patterns"]
    route53_patterns["route53-patterns"]
    security_hub_patterns["security-hub-patterns"]
  end

  subgraph containers["Containers"]
    container_image_optimization["container-image-optimization"]
    container_runtime_debugging[["container-runtime-debugging (5)"]]
    docker_cli_operations["docker-cli-operations"]
    docker_compose_patterns[["docker-compose-patterns (5)"]]
    dockerfile_authoring["dockerfile-authoring"]
  end

  subgraph development["Development"]
    agent_platform_design["agent-platform-design"]
    anomaly_detection_deep["anomaly-detection-deep"]
    dotnet_async_patterns["dotnet-async-patterns"]
    dotnet_otel_patterns[["dotnet-otel-patterns (10)"]]
    go_patterns[["go-patterns (6)"]]
    grpc_distributed_tracing[["grpc-distributed-tracing (9)"]]
    interactive_debugging["interactive-debugging"]
    mcp_server_development["mcp-server-development"]
    prophet_isolation_forest_patterns["prophet-isolation-forest-patterns"]
    python_fastapi_patterns[["python-fastapi-patterns (6)"]]
    python_grpc_aio[["python-grpc-aio (8)"]]
    python_otel_patterns[["python-otel-patterns (12)"]]
    python_performance["python-performance"]
    python_scripting[["python-scripting (5)"]]
    secrets_management_dotnet["secrets-management-dotnet"]
    telemetry_standard[["telemetry-standard (6)"]]
  end

  subgraph finops["Finops"]
    ec2_rightsizing_patterns["ec2-rightsizing-patterns"]
    savings_plans_strategy["savings-plans-strategy"]
  end

  subgraph infrastructure["Infrastructure"]
    argocd_patterns[["argocd-patterns (7)"]]
    cosign_image_signing[["cosign-image-signing (7)"]]
    external_secrets_aws_sm[["external-secrets-aws-sm (7)"]]
    gitops_environments["gitops-environments"]
    helm_chart_app[["helm-chart-app (8)"]]
    helm_chart_cronworkflow["helm-chart-cronworkflow"]
    helmfile_applicationset[["helmfile-applicationset (5)"]]
    helmfile_k8s_addon[["helmfile-k8s-addon (5)"]]
    helmfile_templating["helmfile-templating"]
    istio_ambient_debugging["istio-ambient-debugging"]
    istio_ambient_otel["istio-ambient-otel"]
    karpenter_consolidation["karpenter-consolidation"]
    kyverno_policies["kyverno-policies"]
    terraform_modules["terraform-modules"]
  end

  subgraph observability["Observability"]
    alertmanager_slack_config[["alertmanager-slack-config (7)"]]
    cardinality_explosion_finder["cardinality-explosion-finder"]
    fluent_bit_loki_pipeline["fluent-bit-loki-pipeline"]
    fluent_bit_vs_otel_logs["fluent-bit-vs-otel-logs"]
    grafana_cross_signal_correlation[["grafana-cross-signal-correlation (6)"]]
    kafka_pipeline_health["kafka-pipeline-health"]
    kubelet_scrape_architecture["kubelet-scrape-architecture"]
    log_pattern_analyzer["log-pattern-analyzer"]
    loki_logql_patterns[["loki-logql-patterns (8)"]]
    monitoring_stack_overview[["monitoring-stack-overview (16)"]]
    multicluster_label_strategy["multicluster-label-strategy"]
    observability_tooling["observability-tooling"]
    otel_collector_multi_cluster[["otel-collector-multi-cluster (14)"]]
    otel_ebpf_instrumentation["otel-ebpf-instrumentation"]
    otel_pipeline_review["otel-pipeline-review"]
    otel_pipeline_troubleshooting[["otel-pipeline-troubleshooting (5)"]]
    pyroscope_profiling_patterns["pyroscope-profiling-patterns"]
    streaming_aggregation[["streaming-aggregation (7)"]]
    tempo_trace_investigation["tempo-trace-investigation"]
    tempo_traceql_patterns[["tempo-traceql-patterns (5)"]]
    tempo_v3_kafka_operations["tempo-v3-kafka-operations"]
    victoriametrics_investigation[["victoriametrics-investigation (7)"]]
    victoriametrics_troubleshooting[["victoriametrics-troubleshooting (9)"]]
    victoriametrics_tuning["victoriametrics-tuning"]
    vm_capacity_review["vm-capacity-review"]
    vm_cardinality_management[["vm-cardinality-management (8)"]]
    vmalert_configuration[["vmalert-configuration (9)"]]
  end

  subgraph projects["Projects"]
    telemetry_helper["telemetry-helper"]
  end

  subgraph security["Security"]
    aws_ftr_compliance[["aws-ftr-compliance (5)"]]
    container_image_apko[["container-image-apko (8)"]]
    container_package_melange["container-package-melange"]
    dependency_track_integration["dependency-track-integration"]
    golden_ami_creation["golden-ami-creation"]
    sbom_vulnerability_management[["sbom-vulnerability-management (8)"]]
    security_hub_findings_mgmt["security-hub-findings-mgmt"]
  end

  subgraph sre["Sre"]
    alerting_strategy[["alerting-strategy (11)"]]
    error_budget_framework["error-budget-framework"]
    incident_response_runbook[["incident-response-runbook (5)"]]
    incident_skip_criteria["incident-skip-criteria"]
    incident_triage[["incident-triage (9)"]]
    investigation_cost_guardrail["investigation-cost-guardrail"]
    metric_correlation_analysis["metric-correlation-analysis"]
    post_mortem_templates["post-mortem-templates"]
    root_cause_analysis[["root-cause-analysis (6)"]]
    runbook_authoring[["runbook-authoring (5)"]]
    sla_slo_design["sla-slo-design"]
  end

  subgraph workflows["Workflows"]
    gitops_environment_onboard["gitops-environment-onboard"]
  end

  %% Edges (source --> hub)
  agent_evals --> agent_observability
  agent_evals --> ai_red_teaming
  agent_evals --> llm_cost_optimization
  agent_observability --> dotnet_otel_patterns
  agent_observability --> llm_cost_optimization
  agent_observability --> otel_collector_multi_cluster
  agent_observability --> python_otel_patterns
  agent_platform_design --> cosign_image_signing
  agent_platform_design --> dotnet_otel_patterns
  agent_platform_design --> helm_chart_app
  agent_platform_design --> python_fastapi_patterns
  agent_platform_design --> python_grpc_aio
  agent_platform_design --> telemetry_standard
  agent_skills_metric_verification --> agent_skills_new_skill_checklist
  agent_skills_metric_verification --> victoriametrics_investigation
  ai_agent_security --> ai_red_teaming
  ai_agent_security --> mcp_server_security
  ai_agent_security --> prompt_injection_defense
  ai_coding_agent_guardrails --> ai_agent_security
  ai_coding_agent_guardrails --> ai_red_teaming
  ai_coding_agent_guardrails --> mcp_server_security
  ai_coding_agent_guardrails --> prompt_injection_defense
  ai_pipeline_orchestration --> agent_evals
  ai_pipeline_orchestration --> agent_observability
  ai_pipeline_orchestration --> llm_cost_optimization
  ai_red_teaming --> agent_evals
  ai_red_teaming --> ai_agent_security
  ai_red_teaming --> mcp_server_security
  ai_red_teaming --> prompt_injection_defense
  ai_security_hardening --> ai_agent_security
  ai_security_hardening --> external_secrets_aws_sm
  ai_security_hardening --> mcp_server_security
  ai_sre_incident_response --> agent_observability
  ai_sre_incident_response --> ai_agent_security
  ai_sre_incident_response --> ai_red_teaming
  ai_sre_incident_response --> incident_response_runbook
  ai_sre_incident_response --> llm_cost_optimization
  alerting_strategy --> alertmanager_slack_config
  alerting_strategy --> runbook_authoring
  alerting_strategy --> vmalert_configuration
  alertmanager_slack_config --> alerting_strategy
  alertmanager_slack_config --> monitoring_stack_overview
  alertmanager_slack_config --> vmalert_configuration
  anomaly_detection_deep --> alerting_strategy
  anomaly_detection_deep --> alertmanager_slack_config
  anomaly_detection_deep --> go_patterns
  anomaly_detection_deep --> python_grpc_aio
  anomaly_detection_deep --> vmalert_configuration
  argocd_patterns --> helmfile_applicationset
  argocd_patterns --> helmfile_k8s_addon
  aws_ftr_compliance --> iam_patterns
  aws_ftr_compliance --> sbom_vulnerability_management
  cardinality_explosion_finder --> streaming_aggregation
  cardinality_explosion_finder --> victoriametrics_investigation
  cardinality_explosion_finder --> vm_cardinality_management
  cloudfront_patterns --> cost_explorer
  cloudfront_patterns --> iam_patterns
  container_image_optimization --> container_image_apko
  container_image_optimization --> container_runtime_debugging
  container_package_melange --> container_image_apko
  container_package_melange --> cosign_image_signing
  container_package_melange --> sbom_vulnerability_management
  cosign_image_signing --> container_image_apko
  cosign_image_signing --> sbom_vulnerability_management
  dependency_track_integration --> container_image_apko
  dependency_track_integration --> cosign_image_signing
  dependency_track_integration --> sbom_vulnerability_management
  docker_cli_operations --> container_runtime_debugging
  docker_cli_operations --> docker_compose_patterns
  docker_compose_patterns --> container_runtime_debugging
  docker_compose_patterns --> helm_chart_app
  dockerfile_authoring --> container_image_apko
  dockerfile_authoring --> container_runtime_debugging
  dockerfile_authoring --> docker_compose_patterns
  dotnet_async_patterns --> dotnet_otel_patterns
  dotnet_async_patterns --> go_patterns
  dotnet_async_patterns --> grpc_distributed_tracing
  dotnet_otel_patterns --> grpc_distributed_tracing
  dotnet_otel_patterns --> otel_collector_multi_cluster
  dotnet_otel_patterns --> python_otel_patterns
  dotnet_otel_patterns --> telemetry_standard
  ec2_rightsizing_patterns --> cost_explorer
  ec2_rightsizing_patterns --> eks_management
  eks_management --> cost_explorer
  eks_management --> iam_patterns
  eks_node_troubleshooting --> cost_explorer
  eks_node_troubleshooting --> helm_chart_app
  eks_node_troubleshooting --> incident_triage
  error_budget_framework --> alerting_strategy
  error_budget_framework --> alertmanager_slack_config
  error_budget_framework --> runbook_authoring
  error_budget_framework --> vmalert_configuration
  external_secrets_aws_sm --> helmfile_k8s_addon
  external_secrets_aws_sm --> iam_patterns
  external_secrets_metrics --> collector_internal_metrics
  external_secrets_metrics --> external_secrets_aws_sm
  fluent_bit_loki_pipeline --> loki_logql_patterns
  fluent_bit_loki_pipeline --> monitoring_stack_overview
  fluent_bit_loki_pipeline --> otel_collector_multi_cluster
  fluent_bit_vs_otel_logs --> loki_logql_patterns
  fluent_bit_vs_otel_logs --> monitoring_stack_overview
  fluent_bit_vs_otel_logs --> otel_collector_multi_cluster
  gitops_environment_onboard --> argocd_patterns
  gitops_environment_onboard --> helm_chart_app
  gitops_environment_onboard --> helmfile_applicationset
  gitops_environments --> argocd_patterns
  gitops_environments --> helm_chart_app
  go_patterns --> grpc_distributed_tracing
  go_patterns --> python_grpc_aio
  go_patterns --> telemetry_standard
  golden_ami_creation --> aws_ftr_compliance
  golden_ami_creation --> container_image_apko
  golden_ami_creation --> eks_management
  golden_ami_creation --> sbom_vulnerability_management
  grafana_cross_signal_correlation --> loki_logql_patterns
  grafana_cross_signal_correlation --> monitoring_stack_overview
  grafana_cross_signal_correlation --> tempo_traceql_patterns
  grpc_distributed_tracing --> dotnet_otel_patterns
  grpc_distributed_tracing --> go_patterns
  grpc_distributed_tracing --> otel_collector_multi_cluster
  grpc_distributed_tracing --> python_grpc_aio
  grpc_distributed_tracing --> python_otel_patterns
  helm_chart_app --> argocd_patterns
  helm_chart_app --> external_secrets_aws_sm
  helm_chart_app --> helmfile_applicationset
  helm_chart_app --> helmfile_k8s_addon
  helm_chart_app --> telemetry_standard
  helm_chart_cronworkflow --> argocd_patterns
  helm_chart_cronworkflow --> helm_chart_app
  helm_chart_cronworkflow --> helmfile_applicationset
  helmfile_applicationset --> argocd_patterns
  helmfile_applicationset --> helm_chart_app
  helmfile_applicationset --> helmfile_k8s_addon
  helmfile_k8s_addon --> argocd_patterns
  helmfile_k8s_addon --> helmfile_applicationset
  helmfile_k8s_addon --> monitoring_stack_overview
  helmfile_templating --> alertmanager_slack_config
  helmfile_templating --> argocd_patterns
  helmfile_templating --> helmfile_k8s_addon
  helmfile_templating --> vmalert_configuration
  iam_patterns --> aws_ftr_compliance
  iam_patterns --> cost_explorer
  iam_patterns --> eks_management
  iam_patterns --> external_secrets_aws_sm
  incident_response_runbook --> alerting_strategy
  incident_response_runbook --> runbook_authoring
  incident_skip_criteria --> alerting_strategy
  incident_skip_criteria --> incident_triage
  incident_triage --> alerting_strategy
  incident_triage --> root_cause_analysis
  interactive_debugging --> container_runtime_debugging
  interactive_debugging --> dotnet_otel_patterns
  interactive_debugging --> go_patterns
  interactive_debugging --> python_otel_patterns
  investigation_cost_guardrail --> incident_triage
  investigation_cost_guardrail --> root_cause_analysis
  istio_ambient_debugging --> grpc_distributed_tracing
  istio_ambient_debugging --> monitoring_stack_overview
  istio_ambient_debugging --> otel_collector_multi_cluster
  istio_ambient_otel --> grpc_distributed_tracing
  istio_ambient_otel --> monitoring_stack_overview
  istio_ambient_otel --> otel_collector_multi_cluster
  kafka_pipeline_health --> otel_pipeline_troubleshooting
  kafka_pipeline_health --> victoriametrics_investigation
  karpenter_consolidation --> eks_management
  karpenter_consolidation --> monitoring_stack_overview
  kubelet_scrape_architecture --> monitoring_stack_overview
  kubelet_scrape_architecture --> streaming_aggregation
  kubelet_scrape_architecture --> victoriametrics_troubleshooting
  kyverno_policies --> container_image_apko
  kyverno_policies --> cosign_image_signing
  kyverno_policies --> helm_chart_app
  lambda_patterns --> cost_explorer
  lambda_patterns --> iam_patterns
  lambda_patterns --> python_fastapi_patterns
  llm_app_security --> ai_agent_security
  llm_app_security --> prompt_injection_defense
  llm_caching --> agent_observability
  llm_caching --> llm_cost_optimization
  llm_cost_optimization --> agent_evals
  llm_cost_optimization --> agent_observability
  llmops_platform_engineering --> agent_observability
  llmops_platform_engineering --> llm_cost_optimization
  log_pattern_analyzer --> incident_triage
  log_pattern_analyzer --> loki_logql_patterns
  log_pattern_analyzer --> root_cause_analysis
  loki_logql_patterns --> grafana_cross_signal_correlation
  loki_logql_patterns --> monitoring_stack_overview
  loki_logql_patterns --> tempo_traceql_patterns
  loki_logql_patterns --> victoriametrics_troubleshooting
  loki_tempo_self_metrics --> collector_internal_metrics
  loki_tempo_self_metrics --> loki_logql_patterns
  loki_tempo_self_metrics --> tempo_traceql_patterns
  loki_tempo_self_metrics --> victoriametrics_troubleshooting
  mcp_server_development --> docker_compose_patterns
  mcp_server_development --> python_fastapi_patterns
  mcp_server_development --> python_grpc_aio
  mcp_server_development --> python_otel_patterns
  mcp_server_security --> ai_agent_security
  mcp_server_security --> ai_red_teaming

  %% Styling
  style ai fill:#00b894,fill-opacity:0.1,stroke:#00b894
  style apm_metrics fill:#55a3c4,fill-opacity:0.1,stroke:#55a3c4
  style aws fill:#ff9f43,fill-opacity:0.1,stroke:#ff9f43
  style containers fill:#6c5ce7,fill-opacity:0.1,stroke:#6c5ce7
  style development fill:#45b7d1,fill-opacity:0.1,stroke:#45b7d1
  style finops fill:#ffeaa7,fill-opacity:0.1,stroke:#ffeaa7
  style infrastructure fill:#a29bfe,fill-opacity:0.1,stroke:#a29bfe
  style observability fill:#4ecdc4,fill-opacity:0.1,stroke:#4ecdc4
  style projects fill:#74b9ff,fill-opacity:0.1,stroke:#74b9ff
  style security fill:#fd79a8,fill-opacity:0.1,stroke:#fd79a8
  style sre fill:#ff6b6b,fill-opacity:0.1,stroke:#ff6b6b
  style workflows fill:#b2bec3,fill-opacity:0.1,stroke:#b2bec3
```

## Statistics

- **Hub skills** (≥5 inbound): 48
- **Active sources** (≥2 outbound to hubs): 108
- **Total nodes in graph**: 115
- **Total edges shown**: 200
- **Categories**: 12

## How to Read

- **Double-bordered nodes** `[[...]]` are hubs — heavily referenced by other skills
- **Number in parentheses** = inbound reference count
- **Arrows** show "references" direction (source → target)
- Skills clustered by category (color-coded subgraphs)
- If a skill is both a hub AND references other hubs, it appears as a connector

## Regeneration

```bash
# Extract edges from SKILL.md files
grep -rh 'Related [Ss]kills' skills/ --include='*.md' -A 20 | grep -oP '\x60[a-z][a-z0-9-]+\x60' | tr -d '\x60' | sort | uniq -c | sort -rn
```
