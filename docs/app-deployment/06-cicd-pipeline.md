---
id: cicd-pipeline
title: Full CI/CD Pipeline
sidebar_position: 6
---

# Full CI/CD Pipeline — Build → Scan → Package → Deploy

This is the complete GitLab CI pipeline that covers the entire deploy lifecycle: build the Docker image, scan it, package the Helm chart, push both to Harbor, then update the GitOps repo to trigger ArgoCD.

---

## Pipeline Stages

```text
build     → docker build + push image to Harbor
test      → unit tests inside container
scan      → Trivy vulnerability scan (fail on CRITICAL)
package   → helm package + push chart to Harbor OCI
promote   → bump chart version in gitops repo → ArgoCD takes over
```

---

## Complete `.gitlab-ci.yml`

```yaml
# .gitlab-ci.yml
stages:
  - build
  - test
  - scan
  - package
  - promote

variables:
  HARBOR_URL: harbor.local
  HARBOR_PROJECT: myteam
  APP_NAME: myapp
  CHART_PATH: ./chart
  GITOPS_REPO: https://gitlab.local/platform/gitops-repo.git
  IMAGE: $HARBOR_URL/$HARBOR_PROJECT/$APP_NAME

# ── Stage 1: Build ──────────────────────────────────────────────────
build-image:
  stage: build
  image: docker:24
  services:
    - docker:24-dind
  before_script:
    - docker login $HARBOR_URL -u $HARBOR_USER -p $HARBOR_PASSWORD
  script:
    - |
      docker build \
        --label "git.commit=$CI_COMMIT_SHA" \
        --label "git.branch=$CI_COMMIT_BRANCH" \
        --label "build.date=$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        -t $IMAGE:$CI_COMMIT_SHORT_SHA \
        -t $IMAGE:latest-$CI_COMMIT_BRANCH \
        .
    - docker push $IMAGE:$CI_COMMIT_SHORT_SHA
    - docker push $IMAGE:latest-$CI_COMMIT_BRANCH
  only:
    - main
    - /^release\/.*/

# ── Stage 2: Test ───────────────────────────────────────────────────
unit-tests:
  stage: test
  image: $IMAGE:$CI_COMMIT_SHORT_SHA
  script:
    - npm test                         # or pytest, go test, etc.
  coverage: '/Lines\s*:\s*(\d+\.?\d*)%/'
  artifacts:
    reports:
      junit: test-results/junit.xml
      coverage_report:
        coverage_format: cobertura
        path: coverage/cobertura-coverage.xml

# ── Stage 3: Scan ───────────────────────────────────────────────────
trivy-scan:
  stage: scan
  image:
    name: aquasec/trivy:latest
    entrypoint: [""]
  script:
    - trivy image \
        --exit-code 1 \
        --severity CRITICAL \
        --no-progress \
        --format table \
        $IMAGE:$CI_COMMIT_SHORT_SHA
  # Fail the pipeline if CRITICAL vulnerabilities are found
  allow_failure: false
  only:
    - main
    - /^release\/.*/

# ── Stage 4: Package Helm Chart ─────────────────────────────────────
package-chart:
  stage: package
  image: alpine/helm:3.14.0
  before_script:
    - helm registry login $HARBOR_URL -u $HARBOR_USER -p $HARBOR_PASSWORD
  script:
    # Set chart version = app version = semver from git tag or commit
    - export CHART_VERSION=${CI_COMMIT_TAG:-"0.0.0-$CI_COMMIT_SHORT_SHA"}
    - |
      # Update Chart.yaml versions
      sed -i "s/^version:.*/version: $CHART_VERSION/" $CHART_PATH/Chart.yaml
      sed -i "s/^appVersion:.*/appVersion: \"$CHART_VERSION\"/" $CHART_PATH/Chart.yaml
      # Update default image tag in values.yaml
      sed -i "s/tag:.*/tag: \"$CI_COMMIT_SHORT_SHA\"/" $CHART_PATH/values.yaml
    - helm dependency update $CHART_PATH
    - helm package $CHART_PATH --destination ./dist
    - helm push ./dist/$APP_NAME-$CHART_VERSION.tgz oci://$HARBOR_URL/charts
  artifacts:
    paths:
      - dist/
  only:
    - main
    - /^release\/.*/

# ── Stage 5: Promote to GitOps Repo ─────────────────────────────────
promote-staging:
  stage: promote
  image: alpine/git:latest
  before_script:
    - git config --global user.email "ci@platform.local"
    - git config --global user.name "GitLab CI"
  script:
    - export CHART_VERSION=${CI_COMMIT_TAG:-"0.0.0-$CI_COMMIT_SHORT_SHA"}
    # Clone gitops repo
    - git clone https://ci-token:$GITOPS_TOKEN@gitlab.local/platform/gitops-repo.git /tmp/gitops
    - cd /tmp/gitops
    # Bump chart version in staging values
    - |
      sed -i "s/targetRevision:.*/targetRevision: \"$CHART_VERSION\"/" \
        apps/$APP_NAME/application-staging.yaml
    - |
      sed -i "s/tag:.*/tag: \"$CI_COMMIT_SHORT_SHA\"/" \
        apps/$APP_NAME/values-staging.yaml
    - git add .
    - git commit -m "chore: bump $APP_NAME staging to $CHART_VERSION [skip ci]"
    - git push origin main
  only:
    - main
  environment:
    name: staging
    url: https://$APP_NAME.staging.yourdomain.com

promote-production:
  stage: promote
  image: alpine/git:latest
  before_script:
    - git config --global user.email "ci@platform.local"
    - git config --global user.name "GitLab CI"
  script:
    - export CHART_VERSION=$CI_COMMIT_TAG
    - git clone https://ci-token:$GITOPS_TOKEN@gitlab.local/platform/gitops-repo.git /tmp/gitops
    - cd /tmp/gitops
    - |
      sed -i "s/targetRevision:.*/targetRevision: \"$CHART_VERSION\"/" \
        apps/$APP_NAME/application-prod.yaml
    - |
      sed -i "s/tag:.*/tag: \"$CI_COMMIT_SHORT_SHA\"/" \
        apps/$APP_NAME/values-prod.yaml
    - git add .
    - git commit -m "chore: bump $APP_NAME production to $CHART_VERSION [skip ci]"
    - git push origin main
  only:
    - /^v\d+\.\d+\.\d+$/   # only on semver tags: v1.2.3
  when: manual              # human approval before production
  environment:
    name: production
    url: https://$APP_NAME.yourdomain.com
```

---

## Required CI/CD Variables

Set these in GitLab → Settings → CI/CD → Variables:

| Variable | Value | Protected | Masked |
|---|---|---|---|
| `HARBOR_USER` | `ci-robot` | ✅ | ✅ |
| `HARBOR_PASSWORD` | `<robot token>` | ✅ | ✅ |
| `GITOPS_TOKEN` | GitLab deploy token | ✅ | ✅ |

---

## Release Workflow (Semantic Versioning)

```bash
# Feature ready for production
git tag v1.3.0
git push origin v1.3.0

# GitLab CI triggers:
#   build → test → scan → package → promote-production (manual)
```

```text
v1.3.0 tag pushed
    ↓
CI builds image: harbor.local/myteam/myapp:<sha>
CI packages chart: harbor.local/charts/myapp:1.3.0
CI updates gitops-repo → values-prod.yaml
    ↓
ArgoCD detects change (OutOfSync)
Release manager clicks SYNC in ArgoCD UI
    ↓
Production deploys v1.3.0
```

---

## Pipeline Visualization

```text
 build-image ──→ unit-tests ──→ trivy-scan ──→ package-chart ──→ promote-staging
                                                                       │
                                                       (on tag v*)     ↓
                                                               promote-production
                                                               [manual approval]
```

---

## Done When

```text
✔ Pipeline runs green on push to main
✔ Image appears in Harbor with correct tag
✔ Helm chart appears in Harbor OCI charts
✔ gitops-repo staging values updated automatically
✔ ArgoCD picks up change and syncs staging
✔ Production deploy requires git tag + manual approval
```
